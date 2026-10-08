"""Workspace boundaries and realistic task CLI integration; synthetic games only."""
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from translation_workspace import Workspace, initialize, main as workspace_main
from apply_translation import main as writer_main
from audit_visible_jp import main as audit_main
from verify_untouched import main as verifier_main
from json_safety import snapshot_hash


def hashes(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.game = self.base / 'game'
        self.runtime = self.make_game(self.game)
        self.original = hashes(self.game)

    def make_game(self, game, engine='MZ', www=False):
        runtime = game / 'www' if www else game
        (runtime / 'data').mkdir(parents=True)
        (runtime / 'js').mkdir()
        (runtime / 'js' / ('rmmz_core.js' if engine == 'MZ' else 'rpg_core.js')).write_text('// synthetic core')
        (runtime / 'js/plugins.js').write_text('var $plugins = [];')
        (runtime / 'data/Armors.json').write_text(json.dumps([None, {'id': 1, 'name': '原文', 'note': '<tag:1>'}]))
        (runtime / 'data/System.json').write_text('{"gameTitle":"Original"}')
        return runtime

    def init(self, root=None):
        task, created = initialize(self.game, root)
        self.assertTrue(created)
        return task

    def quiet(self, fn, args):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return fn(args)

    def plan(self, task):
        raw = {p.name: p.read_bytes() for p in task.source().glob('*.json')}
        manifest = {'schema_version': 1, 'source_sha256': snapshot_hash(raw), 'files': [
            {'file': 'Armors.json', 'sha256': hashlib.sha256(raw['Armors.json']).hexdigest(),
             'changes': [{'path': '/1/name', 'old': '原文', 'new': '译文'}]}]}
        task.path('text/patch.json').write_text(json.dumps(manifest))

    def test_default_init_and_resume_are_isolated_and_preserve_originals(self):
        task = self.init()
        self.assertEqual(task.root, self.base / 'game_translation_work')
        self.assertEqual(task.config['engine'], 'MZ')
        before = hashes(task.root)
        task2, created = initialize(self.game)
        self.assertFalse(created)
        self.assertEqual(task2.root, task.root)
        self.assertEqual(hashes(task.root), before)
        self.assertEqual(hashes(self.game), self.original)
        self.assertEqual(set(p.name for p in self.base.iterdir()), {'game', 'game_translation_work'})
        self.assertEqual(task.source().joinpath('Armors.json').read_bytes(), task.current().joinpath('Armors.json').read_bytes())

    def test_mv_www_and_custom_workspace(self):
        game = self.base / 'MV'
        self.make_game(game, engine='MV', www=True)
        task, _ = initialize(game, self.base / 'custom')
        self.assertEqual(task.config['engine'], 'MV')
        self.assertEqual(task.config['runtime_relative'], 'www')
        self.assertEqual(task.game, game)

    def test_unknown_or_ambiguous_layout_does_not_create_workspace(self):
        (self.runtime / 'js/rpg_core.js').write_text('// conflicting marker')
        with self.assertRaises(ValueError):
            initialize(self.game)
        self.assertFalse((self.base / 'game_translation_work').exists())
        (self.runtime / 'js/rpg_core.js').unlink()
        (self.runtime / 'js/rmmz_core.js').unlink()
        with self.assertRaises(ValueError):
            initialize(self.game)
        self.assertFalse((self.base / 'game_translation_work').exists())

    def test_invalid_data_does_not_create_workspace(self):
        (self.runtime / 'data/System.json').write_text('{"duplicate":1,"duplicate":2}')
        with self.assertRaises(ValueError):
            initialize(self.game)
        self.assertFalse((self.base / 'game_translation_work').exists())

    def test_overlap_and_preexisting_unrelated_workspace_are_rejected(self):
        for root in (self.game, self.game / 'work', self.base, SCRIPTS / 'work'):
            with self.subTest(root=root), self.assertRaises(ValueError):
                initialize(self.game, root)
        occupied = self.base / 'occupied'
        occupied.mkdir()
        (occupied / 'mine').write_text('keep')
        with self.assertRaises(OSError):
            initialize(self.game, occupied)
        self.assertEqual(hashes(occupied), {'mine': hashlib.sha256(b'keep').hexdigest()})

    def test_resume_other_game_or_language_does_not_change_workspace(self):
        task = self.init()
        before = hashes(task.root)
        other = self.base / 'other'
        self.make_game(other)
        with self.assertRaises(ValueError):
            initialize(other, task.root)
        with self.assertRaises(ValueError):
            initialize(self.game, task.root, 'en')
        self.assertEqual(hashes(task.root), before)

    def test_resume_detects_live_game_change_without_replacing_backup(self):
        task = self.init()
        before = hashes(task.root)
        (self.runtime / 'data/System.json').write_text('{"gameTitle":"new build"}')
        with self.assertRaises(ValueError):
            initialize(self.game)
        self.assertEqual(hashes(task.root), before)

    def test_backup_tampering_addition_and_configuration_relocation_fail(self):
        task = self.init()
        original = task.source().joinpath('Armors.json').read_bytes()
        task.source().joinpath('Armors.json').write_bytes(b'[]')
        with self.assertRaises(ValueError):
            Workspace(task.config_path)
        task.source().joinpath('Armors.json').write_bytes(original)
        task.source().joinpath('Extra.json').write_bytes(b'[]')
        with self.assertRaises(ValueError):
            Workspace(task.config_path)
        task.source().joinpath('Extra.json').unlink()
        task.config['workspace_root'] = str(self.base / 'elsewhere')
        task.config_path.write_text(json.dumps(task.config))
        with self.assertRaises(ValueError):
            Workspace(task.config_path)

    def test_all_task_cli_outputs_land_in_workspace_from_unrelated_cwd(self):
        task = self.init()
        args = ['--task', str(task.config_path)]
        previous = Path.cwd()
        os.chdir(self.base)
        self.addCleanup(os.chdir, previous)
        self.assertEqual(self.quiet(audit_main, args), 0)
        self.assertTrue(task.path('reports/audit.txt').is_file())
        self.assertTrue(task.path('reports/inventory.json').is_file())
        self.assertFalse((self.base / 'audit_visible_jp.txt').exists())
        self.assertEqual(self.quiet(writer_main, args + ['--describe']), 0)
        self.plan(task)
        self.assertEqual(self.quiet(writer_main, args), 0)
        self.assertFalse(task.path('build/translated/data').exists())
        self.assertEqual(self.quiet(writer_main, args + ['--write']), 0)
        self.assertEqual(self.quiet(verifier_main, args), 0)
        self.assertEqual(self.quiet(audit_main, args), 0)
        result = json.loads(task.path('reports/verify.json').read_text(encoding='utf-8'))
        self.assertTrue(result['complete'])
        self.assertTrue(result['manifest_checked'])
        self.assertTrue(json.loads(task.path('reports/inventory.json').read_text(encoding='utf-8'))['integrity']['manifest_checked'])
        self.assertEqual(hashes(self.game), self.original)
        self.assertEqual(set(p.name for p in self.base.iterdir()), {'game', 'game_translation_work'})

    def test_large_initial_event_copy_still_extracts_inventory_and_checks_choices(self):
        commands = []
        for i in range(600):
            commands.extend([{'code': 101, 'indent': 0, 'parameters': ['Face', 0, 0, 2, '']},
                             {'code': 401, 'indent': 0, 'parameters': ['会话' + str(i)]}])
        (self.runtime / 'data/Map001.json').write_text(json.dumps({'events': [None, {'pages': [{'list': commands}]}]}))
        task = self.init()
        args = ['--task', str(task.config_path)]
        self.assertEqual(self.quiet(audit_main, args), 0)
        inventory = json.loads(task.path('reports/inventory.json').read_text(encoding='utf-8'))
        self.assertEqual(sum(row['src'] == 'Map001.json' and row['role'] == '显示文本' for row in inventory['rows']), 600)
        bad = [{'code': 102, 'indent': 0, 'parameters': [['A'], 0]},
               {'code': 402, 'indent': 0, 'parameters': [0, 'wrong']},
               {'code': 404, 'indent': 0, 'parameters': []}]
        # Even an exact initial copy must report broken choice routing labels.
        map_path = task.path('build/source/data/Map001.json')
        value = {'events': [None, {'pages': [{'list': bad}]}]}
        map_path.write_text(json.dumps(value))
        backup_path = task.path('backup/data/Map001.json')
        backup_path.write_bytes(map_path.read_bytes())
        task.config['backup_sha256']['data/Map001.json'] = hashlib.sha256(backup_path.read_bytes()).hexdigest()
        task.config_path.write_text(json.dumps(task.config))
        self.assertEqual(self.quiet(audit_main, args), 1)

    def test_relative_overrides_are_relative_to_task_and_existing_output_is_not_overwritten(self):
        task = self.init()
        self.plan(task)
        args = ['--task', str(task.config_path)]
        self.assertEqual(self.quiet(writer_main, args + ['--output', 'build/custom-data', '--write']), 0)
        before = hashes(task.path('build/custom-data'))
        self.assertEqual(self.quiet(writer_main, args + ['--output', 'build/custom-data', '--write']), 1)
        self.assertEqual(hashes(task.path('build/custom-data')), before)
        self.assertEqual(self.quiet(verifier_main, args + ['--current', 'build/custom-data',
                              '--manifest', 'text/patch.json', '--json-out', 'reports/custom.json']), 0)
        self.assertTrue(task.path('reports/custom.json').is_file())

    def test_every_task_path_override_rejects_escape_before_writing(self):
        task = self.init()
        self.plan(task)
        args = ['--task', str(task.config_path)]
        outside = str(self.base / 'outside')
        cases = [(audit_main, ['--out', outside]), (audit_main, ['--json-out', outside]),
                 (audit_main, ['--current', str(self.runtime / 'data')]),
                 (audit_main, ['--plugins', str(self.runtime / 'js/plugins.js')]),
                 (audit_main, ['--plugins-backup', str(self.runtime / 'js/plugins.js')]),
                 (verifier_main, ['--json-out', outside]), (verifier_main, ['--backup', outside]),
                 (writer_main, ['--source', outside]), (writer_main, ['--output', outside, '--write']),
                 (writer_main, ['--manifest', outside]), (audit_main, ['--out', '../outside'])]
        before = hashes(task.root)
        for fn, options in cases:
            with self.subTest(fn=fn.__name__, options=options), self.assertRaises(SystemExit):
                self.quiet(fn, args + options)
            self.assertFalse((self.base / 'outside').exists())
            self.assertEqual(hashes(task.root), before)

    def test_outputs_cannot_overwrite_config_backup_or_input(self):
        task = self.init()
        self.plan(task)
        args = ['--task', str(task.config_path)]
        for output in ('workspace.json', 'backup/js/plugins.js', 'backup', 'text/patch.json', 'build/js/plugins.js'):
            with self.subTest(output=output), self.assertRaises(SystemExit):
                self.quiet(audit_main, args + ['--out', output])
        with self.assertRaises(SystemExit):
            self.quiet(writer_main, args + ['--output', 'backup/new-data', '--write'])
        self.assertEqual(hashes(self.game), self.original)

    def test_missing_manifest_for_translated_data_fails_instead_of_partial_audit(self):
        task = self.init()
        self.plan(task)
        args = ['--task', str(task.config_path)]
        self.assertEqual(self.quiet(writer_main, args + ['--write']), 0)
        task.path('text/patch.json').unlink()
        with self.assertRaises(SystemExit):
            self.quiet(audit_main, args)
        with self.assertRaises(SystemExit):
            self.quiet(verifier_main, args)
        self.assertFalse(task.path('reports/verify.json').exists())

    def test_report_hardlink_cannot_mutate_other_files(self):
        task = self.init()
        outside = self.base / 'important'
        outside.write_text('keep')
        link = task.path('reports/link.txt')
        os.link(outside, link)
        with self.assertRaises(SystemExit):
            self.quiet(audit_main, ['--task', str(task.config_path), '--out', str(link)])
        self.assertEqual(outside.read_text(encoding='utf-8'), 'keep')

    def directory_link(self, link, destination):
        if os.name == 'nt':
            result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(destination)], capture_output=True)
            if result.returncode:
                self.skipTest('cannot create test junction')
        else:
            link.symlink_to(destination, target_is_directory=True)
        # Remove only the link, before TemporaryDirectory removes the test root.
        self.addCleanup(link.rmdir if os.name == 'nt' else link.unlink)

    def test_directory_junction_or_symlink_escape_is_rejected(self):
        task = self.init()
        outside = self.base / 'outside'
        outside.mkdir()
        link = task.root / 'reports/redirect'
        self.directory_link(link, outside)
        with self.assertRaises(SystemExit):
            self.quiet(audit_main, ['--task', str(task.config_path), '--out', 'reports/redirect/report.txt'])
        self.assertEqual(list(outside.iterdir()), [])

    def test_managed_temp_directory_cannot_redirect_into_backup(self):
        task = self.init()
        temp = task.root / 'tmp'
        temp.rmdir()
        self.directory_link(temp, task.root / 'backup')
        with self.assertRaises(ValueError):
            Workspace(task.config_path)

    def test_audit_reports_cannot_overwrite_each_other(self):
        task = self.init()
        with self.assertRaises(SystemExit):
            self.quiet(audit_main, ['--task', str(task.config_path),
                                    '--out', 'reports/same.json', '--json-out', 'reports/same.json'])
        self.assertFalse(task.path('reports/same.json').exists())

    def test_game_data_link_outside_game_is_not_adopted(self):
        outside = self.base / 'outside-data'
        (self.runtime / 'data').rename(outside)
        self.directory_link(self.runtime / 'data', outside)
        with self.assertRaises(ValueError):
            initialize(self.game)
        self.assertFalse((self.base / 'game_translation_work').exists())

    def test_run_localizes_cwd_and_temp_cache_without_changing_parent_environment(self):
        task = self.init()
        environment = dict(os.environ)
        code = ("import json,os,tempfile; from pathlib import Path; "
                "p=Path(tempfile.mkstemp()[1]); "
                "Path('reports/child.json').write_text(json.dumps({'cwd':os.getcwd(),'temp':str(p),'cache':os.environ['XDG_CACHE_HOME']}))")
        self.assertEqual(self.quiet(workspace_main, ['run', '--task', str(task.config_path), '--', sys.executable, '-B', '-c', code]), 0)
        result = json.loads(task.path('reports/child.json').read_text(encoding='utf-8'))
        self.assertEqual(Path(result['cwd']), task.root)
        self.assertEqual(Path(result['temp']).parent, task.path('tmp'))
        self.assertEqual(Path(result['cache']), task.path('tmp/cache'))
        self.assertEqual(dict(os.environ), environment)
        self.assertFalse(list(task.root.rglob('*.pyc')))

    def test_runner_replaces_inherited_mixed_case_cache_locations(self):
        task = self.init()
        with patch.dict(os.environ, {'NPM_CONFIG_CACHE': str(self.base / 'outside-cache'),
                                     'npm_config_cache': str(self.base / 'other-cache')}):
            parent = dict(os.environ)
            env = task.environment()
            candidates = [value for key, value in env.items() if key.lower() == 'npm_config_cache']
            self.assertEqual(candidates, [str(task.path('tmp/npm-cache'))])
            self.assertEqual(dict(os.environ), parent)

    def test_cli_init_show_and_unknown_task_schema(self):
        self.assertEqual(self.quiet(workspace_main, ['init', '--game', str(self.game)]), 0)
        config = self.base / 'game_translation_work/workspace.json'
        self.assertEqual(self.quiet(workspace_main, ['show', '--task', str(config)]), 0)
        data = json.loads(config.read_text(encoding='utf-8'))
        data['schema_version'] = 99
        config.write_text(json.dumps(data))
        self.assertEqual(self.quiet(workspace_main, ['show', '--task', str(config)]), 1)


if __name__ == '__main__':
    unittest.main()
