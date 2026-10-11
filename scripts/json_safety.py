"""Strict JSON, byte spans, RFC 6901 selectors and conservative carrier rules.

Safety is independent of source-language detection. No plugin visibility inference
is attempted: unknown/editor text needs a recorded consumer review.
"""
import json
import hashlib
import os
import stat
import tempfile
import math
from collections import Counter
import re
from pathlib import Path

def inside(path, root):
    return path == root or root in path.parents


def overlap(a, b):
    return inside(a, b) or inside(b, a)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def regular(path, allow_hardlinks=False):
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or path.is_symlink() or
            getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
        raise ValueError(f'expected a regular, unlinked file: {path}')
    if info.st_nlink > 1 and not allow_hardlinks:
        raise ValueError(f'hard-linked file is not allowed: {path}')


def atomic_bytes(path, raw):
    """Replace one checked file; interrupted multi-file writes are journaled separately."""
    if path.exists():
        regular(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix='.translation-', dir=path.parent)
    staged = Path(name)
    try:
        with os.fdopen(descriptor, 'wb') as file:
            file.write(raw)
            file.flush()
            os.fsync(file.fileno())
        os.replace(staged, path)
    finally:
        if staged.exists():
            staged.unlink()


def write_json(path, value):
    atomic_bytes(path, (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8'))


PROTECTED_KEYS = {'note', 'meta'}
RESOURCE_KEYS = {'faceName', 'characterName', 'battlerName', 'battlerName1',
                 'battlerName2', 'animation1Name', 'animation2Name', 'parallaxName',
                 'tilesetNames', 'title1Name', 'title2Name', 'encryptionKey', '__collapsed'}
DB_DISPLAY = {
    'Actors': {'name', 'nickname', 'profile'}, 'Classes': {'name'},
    'Items': {'name', 'description'}, 'Weapons': {'name', 'description'},
    'Armors': {'name', 'description'},
    'Skills': {'name', 'description', 'message1', 'message2'},
    'States': {'name', 'message1', 'message2', 'message3', 'message4'},
    'Enemies': {'name'},
}
SYSTEM_DISPLAY = {'currencyUnit', 'gameTitle', 'terms', 'armorTypes',
                  'weaponTypes', 'elements', 'skillTypes'}
NUMBER = re.compile(rb'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?')


def strict_loads(text):
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f'duplicate JSON key: {key!r}')
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError(f'non-JSON constant: {value}')

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError('JSON number is outside finite float range')
        return number

    return json.loads(text, object_pairs_hook=object_pairs, parse_constant=invalid_constant,
                      parse_float=finite_float)


def pointer(path):
    return ''.join('/' + str(k).replace('~', '~0').replace('/', '~1') for k in path)


def resolve(tree, text):
    """Return the typed path and value; never eval a selector."""
    if not isinstance(text, str) or (text and not text.startswith('/')):
        raise ValueError('selector must be an RFC 6901 JSON Pointer')
    path = []
    node = tree
    for part in text.split('/')[1:] if text else []:
        if re.search(r'~(?![01])', part):
            raise ValueError('invalid JSON Pointer escape')
        key = part.replace('~1', '/').replace('~0', '~')
        if isinstance(node, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', key):
                raise ValueError('invalid array index')
            key = int(key)
            if key >= len(node):
                raise ValueError('array index outside document')
        elif not isinstance(node, dict) or key not in node:
            raise ValueError(f'no value at {text!r}')
        path.append(key)
        node = node[key]
    return tuple(path), node


def selector_chain(value):
    parts = [value] if isinstance(value, str) else value
    if not isinstance(parts, list) or not parts or any(not isinstance(p, str) for p in parts):
        raise ValueError('path must be a pointer or a nonempty list of pointers')
    if len(parts) > 16:
        raise ValueError('too many JSON-string decoding boundaries')
    return tuple(parts)


class Document:
    """Map parsed values to their exact UTF-8 byte spans, including BOM offset."""
    def __init__(self, raw):
        raw.decode('utf-8-sig')  # Reject invalid UTF-8 even outside string tokens.
        self.raw = raw
        self.spans = {}
        self.pos = 3 if raw.startswith(b'\xef\xbb\xbf') else 0
        self.value = self._value((), 0)
        self._space()
        if self.pos != len(raw):
            raise ValueError('trailing data after JSON document')

    def _space(self):
        while self.pos < len(self.raw) and self.raw[self.pos] in b' \t\r\n':
            self.pos += 1

    def _string(self):
        start = self.pos
        self.pos += 1
        while self.pos < len(self.raw):
            char = self.raw[self.pos]
            self.pos += 1
            if char == 92:
                self.pos += 1
            elif char == 34:
                return strict_loads(self.raw[start:self.pos].decode('utf-8'))
        raise ValueError('unterminated JSON string')

    def _value(self, path, depth):
        if depth > 128:
            raise ValueError('JSON nesting exceeds 128')
        self._space()
        start = self.pos
        char = self.raw[self.pos:self.pos + 1]
        if char == b'"':
            value = self._string()
        elif char in (b'{', b'['):
            obj = char == b'{'
            close = b'}' if obj else b']'
            self.pos += 1
            value = {} if obj else []
            self._space()
            if self.raw[self.pos:self.pos + 1] != close:
                while True:
                    self._space()
                    if obj:
                        if self.raw[self.pos:self.pos + 1] != b'"':
                            raise ValueError('object key must be a string')
                        key = self._string()
                        if key in value:
                            raise ValueError(f'duplicate JSON key: {key!r}')
                        self._space()
                        if self.raw[self.pos:self.pos + 1] != b':':
                            raise ValueError('missing object colon')
                        self.pos += 1
                        value[key] = self._value(path + (key,), depth + 1)
                    else:
                        value.append(self._value(path + (len(value),), depth + 1))
                    self._space()
                    if self.raw[self.pos:self.pos + 1] == close:
                        break
                    if self.raw[self.pos:self.pos + 1] != b',':
                        raise ValueError('missing JSON comma or closing delimiter')
                    self.pos += 1
            self.pos += 1
        else:
            match = NUMBER.match(self.raw, self.pos)
            token = match.group() if match else next(
                (word for word in (b'true', b'false', b'null') if self.raw.startswith(word, self.pos)), None)
            if token is None:
                raise ValueError(f'invalid JSON value at byte {self.pos}')
            self.pos += len(token)
            value = strict_loads(token.decode('ascii'))
            if isinstance(value, float) and not (-float('inf') < value < float('inf')):
                raise ValueError('JSON number is outside finite float range')
        self.spans[path] = (start, self.pos)
        return value

    def token(self, path):
        start, end = self.spans[path]
        return self.raw[start:end]


def locate(document, chain):
    levels = []
    current = document
    for i, item in enumerate(chain):
        path, value = resolve(current.value, item)
        levels.append((current, path, value))
        if i + 1 < len(chain):
            if not isinstance(value, str):
                raise ValueError('decoding boundary does not select a JSON string')
            current = Document(value.encode('utf-8'))
    return levels


def protected_reason(tree, path):
    if any(key in PROTECTED_KEYS for key in path):
        return 'note/meta subtree is frozen; requires a dedicated plugin-specific procedure'
    if any(key in RESOURCE_KEYS for key in path):
        return 'resource/identifier field is frozen'
    if path and isinstance(path[-1], str) and (path[-1] == 'id' or path[-1].endswith('Id')):
        return 'identifier field is frozen'
    if len(path) >= 2 and path[-2:] == ('damage', 'formula'):
        return 'damage formula is program input'
    node = tree
    for i, key in enumerate(path):
        if isinstance(node, dict) and 'code' in node and 'parameters' in node:
            if key in ('code', 'indent'):
                return 'event command structure is frozen'
            if key == 'parameters' and i + 1 < len(path):
                index = path[i + 1]
                code = node['code']
                if (code == 101 and index == 0 or code == 357 and index < 3 or
                        code in (118, 119) or code == 231 and index == 1 or
                        code in (241, 245, 249, 250) and index == 0):
                    return 'event resource/command/label metadata is frozen'
        node = node[key]
    return None


def category(tree, path, filename):
    if protected_reason(tree, path):
        return 'program'
    node = tree
    for i, key in enumerate(path):
        if isinstance(node, dict) and 'code' in node and key == 'parameters' and i + 1 < len(path):
            code, index = node['code'], path[i + 1]
            if (code in (401, 405) and index == 0 or code == 102 and index == 0 or
                    code == 402 and index == 1 or code in (320, 324, 325) and index == 1 or
                    code == 101 and index == 4):
                return 'display'
            return 'editor' if code in (108, 408, 657) else 'unknown'
        node = node[key]
    stem = Path(filename).stem
    if (len(path) == 2 and isinstance(path[0], int) and path[1] in DB_DISPLAY.get(stem, ()) or
            stem == 'System' and path and path[0] in SYSTEM_DISPLAY or
            re.fullmatch(r'Map\d+', stem) and path == ('displayName',)):
        return 'display'
    if path and (path[-1] == 'name' and stem in {'MapInfos', 'CommonEvents', 'Troops', 'Tilesets', 'Animations'} or
                 stem == 'System' and path[0] in ('switches', 'variables')):
        return 'editor'
    return 'unknown'


def structure_errors(current, backup, path='$'):
    """Compare all containers/types/scalars; strings can change except note/meta."""
    errors = []
    if type(current) is not type(backup):
        return [f'{path}: type changed']
    if isinstance(backup, dict):
        if current.keys() != backup.keys():
            errors.append(f'{path}: keys changed')
        for key in sorted(current.keys() & backup.keys()):
            child = f'{path}[{json.dumps(key, ensure_ascii=False)}]'
            if key in PROTECTED_KEYS and not equal(current[key], backup[key]):
                errors.append(f'{child}: protected note/meta changed')
            else:
                errors.extend(structure_errors(current[key], backup[key], child))
    elif isinstance(backup, list):
        if len(current) != len(backup):
            errors.append(f'{path}: length changed')
        for i, (a, b) in enumerate(zip(current, backup)):
            errors.extend(structure_errors(a, b, f'{path}[{i}]'))
    elif not isinstance(backup, str) and current != backup:
        errors.append(f'{path}: non-text value changed')
    return errors


def equal(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    return a == b


def json_files(directory):
    directory = Path(directory).resolve()
    if not directory.is_dir():
        raise ValueError(f'not a directory: {directory}')
    files = {p.name: p for p in directory.glob('*.json')}
    if not files:
        raise ValueError(f'no data JSON files: {directory}')
    for path in files.values():
        if not path.is_file() or path.resolve().parent != directory:
            raise ValueError(f'file escapes data directory: {path.name}')
    return files


def snapshot_hash(raw_files):
    digest = hashlib.sha256()
    for name, raw in sorted(raw_files.items()):
        digest.update(name.encode('utf-8') + b'\0')
        digest.update(hashlib.sha256(raw).digest())
    return digest.hexdigest()


def load_manifest(path):
    data = strict_loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or set(data) != {'schema_version', 'source_sha256', 'files'}:
        raise ValueError('manifest needs schema_version, source_sha256 and files only')
    if type(data['schema_version']) is not int or data['schema_version'] != 1:
        raise ValueError('unsupported manifest schema')
    if not isinstance(data['source_sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', data['source_sha256']):
        raise ValueError('source_sha256 must be a lowercase SHA256 digest')
    if not isinstance(data['files'], list):
        raise ValueError('manifest files must be an array')
    files = {}
    for entry in data['files']:
        if not isinstance(entry, dict) or set(entry) != {'file', 'sha256', 'changes'}:
            raise ValueError('file entry needs file, sha256 and changes only')
        name = entry['file']
        if (not isinstance(name, str) or not re.fullmatch(r'[^/\\:]+\.json', name) or
                name in ('.json', '..json') or name in files):
            raise ValueError('file must be a unique data JSON basename')
        if not isinstance(entry['sha256'], str) or not re.fullmatch(r'[0-9a-f]{64}', entry['sha256']):
            raise ValueError(f'{name}: invalid sha256')
        if not isinstance(entry['changes'], list) or not entry['changes']:
            raise ValueError(f'{name}: changes must be a nonempty array')
        seen = set()
        for change in entry['changes']:
            if (not isinstance(change, dict) or not {'path', 'old', 'new'} <= change.keys() or
                    change.keys() - {'path', 'old', 'new', 'kind', 'review'}):
                raise ValueError('change needs path, old, new; optional kind and review')
            chain = selector_chain(change['path'])
            if chain in seen:
                raise ValueError(f'{name}: duplicate patch selector {chain}')
            seen.add(chain)
            if change.get('kind', 'translation') not in ('translation', 'config'):
                raise ValueError('kind must be translation or config')
            if 'review' in change and not isinstance(change['review'], str):
                raise ValueError('review must be a consumer/configuration rationale string')
        files[name] = entry
    return data, files


def validate_change(filename, document, change):
    chain = selector_chain(change['path'])
    levels = locate(document, chain)
    for doc, path, _ in levels:
        reason = protected_reason(doc.value, path)
        if reason:
            raise ValueError(f'{filename} {chain}: {reason}')
    path, old = levels[-1][1:]
    if not equal(old, change['old']):
        raise ValueError(f'{filename} {chain}: expected old value does not match')
    new = change['new']
    if type(new) is not type(old) or isinstance(old, (dict, list)):
        raise ValueError('patch must preserve scalar type; containers cannot be replaced')
    if equal(new, old):
        raise ValueError('unchanged values belong in the decision record, not the patch')
    kind = change.get('kind', 'translation')
    label = category(document.value, levels[0][1], filename)
    if kind == 'translation' and not isinstance(old, str):
        raise ValueError('translation patches must edit string values only')
    if isinstance(old, str) and control_tokens(old) != control_tokens(new):
        raise ValueError('control codes/placeholders changed or lost')
    if (kind == 'config' or label != 'display') and not change.get('review', '').strip():
        raise ValueError('configuration or non-native text needs a recorded consumer review')
    # Do not give an opaque JSON blob permission to change every leaf inside it.
    if label != 'display' and isinstance(old, str) and old.strip().startswith(('{', '[')):
        try:
            parsed = strict_loads(old)
        except ValueError:
            parsed = None
        if isinstance(parsed, (dict, list)):
            raise ValueError('JSON-encoded payload needs an explicit decoding boundary and leaf selector')
    return levels


def choice_errors(events, path='$'):
    errors, active = [], {}
    for index, event in enumerate(events):
        if not isinstance(event, dict) or 'code' not in event:
            continue
        code, indent = event['code'], event.get('indent', 0)
        params = event.get('parameters', [])
        where = f'{path}[{index}]'
        if code not in (102, 402, 404):
            continue
        if type(indent) is not int or not isinstance(params, list):
            errors.append(f'{where}: invalid choice command shape')
            continue
        if code == 102:
            if not params or not isinstance(params[0], list):
                errors.append(f'{where}: invalid choices')
                continue
            if indent in active:
                errors.append(f'{where}: previous choice block not closed')
            active[indent] = (params[0], set())
        elif code == 402:
            block = active.get(indent)
            if block is None or len(params) < 2:
                errors.append(f'{where}: branch has no matching choice block')
                continue
            labels, seen = block
            i = params[0]
            if type(i) is not int or not 0 <= i < len(labels):
                errors.append(f'{where}: invalid choice index')
            elif i in seen or params[1] != labels[i]:
                errors.append(f'{where}: duplicate index or mismatched choice label')
            if type(i) is int:
                seen.add(i)
        elif code == 404:
            block = active.pop(indent, None)
            if block is not None and block[1] != set(range(len(block[0]))):
                errors.append(f'{where}: missing choice branch')
    if active:
        errors.append(f'{path}: unclosed choice block')
    return errors


def all_choice_errors(tree, path='$'):
    errors = []
    if isinstance(tree, dict):
        for key, value in tree.items():
            errors.extend(all_choice_errors(value, path + '/' + str(key)))
    elif isinstance(tree, list):
        if any(isinstance(e, dict) and e.get('code') in (102, 402, 404) for e in tree):
            errors.extend(choice_errors(tree, path))
        for i, value in enumerate(tree):
            errors.extend(all_choice_errors(value, path + '/' + str(i)))
    return errors


def frozen_token_errors(current, backup, filename):
    errors, frozen = [], []
    for path in sorted(backup.spans, key=len):
        if any(path[:len(parent)] == parent for parent in frozen):
            continue
        if protected_reason(backup.value, path):
            frozen.append(path)
            if path not in current.spans or current.token(path) != backup.token(path):
                errors.append(f'{filename} {pointer(path)}: protected program token changed')
    return errors


def audit_selector(text):
    """Convert our bracket display path to pointers without eval or regex splitting."""
    if not text.startswith('$'):
        raise ValueError('audit path must start with $')
    decoder, position, parts, path = json.JSONDecoder(), 1, [], []
    while position < len(text):
        if text.startswith('::<json>', position):
            parts.append(pointer(path))
            path = []
            position += len('::<json>')
            continue
        if text[position] != '[':
            raise ValueError('invalid audit path')
        key, end = decoder.raw_decode(text, position + 1)
        if type(key) not in (str, int) or text[end:end + 1] != ']':
            raise ValueError('invalid audit path component')
        path.append(key)
        position = end + 1
    parts.append(pointer(path))
    return parts


def control_tokens(text):
    tokens = []
    for match in re.finditer(r'\\\\|\x1b\x1b|(?:\\|\x1b)(?:[A-Za-z]+(?:\[[^\]]*\])?|[.$|{}!><^])|%[1-9][0-9]*', text):
        token = match.group()
        ruby = re.fullmatch(r'(\\|\x1b)RB\[([^,\]]+),([^\]]+)\]', token, re.IGNORECASE)
        # Ruby base text is display text; keep the directive and reading intact.
        tokens.append(ruby[1] + token[1:3] + '[' + ruby[3] + ']' if ruby else token)
    return Counter(tokens)


def check_report_path(path, directories, manifest=None, protected_files=()):
    target = Path(path).resolve()
    for directory in directories:
        directory = Path(directory).resolve()
        if target == directory or directory in target.parents:
            raise ValueError('report must be outside current/source/backup data directories')
    for file in (*protected_files, manifest):
        if file is not None and target == Path(file).resolve():
            raise ValueError('report must not overwrite an input file or patch manifest')
