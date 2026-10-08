"""Path/byte integrity regressions. Synthetic inputs only; no game assets."""
import contextlib
import copy
import hashlib
import io
import json
import random
import runpy
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
from json_safety import Document, audit_selector, pointer, resolve, snapshot_hash, strict_loads
from apply_translation import apply, main as writer_main, patch_document
from verify_untouched import verify_directories, verify_document, main as verifier_main
from audit_visible_jp import main as audit_main


def encoded(value):
    return json.dumps(value, ensure_ascii=False).encode('utf-8')


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.source.mkdir()
        self.output = self.root / 'output'
        self.manifest = self.root / 'patch.json'

    def setup_data(self, value, filename='Armors.json', raw=None, changes=None):
        raw = encoded(value) if raw is None else raw
        (self.source / filename).write_bytes(raw)
        self.filename = filename
        self.save_manifest(changes or [], filename)
        return raw

    def save_manifest(self, changes, filename=None):
        filename = filename or self.filename
        originals = {p.name: p.read_bytes() for p in self.source.glob('*.json')}
        self.plan = {'schema_version': 1, 'source_sha256': snapshot_hash(originals),
                     'files': [{'file': filename, 'sha256': hashlib.sha256(originals[filename]).hexdigest(),
                                'changes': changes}] if changes else []}
        self.manifest.write_bytes(encoded(self.plan))

    def write(self):
        return apply(self.source, self.output, self.manifest, write=True)

    def verify(self):
        return verify_directories(self.output, self.source, self.manifest)

    def quiet(self, fn, args):
        with contextlib.redirect_stdout(io.StringIO()):
            return fn(args)


