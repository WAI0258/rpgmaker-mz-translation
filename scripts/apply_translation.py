#!/usr/bin/env python3
"""Plan/apply reviewed JSON leaf patches into a NEW working data directory.

No --write means validation only. Never overwrite live data or a backup. The
manifest binds the complete source snapshot and each edited file. All patches
are validated before staging; a verified directory is published by one rename.
This does not promise a power-loss-proof filesystem transaction.
"""
import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path

from json_safety import (Document, json_files, load_manifest, locate, selector_chain,
                         snapshot_hash, validate_change, resolve)
from verify_untouched import verify_directories, verify_document


def _encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')


def patch_document(document, changes, filename):
    """Group edits by outer token; apply child edits from the same original."""
    groups = {}
    for change in changes:
        chain = selector_chain(change['path'])
        path, _ = resolve(document.value, chain[0])
        groups.setdefault(path, []).append((chain, change))
    replacements = []
    for path, operations in groups.items():
        direct = [(chain, change) for chain, change in operations if len(chain) == 1]
        nested = [(chain, change) for chain, change in operations if len(chain) > 1]
        if direct and nested or len(direct) > 1:
            raise ValueError(f'{filename}: conflicting patch selectors')
        if direct:
            new_token = _encode(direct[0][1]['new'])
        else:
            original = locate(document, operations[0][0])[0][2]
            inner = Document(original.encode('utf-8'))
            child_changes = [{**change, 'path': list(chain[1:])} for chain, change in nested]
            new_token = _encode(patch_document(inner, child_changes, filename).decode('utf-8'))
        replacements.append((*document.spans[path], new_token))
    replacements.sort(reverse=True)
    raw, previous = document.raw, len(document.raw)
    for start, end, token in replacements:
        if end > previous:
            raise ValueError('overlapping JSON value spans')
        raw = raw[:start] + token + raw[end:]
        previous = start
    return raw


def prepare(source, manifest):
    files = json_files(source)
    originals = {name: p.read_bytes() for name, p in files.items()}
    data, entries = load_manifest(manifest)
    if snapshot_hash(originals) != data['source_sha256']:
        raise ValueError('source snapshot does not match manifest source_sha256')
    if entries.keys() - originals.keys():
        raise ValueError('manifest references files outside source snapshot')
    outputs = {}
    for name, raw in originals.items():
        document = Document(raw)
        entry = entries.get(name)
        changes = entry['changes'] if entry else []
        if entry and hashlib.sha256(raw).hexdigest() != entry['sha256']:
            raise ValueError(f'{name}: source file digest mismatch')
        for change in changes:
            validate_change(name, document, change)
        result = patch_document(document, changes, name)
        current = document if result == raw else Document(result)
        errors, _ = verify_document(current, document, name, changes)
        if errors:
            raise ValueError('\n'.join(errors))
        outputs[name] = result
    return originals, outputs


def apply(source, output, manifest, write=False):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or source in output.parents or output in source.parents:
        raise ValueError('output must be separate from the source tree')
    if output.exists():
        raise ValueError('output must be a new directory; never overwrite existing data')
    originals, outputs = prepare(source, manifest)
    changed = sum(originals[name] != raw for name, raw in outputs.items())
    if not write:
        return {'mode': 'dry-run', 'files': len(outputs), 'changed_files': changed}
    if not output.parent.is_dir():
        raise ValueError('output parent must already exist')
    staging = Path(tempfile.mkdtemp(prefix='.translation-', dir=output.parent)).resolve()
    try:
        for name, raw in outputs.items():
            with (staging / name).open('wb') as file:
                file.write(raw)
                file.flush()
                os.fsync(file.fileno())
        result = verify_directories(staging, source, manifest)
        if not result['complete']:
            raise ValueError('\n'.join(result['errors']))
        latest = {name: p.read_bytes() for name, p in json_files(source).items()}
        if latest != originals:
            raise ValueError('source changed during preparation; output not installed')
        if output.exists():
            raise ValueError('output appeared during preparation; refusing overwrite')
        os.rename(staging, output)
        return {'mode': 'written', 'files': len(outputs), 'changed_files': changed,
                'protected_fields': result['protected_fields'], 'output': str(output)}
    finally:
        if staging.exists():
            if staging.parent != output.parent or not staging.name.startswith('.translation-'):
                raise RuntimeError('unsafe staging cleanup path')
            shutil.rmtree(staging)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', help='workspace.json; use task paths and defaults')
    parser.add_argument('--source')
    parser.add_argument('--manifest')
    parser.add_argument('--output')
    parser.add_argument('--describe', action='store_true', help='Print source snapshot/file digests without writing')
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args(argv)
    if args.task:
        from translation_workspace import configure_task
        try:
            configure_task(args, 'apply')
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            parser.error(str(exc))
    if not args.source:
        parser.error('provide --task or --source')
    if args.describe and (args.manifest or args.output or args.write):
        parser.error('--describe is read-only; do not combine with patch options')
    if not args.describe and (not args.manifest or not args.output):
        parser.error('patching needs --manifest and --output')
    try:
        if args.describe:
            raw = {name: p.read_bytes() for name, p in json_files(args.source).items()}
            for value in raw.values():
                Document(value)
            result = {'schema_version': 1, 'source_sha256': snapshot_hash(raw),
                      'files': [{'file': name, 'sha256': hashlib.sha256(value).hexdigest()}
                                for name, value in sorted(raw.items())]}
        else:
            result = apply(args.source, args.output, args.manifest, args.write)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
        print(f'ERROR: {exc}')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
