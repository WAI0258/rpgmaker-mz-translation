#!/usr/bin/env python3
"""Initialize/resume one translation workspace, or run a command inside it.

Workspace mode checks paths before writes; it is not an OS sandbox for external
commands, other processes or concurrent filesystem changes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

from json_safety import Document, json_files, strict_loads

TOOL_ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ('backup', 'backup/data', 'backup/js', 'text', 'images', 'build',
           'build/source/data', 'build/js', 'build/translated', 'reports', 'tmp')
CONFIG_KEYS = {'schema_version', 'workspace_root', 'game_root', 'runtime_relative',
               'engine', 'target_language', 'backup_sha256'}


def inside(path, root):
    return path == root or root in path.parents


def overlap(a, b):
    return inside(a, b) or inside(b, a)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(path):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink() or
            getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError(f'expected a regular, unlinked file: {path}')
    if info.st_nlink > 1:
        raise ValueError(f'hard-linked file is not allowed: {path}')


def separate(root, game):
    if overlap(root, game) or overlap(root, TOOL_ROOT):
        raise ValueError('workspace must be outside both the game and tool trees')


def detect_game(game):
    if not game.is_dir():
        raise ValueError('game must be an existing directory')
    matches = []
    for relative in ('.', 'www'):
        runtime = game / relative
        for engine, core in (('MZ', 'rmmz_core.js'), ('MV', 'rpg_core.js')):
            if (runtime / 'data').is_dir() and (runtime / 'js' / core).is_file():
                matches.append((relative, engine))
    if len(matches) != 1:
        raise ValueError('cannot identify a unique MV/MZ runtime (root or www); inspect the game layout')
    relative, engine = matches[0]
    runtime = game / relative
    if not inside(runtime.resolve(), game):
        raise ValueError('runtime escapes the game tree')
    for path in (runtime / 'js' / ('rmmz_core.js' if engine == 'MZ' else 'rpg_core.js'),
                 runtime / 'js' / 'plugins.js'):
        if not inside(path.resolve(), game):
            raise ValueError('game input escapes the game tree')
        regular(path)
    if not inside((runtime / 'data').resolve(), game):
        raise ValueError('data directory escapes the game tree')
    files = json_files(runtime / 'data')
    # This writer handles top-level data JSON; reject special inputs rather than copy links.
    for path in files.values():
        regular(path)
    return relative, engine, files


class Workspace:
    def __init__(self, config_path):
        config_path = Path(config_path).absolute()
        if config_path.name != 'workspace.json':
            raise ValueError('--task must select workspace.json')
        regular(config_path)
        self.root = config_path.parent.resolve()
        if config_path.resolve().parent != self.root:
            raise ValueError('task configuration escapes the workspace')
        self.config_path = config_path.resolve()
        self.config = strict_loads(config_path.read_text(encoding='utf-8'))
        data = self.config
        if (not isinstance(data, dict) or set(data) != CONFIG_KEYS or
                type(data['schema_version']) is not int or data['schema_version'] != 1):
            raise ValueError('unsupported workspace configuration')
        for key in ('workspace_root', 'game_root', 'target_language'):
            if not isinstance(data[key], str) or not data[key].strip():
                raise ValueError(f'invalid workspace field: {key}')
        if not Path(data['workspace_root']).is_absolute() or Path(data['workspace_root']).resolve() != self.root:
            raise ValueError('workspace identity differs from its stored location')
        if not Path(data['game_root']).is_absolute():
            raise ValueError('game identity must be an absolute path')
        self.game = Path(data['game_root']).resolve()
        separate(self.root, self.game)
        if data['runtime_relative'] not in ('.', 'www') or data['engine'] not in ('MV', 'MZ'):
            raise ValueError('invalid runtime identity')
        for folder in FOLDERS:
            path = self.path(folder)
            if path != self.root / folder or not path.is_dir():
                raise ValueError(f'missing or redirected workspace directory: {folder}')
        expected = data['backup_sha256']
        if not isinstance(expected, dict) or not expected:
            raise ValueError('missing backup digests')
        for name, sha in expected.items():
            if (not isinstance(name, str) or not isinstance(sha, str) or len(sha) != 64 or
                    any(c not in '0123456789abcdef' for c in sha)):
                raise ValueError('invalid backup digest')
            path = self.path('backup/' + name)
            regular(path)
            if digest(path) != sha:
                raise ValueError(f'pristine backup changed: {name}')
        actual_data = {'data/' + name for name in json_files(self.path('backup/data'))}
        if actual_data != {name for name in expected if name.startswith('data/')}:
            raise ValueError('backup data file set changed')
        if 'js/plugins.js' not in expected:
            raise ValueError('missing plugins.js backup digest')

    def path(self, value):
        value = Path(value)
        if '..' in value.parts:
            raise ValueError('parent traversal is not allowed in task paths')
        result = (value if value.is_absolute() else self.root / value).resolve()
        if not inside(result, self.root):
            raise ValueError(f'path escapes the workspace: {value}')
        return result

    def output(self, value):
        result = self.path(value)
        if (result == self.root or overlap(result, self.path('backup')) or
                overlap(result, self.config_path) or overlap(result, self.path('text/patch.json'))):
            raise ValueError('output would overwrite workspace identity or pristine backup')
        if result.is_file():
            regular(result)
        return result

    def source(self, value=None):
        result = self.path(value or 'backup/data')
        if result != self.path('backup/data'):
            raise ValueError('task source/backup must be the pristine backup/data')
        return result

    def current(self, value=None):
        if value is None:
            value = ('build/translated/data' if self.path('build/translated/data').exists()
                     else 'build/source/data')
        result = self.path(value)
        if overlap(result, self.path('backup')):
            raise ValueError('current data must be a working copy, not the backup')
        return result

    def manifest(self, value=None):
        result = self.path(value or 'text/patch.json')
        if not result.is_file():
            raise ValueError(f'missing patch manifest: {result}')
        return result

    def check_live(self):
        relative, engine, files = detect_game(self.game)
        if (relative, engine) != (self.config['runtime_relative'], self.config['engine']):
            raise ValueError('game runtime identity changed')
        actual = {'data/' + name: digest(path) for name, path in files.items()}
        actual['js/plugins.js'] = digest(self.game / relative / 'js/plugins.js')
        if actual != self.config['backup_sha256']:
            raise ValueError('live game differs from the initial snapshot; inspect before resuming, do not replace backups')

    def environment(self):
        env = os.environ.copy()
        settings = {key: str(self.path('tmp')) for key in ('TMPDIR', 'TEMP', 'TMP')}
        settings.update({'PYTHONDONTWRITEBYTECODE': '1',
                         'XDG_CACHE_HOME': str(self.path('tmp/cache')),
                         'PIP_CACHE_DIR': str(self.path('tmp/pip-cache')),
                         'npm_config_cache': str(self.path('tmp/npm-cache'))})
        # Windows names are case-insensitive; npm also accepts mixed-case config.
        # Remove inherited aliases so a child cannot select an outside cache.
        names = {key.lower() for key in settings}
        env = {key: value for key, value in env.items() if key.lower() not in names}
        env.update(settings)
        return env


def initialize(game, root=None, target_language='zh-CN'):
    game = Path(game).resolve()
    if not target_language.strip():
        raise ValueError('target language cannot be empty')
    root = Path(root).resolve() if root else game.with_name(game.name + '_translation_work')
    separate(root, game)
    if root.exists():
        task = Workspace(root / 'workspace.json')
        if task.game != game or task.config['target_language'] != target_language:
            raise ValueError('workspace belongs to a different game or target language')
        task.check_live()
        return task, False
    if not root.parent.is_dir():
        raise ValueError('workspace parent must already exist')
    relative, engine, files = detect_game(game)
    originals = {name: path.read_bytes() for name, path in files.items()}
    for raw in originals.values():
        Document(raw)
    plugins = game / relative / 'js/plugins.js'
    plugins_raw = plugins.read_bytes()
    root.mkdir()  # Do not adopt or overwrite a pre-existing directory.
    for folder in FOLDERS:
        (root / folder).mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, raw in originals.items():
        for folder in ('backup/data', 'build/source/data'):
            (root / folder / name).write_bytes(raw)
        hashes['data/' + name] = hashlib.sha256(raw).hexdigest()
    (root / 'backup/js/plugins.js').write_bytes(plugins_raw)
    (root / 'build/js/plugins.js').write_bytes(plugins_raw)
    hashes['js/plugins.js'] = hashlib.sha256(plugins_raw).hexdigest()
    latest = {name: path.read_bytes() for name, path in json_files(game / relative / 'data').items()}
    if latest != originals or plugins.read_bytes() != plugins_raw:
        raise ValueError('game changed during initialization; incomplete workspace retained for inspection')
    config = {'schema_version': 1, 'workspace_root': str(root), 'game_root': str(game),
              'runtime_relative': relative, 'engine': engine, 'target_language': target_language,
              'backup_sha256': hashes}
    with (root / 'workspace.json').open('x', encoding='utf-8') as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
        file.write('\n')
    (root / 'progress.md').write_text('Workspace initialized. Original game is untouched.\n', encoding='utf-8')
    return Workspace(root / 'workspace.json'), True


def configure_task(args, mode):
    """Resolve a CLI's defaults and validate all supplied task paths before any write."""
    task = Workspace(args.task)
    if mode == 'apply':
        args.source = str(task.source(args.source))
        if not args.describe:
            args.manifest = str(task.manifest(args.manifest))
            args.output = str(task.output(args.output or 'build/translated/data'))
    else:
        args.current = str(task.current(args.current))
        args.backup = str(task.source(args.backup))
        if args.manifest:
            args.manifest = str(task.manifest(args.manifest))
        elif task.path('build/translated/data') == Path(args.current):
            args.manifest = str(task.manifest())
        if mode == 'audit':
            args.out = str(task.output(args.out or 'reports/audit.txt'))
            args.json_out = str(task.output(args.json_out or 'reports/inventory.json'))
            args.plugins = str(task.path(args.plugins or 'build/js/plugins.js'))
            args.plugins_backup = str(task.path(args.plugins_backup or 'backup/js/plugins.js'))
            if Path(args.plugins_backup) != task.path('backup/js/plugins.js'):
                raise ValueError('task plugin backup must be backup/js/plugins.js')
            if overlap(Path(args.plugins), task.path('backup')):
                raise ValueError('plugin current must be a working copy')
        else:
            args.json_out = str(task.output(args.json_out or 'reports/verify.json'))
    return task


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='Create or resume the game-specific workspace')
    init.add_argument('--game', required=True)
    init.add_argument('--workspace')
    init.add_argument('--target-language', default='zh-CN')
    show = sub.add_parser('show', help='Validate identity/backups and show task paths')
    show.add_argument('--task', required=True)
    run = sub.add_parser('run', help='Run a command with workspace cwd and local temp/cache settings (not a sandbox)')
    run.add_argument('--task', required=True)
    run.add_argument('argv', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            task, created = initialize(args.game, args.workspace, args.target_language)
        else:
            task, created = Workspace(args.task), False
        if args.command == 'run':
            command = args.argv[1:] if args.argv[:1] == ['--'] else args.argv
            if not command:
                parser.error('run requires a command after --')
            return subprocess.run(command, cwd=task.root, env=task.environment(), check=False).returncode
        print(json.dumps({'created': created, 'task': str(task.config_path),
                          'game': str(task.game), 'engine': task.config['engine'],
                          'workspace': str(task.root), 'current': str(task.current()),
                          'backup': str(task.source()), 'manifest': str(task.path('text/patch.json'))},
                         ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(f'ERROR: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