class WriterTests(Fixture):
    def test_same_value_in_name_note_resource_and_other_record(self):
        value = [None, {'id': 1, 'name': 'shared', 'note': 'shared', 'faceName': 'shared'},
                 {'id': 2, 'name': 'shared', 'note': ''}]
        original = self.setup_data(value, changes=[{'path': '/1/name', 'old': 'shared', 'new': 'translated'}])
        self.assertEqual(apply(self.source, self.output, self.manifest)['mode'], 'dry-run')
        self.assertFalse(self.output.exists())
        self.write()
        current = json.loads((self.output / self.filename).read_bytes())
        self.assertEqual(current[1]['name'], 'translated')
        self.assertEqual(current[1]['note'], 'shared')
        self.assertEqual(current[1]['faceName'], 'shared')
        self.assertEqual(current[2]['name'], 'shared')
        self.assertEqual((self.source / self.filename).read_bytes(), original)
        self.assertTrue(self.verify()['complete'])

    def test_no_substring_or_cascading_replacements(self):
        self.setup_data([None, {'name': 'A', 'description': 'B', 'note': 'AB'}], changes=[
            {'path': '/1/name', 'old': 'A', 'new': 'B'},
            {'path': '/1/description', 'old': 'B', 'new': 'C'}])
        self.write()
        data = json.loads((self.output / self.filename).read_bytes())[1]
        self.assertEqual(data, {'name': 'B', 'description': 'C', 'note': 'AB'})

    def test_preserves_bom_crlf_key_order_spacing_and_trailing_newline(self):
        raw = b'\xef\xbb\xbf[ null,\r\n {"note":"\\u65e5", "name" : ' + encoded('old\\n') + b', "traits":[]} ]\r\n'
        self.setup_data(None, raw=raw, changes=[{'path': '/1/name', 'old': 'old\\n', 'new': '译"文\\n'}])
        self.write()
        expected = raw.replace(encoded('old\\n'), encoded('译"文\\n'))
        self.assertEqual((self.output / self.filename).read_bytes(), expected)
        self.assertTrue(self.verify()['complete'])

    def test_multiple_nested_decoding_boundaries_and_sibling_edits(self):
        payload = json.dumps({'text': 'old', 'other': 'old', 'nested': json.dumps({'line': 'deep', 'note': '<key:1>'})})
        value = [{'code': 357, 'indent': 0, 'parameters': ['Plugin', 'set', '', payload]}]
        changes = [
            {'path': ['/0/parameters/3', '/text'], 'old': 'old', 'new': 'new', 'review': 'Plugin.set draws args.text'},
            {'path': ['/0/parameters/3', '/nested', '/line'], 'old': 'deep', 'new': 'translated', 'review': 'Plugin draws nested.line'}]
        self.setup_data(value, 'CommonEvents.json', changes=changes)
        self.write()
        result = json.loads((self.output / self.filename).read_bytes())
        inner = json.loads(result[0]['parameters'][3])
        self.assertEqual(inner['text'], 'new')
        self.assertEqual(inner['other'], 'old')
        self.assertEqual(json.loads(inner['nested'])['note'], '<key:1>')
        self.assertTrue(self.verify()['complete'])

    def test_unknown_field_requires_review_and_opaque_blob_is_not_a_leaf_permission(self):
        value = {'text': 'hello', 'blob': '{"name":"old"}'}
        self.setup_data(value, 'Custom.json', changes=[{'path': '/text', 'old': 'hello', 'new': 'world'}])
        with self.assertRaisesRegex(ValueError, 'review'):
            self.write()
        self.save_manifest([{'path': '/blob', 'old': value['blob'], 'new': '{"name":"new"}', 'review': 'draws name'}])
        with self.assertRaisesRegex(ValueError, 'decoding boundary'):
            self.write()

    def test_literal_json_in_native_dialogue_is_not_a_decoding_boundary(self):
        old, new = '{"note":"literal"}', '{"note":"字面文本"}'
        self.setup_data([{'code': 401, 'indent': 0, 'parameters': [old]}], 'CommonEvents.json',
                        changes=[{'path': '/0/parameters/0', 'old': old, 'new': new}])
        self.write()
        self.assertTrue(self.verify()['complete'])

    def test_note_meta_resources_ids_and_event_structure_cannot_be_approved(self):
        for path, value, change in [
            ('/note', {'note': 'a'}, ('a', 'b')),
            ('/meta/key', {'meta': {'key': 'a'}}, ('a', 'b')),
            ('/faceName', {'faceName': 'a'}, ('a', 'b')),
            ('/encryptionKey', {'encryptionKey': 'a'}, ('a', 'b')),
            ('/id', {'id': 1}, (1, 2)),
            ('/code', {'code': 401, 'indent': 0, 'parameters': ['x']}, (401, 355)),
            ('/parameters/1', {'code': 231, 'indent': 0, 'parameters': [1, 'a']}, ('a', 'b')),
            ('/parameters/0', {'code': 357, 'indent': 0, 'parameters': ['a', 'cmd', 'label', {}]}, ('a', 'b')),
        ]:
            with self.subTest(path=path):
                self.setup_data(value, 'Custom.json', changes=[{'path': path, 'old': change[0], 'new': change[1],
                                                               'kind': 'config', 'review': 'explicit but unsafe'}])
                with self.assertRaisesRegex(ValueError, 'frozen'):
                    self.write()
                self.assertFalse(self.output.exists())

    def test_config_is_explicit_typed_and_checked_by_main_audit(self):
        value = {'advanced': {'fontSize': 26, 'mainFontFilename': 'old.woff'}}
        self.setup_data(value, 'System.json', changes=[
            {'path': '/advanced/fontSize', 'old': 26, 'new': 28, 'kind': 'config', 'review': 'approved font size'},
            {'path': '/advanced/mainFontFilename', 'old': 'old.woff', 'new': 'new.woff', 'kind': 'config', 'review': 'approved font'}])
        self.write()
        self.assertTrue(self.verify()['complete'])
        self.assertEqual(self.quiet(audit_main, ['--current', str(self.output), '--backup', str(self.source),
                                              '--manifest', str(self.manifest), '--out', str(self.root / 'audit')]), 0)

    def test_stale_old_value_snapshot_and_duplicate_selector_abort_before_output(self):
        self.setup_data([None, {'name': 'old', 'note': ''}], changes=[{'path': '/1/name', 'old': 'stale', 'new': 'new'}])
        with self.assertRaisesRegex(ValueError, 'old value'):
            self.write()
        self.save_manifest([{'path': '/1/name', 'old': 'old', 'new': 'new'}] * 2)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.write()
        self.save_manifest([{'path': '/1/name', 'old': 'old', 'new': 'new'}])
        (self.source / self.filename).write_bytes(encoded([None, {'name': 'changed', 'note': ''}]))
        with self.assertRaisesRegex(ValueError, 'snapshot'):
            self.write()
        self.assertFalse(self.output.exists())

    def test_preflight_failure_in_later_file_does_not_publish_earlier_patch(self):
        self.setup_data([None, {'name': 'old'}], changes=[{'path': '/1/name', 'old': 'old', 'new': 'new'}])
        (self.source / 'Z.json').write_bytes(b'{"x":1,"x":2}')
        self.save_manifest(self.plan['files'][0]['changes'])
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.write()
        self.assertFalse(self.output.exists())

    def test_existing_or_source_overlapping_output_is_rejected(self):
        self.setup_data([None, {'name': 'old'}])
        self.output.mkdir()
        (self.output / 'keep').write_text('do not touch')
        with self.assertRaisesRegex(ValueError, 'new directory'):
            self.write()
        self.assertEqual((self.output / 'keep').read_text(), 'do not touch')
        with self.assertRaisesRegex(ValueError, 'separate'):
            apply(self.source, self.source / 'nested', self.manifest, True)

    def test_publish_failure_cleans_staging_and_leaves_source(self):
        raw = self.setup_data([None, {'name': 'old'}], changes=[{'path': '/1/name', 'old': 'old', 'new': 'new'}])
        with patch('apply_translation.os.rename', side_effect=OSError('injected publish failure')):
            with self.assertRaises(OSError):
                self.write()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.translation-*')), [])
        self.assertEqual((self.source / self.filename).read_bytes(), raw)

    def test_control_codes_placeholders_and_ruby_readings_are_protected(self):
        old = r'\C[2]Hello %1 \V[3]'
        for new in [r'Hello %1 \V[3]', r'\C[2]Hello %2 \V[3]', r'\C[2]Hello %1 \V[4]']:
            self.setup_data([None, {'name': old}], changes=[{'path': '/1/name', 'old': old, 'new': new}])
            with self.assertRaisesRegex(ValueError, 'control codes'):
                self.write()
        old = r'\RB[陰,かげ]'
        self.setup_data([None, {'name': old}], changes=[{'path': '/1/name', 'old': old, 'new': r'\RB[阴,other]'}])
        with self.assertRaisesRegex(ValueError, 'control codes'):
            self.write()
        self.save_manifest([{'path': '/1/name', 'old': old, 'new': r'\RB[阴,かげ]'}])
        self.write()
        self.assertTrue(self.verify()['complete'])

    def test_escaped_literal_cannot_become_executable_control_code(self):
        self.setup_data([None, {'name': r'\\V[1]'}],
                        changes=[{'path': '/1/name', 'old': r'\\V[1]', 'new': r'\V[1]'}])
        with self.assertRaisesRegex(ValueError, 'control codes'):
            self.write()
        self.assertFalse(self.output.exists())

    def test_unknown_nested_note_cannot_be_approved_and_conflicting_decode_paths_fail(self):
        payload = '{"text":"old","note":"<tag:1>"}'
        value = [{'code': 357, 'indent': 0, 'parameters': ['Plugin', 'set', '', payload]}]
        self.setup_data(value, 'CommonEvents.json', changes=[{'path': ['/0/parameters/3', '/note'],
            'old': '<tag:1>', 'new': '<tag:2>', 'review': 'not sufficient'}])
        with self.assertRaisesRegex(ValueError, 'frozen'):
            self.write()
        self.save_manifest([
            {'path': '/0/parameters/3', 'old': payload, 'new': '{}', 'review': 'not sufficient'},
            {'path': ['/0/parameters/3', '/text'], 'old': 'old', 'new': 'new', 'review': 'draws text'}])
        with self.assertRaises(ValueError):
            self.write()
        self.assertFalse(self.output.exists())

    def test_manifest_cannot_reference_outside_data_and_wrong_file_digest_fails(self):
        self.setup_data([None, {'name': 'old'}], changes=[{'path': '/1/name', 'old': 'old', 'new': 'new'}])
        for filename in ('../Armors.json', 'C:Armors.json', 'dir/Armors.json', 'dir\\Armors.json'):
            self.plan['files'][0]['file'] = filename
            self.manifest.write_bytes(encoded(self.plan))
            with self.assertRaises(ValueError):
                self.write()
        self.plan['files'][0]['file'] = self.filename
        self.plan['files'][0]['sha256'] = '0' * 64
        self.manifest.write_bytes(encoded(self.plan))
        with self.assertRaisesRegex(ValueError, 'digest'):
            self.write()
        self.assertFalse(self.output.exists())

    def test_changed_source_during_staging_is_not_published(self):
        self.setup_data([None, {'name': 'old'}], changes=[{'path': '/1/name', 'old': 'old', 'new': 'new'}])
        def simulate_change(*args):
            (self.source / self.filename).write_bytes(encoded([None, {'name': 'concurrent'}]))
            return {'complete': True, 'protected_fields': 0}
        with patch('apply_translation.verify_directories', side_effect=simulate_change):
            with self.assertRaisesRegex(ValueError, 'source changed'):
                self.write()
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.translation-*')), [])

    def test_choice_labels_must_be_patched_together(self):
        value = [{'code': 102, 'indent': 0, 'parameters': [['Yes']]},
                 {'code': 402, 'indent': 0, 'parameters': [0, 'Yes']},
                 {'code': 404, 'indent': 0, 'parameters': []}]
        change = {'path': '/0/parameters/0/0', 'old': 'Yes', 'new': '是'}
        self.setup_data(value, 'CommonEvents.json', changes=[change])
        with self.assertRaisesRegex(ValueError, 'choice label'):
            self.write()
        self.save_manifest([change, {'path': '/1/parameters/1', 'old': 'Yes', 'new': '是'}])
        self.write()
        self.assertTrue(self.verify()['complete'])

    def test_cli_describe_and_default_dry_run_are_read_only(self):
        self.setup_data([None, {'name': 'old'}], changes=[{'path': '/1/name', 'old': 'old', 'new': 'new'}])
        self.assertEqual(self.quiet(writer_main, ['--source', str(self.source), '--describe']), 0)
        self.assertEqual(self.quiet(writer_main, ['--source', str(self.source), '--manifest', str(self.manifest),
                                               '--output', str(self.output)]), 0)
        self.assertFalse(self.output.exists())


