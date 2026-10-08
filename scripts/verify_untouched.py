#!/usr/bin/env python3
"""Verify every data JSON difference against a path-scoped patch manifest.

Without --manifest, require an exact backup copy. This is NOT a translation
completeness check. Parsed diffs and protected raw spans are checked separately
from the writer; safety does not depend on CJK/kana detection.
"""
import argparse
import hashlib
import json
from pathlib import Path

from json_safety import (Document, PROTECTED_KEYS, all_choice_errors, equal,
                         check_report_path, json_files, load_manifest, locate, pointer,
                         selector_chain, snapshot_hash, strict_loads, validate_change, resolve)


def _diff(a, b, path=()):
    if type(a) is not type(b):
        return {path: (b, a)}
    if isinstance(b, dict):
        result = {}
        for key in a.keys() | b.keys():
            if key not in a or key not in b:
                result[path + (key,)] = ('missing key', 'changed keys')
            else:
                result.update(_diff(a[key], b[key], path + (key,)))
        return result
    if isinstance(b, list):
        if len(a) != len(b):
            return {path: ('array length', 'changed length')}
        result = {}
        for i, (x, y) in enumerate(zip(a, b)):
            result.update(_diff(x, y, path + (i,)))
        return result
    return {} if equal(a, b) else {path: (b, a)}


def _skeleton(document, paths):
    """Remove allowed value tokens, retaining every other original byte."""
    spans = sorted(document.spans[path] for path in paths)
    position, chunks = 0, []
    for start, end in spans:
        if start < position:
            raise ValueError('overlapping permitted token spans')
        chunks.append(document.raw[position:start])
        position = end
    chunks.append(document.raw[position:])
    # Lists preserve boundaries, so moving whitespace across a token cannot hide.
    return chunks


def verify_document(current, backup, filename, changes):
    errors, protected_count = [], 0
    if not changes and current.raw == backup.raw:
        # Exact bytes prove no diff; still validate existing choice consistency.
        return ([f'{filename}: {message}' for message in all_choice_errors(current.value)],
                sum(bool(path) and path[-1] in PROTECTED_KEYS for path in backup.spans))
    approvals = {}
    for change in changes:
        validate_change(filename, backup, change)
        chain = selector_chain(change['path'])
        locate(current, chain)  # Fail if a decoder boundary or target disappeared.
        approvals[chain] = change
    used = set()

    def compare(cur_doc, bak_doc, prefix=()):
        nonlocal protected_count
        current_tree = strict_loads(cur_doc.raw.decode('utf-8-sig'))
        backup_tree = strict_loads(bak_doc.raw.decode('utf-8-sig'))
        changes_by_path = _diff(current_tree, backup_tree)
        allowed_paths = set()
        targets = {}
        for chain, change in approvals.items():
            if chain[:len(prefix)] == prefix and len(chain) > len(prefix):
                path, _ = resolve(backup_tree, chain[len(prefix)])
                targets.setdefault(path, []).append((chain, change))
        for path, pair in changes_by_path.items():
            candidates = targets.get(path, [])
            label = f'{filename} {prefix + (pointer(path),)}'
            if not candidates:
                errors.append(f'{label}: unapproved difference')
                continue
            direct = [(chain, change) for chain, change in candidates if len(chain) == len(prefix) + 1]
            nested = [(chain, change) for chain, change in candidates if len(chain) > len(prefix) + 1]
            if direct and nested or len(direct) > 1:
                errors.append(f'{label}: overlapping patch selectors')
                continue
            if direct:
                chain, change = direct[0]
                if not equal(pair[0], change['old']) or not equal(pair[1], change['new']):
                    errors.append(f'{label}: patch values do not match actual difference')
                else:
                    used.add(chain)
                    allowed_paths.add(path)
            else:
                if not isinstance(pair[0], str) or not isinstance(pair[1], str):
                    errors.append(f'{label}: decoding boundary type changed')
                    continue
                compare(Document(pair[1].encode('utf-8')), Document(pair[0].encode('utf-8')),
                        prefix + (pointer(path),))
                allowed_paths.add(path)
        for path in bak_doc.spans.keys() | cur_doc.spans.keys():
            if path and path[-1] in PROTECTED_KEYS:
                protected_count += 1
                if (path not in bak_doc.spans or path not in cur_doc.spans or
                        bak_doc.token(path) != cur_doc.token(path)):
                    errors.append(f'{filename} {prefix + (pointer(path),)}: protected raw token changed')
        try:
            if _skeleton(cur_doc, allowed_paths) != _skeleton(bak_doc, allowed_paths):
                errors.append(f'{filename} {prefix}: bytes outside approved tokens changed')
        except (KeyError, ValueError) as exc:
            errors.append(f'{filename}: {exc}')

    compare(current, backup)
    for chain in approvals.keys() - used:
        errors.append(f'{filename} {chain}: approved change was not applied')
    errors.extend(f'{filename}: {message}' for message in all_choice_errors(current.value))
    return errors, protected_count


def verify_directories(current, backup, manifest=None):
    current, backup = Path(current).resolve(), Path(backup).resolve()
    if current == backup:
        raise ValueError('current and backup must be independent directories')
    cur_files, bak_files = json_files(current), json_files(backup)
    errors = [f'{name}: file set differs' for name in sorted(cur_files.keys() ^ bak_files.keys())]
    raw_backup = {name: p.read_bytes() for name, p in bak_files.items()}
    approved = {}
    if manifest:
        data, approved = load_manifest(manifest)
        if snapshot_hash(raw_backup) != data['source_sha256']:
            raise ValueError('backup snapshot does not match manifest source_sha256')
        for name, entry in approved.items():
            if name not in raw_backup or hashlib.sha256(raw_backup[name]).hexdigest() != entry['sha256']:
                raise ValueError(f'{name}: manifest source file digest mismatch')
    count = 0
    for name in sorted(cur_files.keys() & bak_files.keys()):
        if cur_files[name].samefile(bak_files[name]):
            raise ValueError(f'{name}: current and backup refer to the same file')
        try:
            current_raw = cur_files[name].read_bytes()
            bak = Document(raw_backup[name])
            cur = bak if current_raw == raw_backup[name] else Document(current_raw)
            messages, protected = verify_document(cur, bak, name, approved.get(name, {}).get('changes', []))
            errors.extend(messages)
            count += protected
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            errors.append(f'{name}: {exc}')
    return {'complete': not errors, 'files_compared': len(cur_files.keys() & bak_files.keys()),
            'protected_fields': count, 'manifest_checked': manifest is not None, 'errors': errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', help='workspace.json; use task paths and defaults')
    parser.add_argument('--current')
    parser.add_argument('--backup')
    parser.add_argument('--manifest')
    parser.add_argument('--json-out')
    args = parser.parse_args(argv)
    if args.task:
        from translation_workspace import configure_task
        try:
            configure_task(args, 'verify')
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            parser.error(str(exc))
    if not args.current or not args.backup:
        parser.error('provide --task or both --current and --backup')
    if args.json_out:
        try:
            check_report_path(args.json_out, (args.current, args.backup), args.manifest)
        except ValueError as exc:
            parser.error(str(exc))
    try:
        result = verify_directories(args.current, args.backup, args.manifest)
    except (OSError, ValueError, TypeError, RecursionError) as exc:
        result = {'complete': False, 'errors': [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if result['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
