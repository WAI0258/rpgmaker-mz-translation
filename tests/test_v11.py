"""Synthetic regressions for v1.1; no game assets, API calls or extra dependencies."""
import copy
import json
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
audit = runpy.run_path(str(ROOT / 'scripts/audit_visible_jp.py'))
codec = runpy.run_path(str(ROOT / 'scripts/encrypt_img.py'))


def command(code, parameters=(), indent=0):
    return {'code': code, 'indent': indent, 'parameters': list(parameters)}


def choice(labels, indent=0):
    return ([command(102, [labels, -1, 0, 2, 0], indent)] +
            [command(402, [i, label], indent) for i, label in enumerate(labels)] +
            [command(404, [], indent)])


class AuditTests(unittest.TestCase):
    def rows(self, value):
        au = audit['Audit']()
        au.walk_events(value, copy.deepcopy(value), '$', 'fixture.json')
        return au

    def test_speaker_only_is_visible(self):
        rows = self.rows(command(101, ['顔画像', 0, 0, 2, '話者'])).rows
        self.assertEqual([r['visible'] for r in rows], [False, True])

    def test_nested_plugin_arguments_need_consumer_review(self):
        rows = self.rows(command(357, ['名前', '方法', '説明', {'rows': [{'text': '日本語'}]}])).rows
        self.assertEqual([r['visible'] for r in rows], [False, False, False, None])
        self.assertEqual(rows[-1]['path'], '$["parameters"][3]["rows"][0]["text"]')

    def test_json_encoded_arguments_with_unicode_escapes(self):
        encoded = json.dumps({'text': '日本語', 'nested': json.dumps(['説明'])})
        rows = self.rows(command(357, ['Plugin', 'set', '', encoded])).rows
        self.assertEqual(len(rows), 2)
        self.assertTrue(all('::<json>' in r['path'] for r in rows))
        self.assertTrue(all(r['visible'] is None for r in rows))

    def test_native_display_json_literal_is_not_unwrapped(self):
        text = json.dumps(['日本語'], ensure_ascii=False)
        rows = self.rows(command(401, [text])).rows
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['text'], text)
        self.assertNotIn('::<json>', rows[0]['path'])

    def test_changed_kana_is_still_recorded(self):
        au = audit['Audit']()
        au.walk_events(command(401, ['テスト!']), command(401, ['テスト']), '$', 'fixture')
        self.assertEqual(au.rows[0]['status'], 'changed')
        self.assertTrue(au.rows[0]['has_kana'])

    def test_kanji_and_halfwidth_kana_candidates(self):
        rows = self.rows([command(401, ['経験']), command(401, ['ﾃｽﾄ'])]).rows
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[0]['has_kana'])
        self.assertTrue(rows[1]['has_kana'])

    def test_system_terms_lists_and_editor_names(self):
        data = {'terms': {'messages': {'save': '保存'}}, 'skillTypes': ['', '魔法'],
                'switches': ['', 'スイッチ'], 'variables': ['', '変数']}
        au = audit['Audit']()
        au.walk_db(data, copy.deepcopy(data), 'System.json', 'System')
        by_path = {r['path']: r for r in au.rows}
        self.assertTrue(by_path['$["terms"]["messages"]["save"]']['visible'])
        self.assertTrue(by_path['$["skillTypes"][1]']['visible'])
        self.assertFalse(by_path['$["switches"][1]']['visible'])

    def test_common_and_troop_event_text_not_dropped_or_duplicated(self):
        for db, value in [('CommonEvents', [None, {'name': '名前', 'list': [command(401, ['会話'])]}]),
                          ('Troops', [None, {'name': '名前', 'pages': [{'list': [command(401, ['会話'])]}]}])]:
            with self.subTest(db=db):
                au = audit['Audit']()
                au.walk_events(value, copy.deepcopy(value), '$', db + '.json')
                au.walk_db(value, copy.deepcopy(value), db + '.json', db)
                self.assertEqual(sum(r['text'] == '会話' for r in au.rows), 1)
                self.assertFalse(next(r for r in au.rows if r['text'] == '名前')['visible'])

    def test_custom_container_text_is_not_discarded(self):
        value = {'pages': [{'title': '案内'}]}
        au = audit['Audit']()
        au.walk_db(value, copy.deepcopy(value), 'Custom.json', 'Custom')
        self.assertEqual(au.rows[0]['text'], '案内')
        self.assertIsNone(au.rows[0]['visible'])

    def test_editor_657_is_not_a_native_display_field(self):
        self.assertFalse(self.rows(command(657, ['テキスト = 案内'])).rows[0]['visible'])

    def test_consecutive_and_nested_choices(self):
        events = choice(['A', 'B']) + choice(['C'])
        self.assertEqual(self.rows(events).errors, [])
        outer = choice(['外側'])
        outer[2:2] = choice(['内側'], 1)
        self.assertEqual(self.rows(outer).errors, [])

    def test_choice_label_swap_duplicate_and_bad_index_fail(self):
        for kind in ('swap', 'duplicate', 'string-index', 'missing'):
            events = choice(['A', 'B'])
            if kind == 'swap':
                events[1]['parameters'][1] = 'B'
            elif kind == 'duplicate':
                events[2]['parameters'][0] = 0
            elif kind == 'string-index':
                events[1]['parameters'][0] = 'A'
            else:
                del events[2]
            with self.subTest(kind=kind):
                self.assertTrue(self.rows(events).errors)

    def test_orphan_branch_fails(self):
        self.assertTrue(self.rows([command(402, [0, 'A'])]).errors)

    def test_structure_catches_pollution_and_nontext_changes(self):
        au = audit['Audit']()
        au.structure({'code': 401, 'parameters': ['中'], '0': 'bad'},
                     {'code': 401, 'parameters': ['日']}, '$')
        au.structure([1], [2], '$')
        self.assertEqual(len(au.errors), 2)

    def test_encoded_shape_changes_fail(self):
        au = audit['Audit']()
        au.walk_plugin(json.dumps({'text': '中文', 'extra': 1}), json.dumps({'text': '日本語'}), '$', 'Plugin')
        self.assertTrue(au.errors)

    def test_plugins_parser_ignores_brackets_inside_strings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'plugins.js'
            value = [{'name': 'P', 'status': True, 'parameters': {'text': '] [ テスト'}}]
            path.write_text('var $plugins =\n' + json.dumps(value) + ';', encoding='utf-8')
            self.assertEqual(audit['load_plugins'](path), value)

    def test_cli_complete_inventory_and_failure_status(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            cur, bak = folder / 'cur', folder / 'bak'
            cur.mkdir(); bak.mkdir()
            original = [None, {'name': '名前', 'list': [command(401, ['テスト'])]}]
            changed = copy.deepcopy(original)
            changed[1]['list'][0]['parameters'][0] += '!'
            (cur / 'CommonEvents.json').write_text(json.dumps(changed), encoding='utf-8')
            (bak / 'CommonEvents.json').write_text(json.dumps(original), encoding='utf-8')
            out, inventory = folder / 'out.txt', folder / 'inventory.json'
            args = ['--current', str(cur), '--backup', str(bak), '--out', str(out), '--json-out', str(inventory)]
            self.assertEqual(audit['main'](args), 0)
            data = json.loads(inventory.read_text(encoding='utf-8'))
            self.assertTrue(data['complete'])
            self.assertTrue(any(r['status'] == 'changed' and r['has_kana'] for r in data['rows']))
            (cur / 'CommonEvents.json').write_text('{broken', encoding='utf-8')
            self.assertEqual(audit['main'](args), 1)
            self.assertFalse(json.loads(inventory.read_text(encoding='utf-8'))['complete'])

    def test_missing_file_and_empty_directory_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            cur, bak = folder / 'cur', folder / 'bak'
            cur.mkdir(); bak.mkdir()
            args = ['--current', str(cur), '--backup', str(bak), '--out', str(folder / 'out')]
            self.assertEqual(audit['main'](args), 1)
            (bak / 'Actors.json').write_text('[]', encoding='utf-8')
            self.assertEqual(audit['main'](args), 1)


class JapaneseHelperTests(unittest.TestCase):
    def test_ruby_backslash_and_escape_variants(self):
        helper = runpy.run_path(str(ROOT / 'scripts/lang/ja.py'))
        for prefix in ('\\', '\x1b'):
            text = prefix + 'RB[愛,あい]'
            with self.subTest(prefix=repr(prefix)):
                self.assertEqual(len(list(helper['ruby_spans'](text))), 1)
                self.assertEqual(helper['rewrite_ruby'](text, {'愛': '爱'}), prefix + 'RB[爱,あい]')
        self.assertEqual(helper['rewrite_ruby']('ordinary text', {}), 'ordinary text')


class CodecTests(unittest.TestCase):
    KEY = '00112233445566778899aabbccddeeff'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.src, self.enc, self.out = [self.folder / name for name in ('src', 'enc', 'out')]
        self.payload = codec['PNG_MAGIC'] + bytes(range(24))
        self.src.write_bytes(self.payload)
        self.out.write_bytes(b'existing destination')

    def test_known_engine_container_and_roundtrip(self):
        codec['encrypt'](self.src, self.enc, self.KEY)
        expected = codec['HEADER'] + bytes(a ^ b for a, b in zip(self.payload[:16], bytes.fromhex(self.KEY))) + self.payload[16:]
        self.assertEqual(self.enc.read_bytes(), expected)
        codec['decrypt'](self.enc, self.out, self.KEY)
        self.assertEqual(self.out.read_bytes(), self.payload)

    def test_wrong_key_preserves_destination(self):
        codec['encrypt'](self.src, self.enc, self.KEY)
        with self.assertRaises(ValueError):
            codec['decrypt'](self.enc, self.out, 'ffeeddccbbaa99887766554433221100')
        self.assertEqual(self.out.read_bytes(), b'existing destination')

    def test_invalid_input_key_and_truncation_preserve_destination(self):
        for data, key, mode in [(b'not a PNG file!', self.KEY, 'encrypt'),
                                (self.payload, 'zz' * 16, 'encrypt'),
                                (self.payload, '00 11' * 8, 'encrypt'),
                                (codec['HEADER'] + b'123', self.KEY, 'decrypt'),
                                (b'bad header' + self.payload, self.KEY, 'decrypt')]:
            with self.subTest(mode=mode, key=key):
                self.src.write_bytes(data)
                with self.assertRaises(ValueError):
                    codec[mode](self.src, self.out, key)
                self.assertEqual(self.out.read_bytes(), b'existing destination')

    def test_ogg_roundtrip_requires_audio_flag(self):
        payload = b'OggS' + bytes(range(28))
        self.src.write_bytes(payload)
        with self.assertRaises(ValueError):
            codec['encrypt'](self.src, self.enc, self.KEY)
        codec['encrypt'](self.src, self.enc, self.KEY, audio=True)
        codec['decrypt'](self.enc, self.out, self.KEY, audio=True)
        self.assertEqual(self.out.read_bytes(), payload)

    def test_replace_failure_preserves_destination_and_cleans_temp(self):
        with patch('os.replace', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                codec['encrypt'](self.src, self.out, self.KEY)
        self.assertEqual(self.out.read_bytes(), b'existing destination')
        self.assertEqual(list(self.folder.glob('*.tmp')), [])

    def test_in_place_roundtrip(self):
        codec['encrypt'](self.src, self.src, self.KEY)
        codec['decrypt'](self.src, self.src, self.KEY)
        self.assertEqual(self.src.read_bytes(), self.payload)

    def test_cli_missing_destination_is_usage_error(self):
        with self.assertRaises(SystemExit) as result:
            codec['main'](['encrypt', str(self.src), '--key', self.KEY])
        self.assertEqual(result.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