class IntegrityTests(Fixture):
    def test_unapproved_string_change_is_rejected_even_if_displayed(self):
        self.setup_data([None, {'name': 'old', 'description': 'keep', 'note': ''}],
                        changes=[{'path': '/1/name', 'old': 'old', 'new': 'new'}])
        self.write()
        current = json.loads((self.output / self.filename).read_bytes())
        current[1]['description'] = 'unexpected'
        (self.output / self.filename).write_bytes(encoded(current))
        self.assertFalse(self.verify()['complete'])

    def test_previously_invisible_corruptions_all_fail(self):
        base = {'note': '', 'meta': {}, 'id': 103, 'flag': True,
                'events': [{'code': 401, 'indent': 0, 'parameters': ['text']}], 'nullable': None}
        self.setup_data(base, 'Custom.json')
        self.output.mkdir()
        for label, mutate in [
            ('code', lambda v: v['events'][0].update(code=355)),
            ('indent', lambda v: v['events'][0].update(indent=99)),
            ('add meta value', lambda v: v['meta'].update(new='bad')),
            ('remove meta', lambda v: v.pop('meta')),
            ('id string', lambda v: v.update(id='103')),
            ('bool int', lambda v: v.update(flag=1)),
            ('remove null', lambda v: v.pop('nullable')),
            ('add field', lambda v: v.update(extra='bad')),
            ('note ASCII change', lambda v: v.update(note='<wrong:10>')),
        ]:
            with self.subTest(label=label):
                value = copy.deepcopy(base)
                mutate(value)
                (self.output / self.filename).write_bytes(encoded(value))
                self.assertFalse(self.verify()['complete'])

    def test_equivalent_note_escape_and_unrelated_whitespace_are_not_byte_identical(self):
        self.setup_data(None, 'Custom.json', raw=b'{"note":"\\u65e5","text":"a"}')
        self.output.mkdir()
        for raw in [encoded({'note': '日', 'text': 'a'}), b'{ "note":"\\u65e5","text":"a"}']:
            (self.output / self.filename).write_bytes(raw)
            self.assertFalse(self.verify()['complete'])

    def test_nested_payload_cannot_hide_other_leaf_or_metadata_changes(self):
        payload = '{"text":"old","resource":"keep","note":"<tag:1>"}'
        value = [{'code': 357, 'indent': 0, 'parameters': ['Plugin', 'set', '', payload]}]
        self.setup_data(value, 'CommonEvents.json', changes=[{'path': ['/0/parameters/3', '/text'], 'old': 'old',
                                                            'new': 'new', 'review': 'Plugin draws text'}])
        self.write()
        for key, new in [('resource', 'wrong'), ('note', '<tag:2>')]:
            current = json.loads((self.output / self.filename).read_bytes())
            inner = json.loads(current[0]['parameters'][3])
            inner[key] = new
            current[0]['parameters'][3] = json.dumps(inner)
            (self.output / self.filename).write_bytes(encoded(current))
            self.assertFalse(self.verify()['complete'])

    def test_missing_application_file_sets_and_self_comparison_fail(self):
        self.setup_data([None, {'name': 'old'}], changes=[{'path': '/1/name', 'old': 'old', 'new': 'new'}])
        self.output.mkdir()
        (self.output / self.filename).write_bytes((self.source / self.filename).read_bytes())
        self.assertFalse(self.verify()['complete'])
        (self.output / 'Extra.json').write_bytes(b'{}')
        self.assertFalse(self.verify()['complete'])
        with self.assertRaisesRegex(ValueError, 'independent'):
            verify_directories(self.source, self.source, self.manifest)

    def test_legitimate_zero_protected_fields_pass_but_empty_directories_fail(self):
        self.setup_data({'terms': {'messages': {'save': 'Save'}}}, 'System.json',
                        changes=[{'path': '/terms/messages/save', 'old': 'Save', 'new': '保存'}])
        self.write()
        result = self.verify()
        self.assertTrue(result['complete'])
        self.assertEqual(result['protected_fields'], 0)
        empty = self.root / 'empty'
        empty.mkdir()
        with self.assertRaisesRegex(ValueError, 'no data'):
            verify_directories(empty, self.source)

    def test_no_manifest_requires_exact_copy_and_cli_failure_is_nonzero(self):
        self.setup_data([None, {'name': 'old', 'note': ''}])
        self.write()
        self.assertTrue(verify_directories(self.output, self.source)['complete'])
        (self.output / self.filename).write_bytes(encoded([None, {'name': 'new', 'note': ''}]))
        self.assertFalse(verify_directories(self.output, self.source)['complete'])
        self.assertEqual(self.quiet(verifier_main, ['--current', str(self.output), '--backup', str(self.source)]), 1)

    def test_reports_cannot_overwrite_inputs(self):
        original = self.setup_data({'note': '', 'name': 'original'}, 'Custom.json')
        self.write()
        for fn in (verifier_main, audit_main):
            args = ['--current', str(self.output), '--backup', str(self.source),
                    '--json-out', str(self.source / self.filename)]
            if fn is audit_main:
                args += ['--out', str(self.root / 'audit')]
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.quiet(fn, args)
        self.assertEqual((self.source / self.filename).read_bytes(), original)

    def test_main_audit_rejects_ascii_note_change_without_kana_or_manifest(self):
        self.setup_data([None, {'name': 'old', 'note': '<MPReg:10>'}])
        self.output.mkdir()
        (self.output / self.filename).write_bytes(encoded([None, {'name': 'new', 'note': '<MPReg:20>'}]))
        args = ['--current', str(self.output), '--backup', str(self.source), '--out', str(self.root / 'audit'),
                '--json-out', str(self.root / 'inventory.json')]
        self.assertEqual(self.quiet(audit_main, args), 1)
        self.assertFalse(json.loads((self.root / 'inventory.json').read_text())['complete'])


class ParserTests(unittest.TestCase):
    def test_strict_json_rejects_ambiguities_and_nonstandard_values(self):
        for value in [b'{"x":1,"x":2}', b'{"x":1,"\\u0078":2}', b'NaN', b'Infinity', b'1e999',
                      b'01', b'{} junk', b'{"x":1,}', b'"\xff"', b'[1,]', b'"\\q"']:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    Document(value)

    def test_pointer_escapes_indices_and_audit_boundary_in_a_key(self):
        data = {'a/b': {'~key': ['x']}, '::<json>': 'literal', '': 'empty'}
        self.assertEqual(resolve(data, '/a~1b/~0key/0')[1], 'x')
        self.assertEqual(resolve(data, '/')[1], 'empty')
        self.assertEqual(audit_selector('$["::<json>"]'), ['/::<json>'])
        self.assertEqual(audit_selector('$["a/b"]["~key"][0]::<json>["line"]'), ['/a~1b/~0key/0', '/line'])
        for path in ['/a~2b', '/a~1b/~0key/00', '/a~1b/~0key/-', 'not-a-pointer']:
            with self.assertRaises(ValueError):
                resolve(data, path)

    def test_span_parser_matches_standard_json_on_varied_unicode_and_scalars(self):
        rng = random.Random(17)
        values = [None, True, False, 0, -3, 1.25, '日"\\\n', '😀', [], {}]
        for _ in range(50):
            data = {f'key/{i}~': rng.choice(values) for i in range(rng.randrange(1, 8))}
            raw = json.dumps(data, ensure_ascii=bool(rng.randrange(2)), indent=2).encode('utf-8')
            document = Document(raw)
            self.assertEqual(document.value, json.loads(raw))
            for path in document.spans:
                self.assertEqual(json.loads(document.token(path)), resolve(document.value, pointer(path))[1])


if __name__ == '__main__':
    unittest.main()
