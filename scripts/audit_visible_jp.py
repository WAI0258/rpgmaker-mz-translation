#!/usr/bin/env python3
"""Read-only Japanese/CJK candidate audit for data/*.json and plugins.js.

Unchanged CJK and changed text still containing kana are review candidates, not
translation verdicts. Plugin arguments require inspection of the actual plugin.
Exit 1 means incomplete input or structural/choice validation failed; exit 0
means the audit ran, never that a game's translation is complete.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path

KANA = re.compile(r"[\u3040-\u309f\u30a0-\u30fa\u30fc-\u30ff\uff66-\uff9f]")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uff66-\uff9f]")
CMD = {
    401: ('显示文本', True), 405: ('滚动文本', True),
    102: ('选项', True), 402: ('分支标签', False),
    101: ('文本头部', False),
    320: ('姓名', True), 324: ('昵称', True), 325: ('简介', True),
    355: ('脚本', None), 655: ('脚本续行', None),
    356: ('MV插件命令', None), 357: ('MZ插件命令', None),
    657: ('插件命令编辑器说明', False),
    122: ('变量操作', None),
    108: ('注释', False), 408: ('注释续行', False),
    118: ('标签', False), 119: ('跳转标签', False),
}
DB_VISIBLE = {
    'Actors': {'name', 'nickname', 'profile'}, 'Classes': {'name'},
    'Items': {'name', 'description'}, 'Weapons': {'name', 'description'},
    'Armors': {'name', 'description'},
    'Skills': {'name', 'description', 'message1', 'message2'},
    'States': {'name', 'message1', 'message2', 'message3', 'message4'},
    'Enemies': {'name'}, 'Map': {'displayName'},
    'System': {'currencyUnit', 'gameTitle', 'terms', 'armorTypes',
               'weaponTypes', 'elements', 'skillTypes'},
}
EDITOR_DATABASES = {'CommonEvents', 'Troops', 'MapInfos', 'Tilesets', 'Animations'}


def load_plugins(path):
    text = path.read_text(encoding='utf-8-sig')
    match = re.search(r'\bvar\s+\$plugins\s*=\s*', text)
    if not match:
        raise ValueError('var $plugins assignment not found')
    value, _ = json.JSONDecoder().raw_decode(text, match.end())
    if not isinstance(value, list):
        raise ValueError('$plugins must be an array')
    return value


def maybe_json(value):
    if isinstance(value, str) and value.strip().startswith(('{', '[')):
        try:
            return json.loads(value), True
        except json.JSONDecodeError:
            pass
    return value, False


def child_path(path, key):
    return f'{path}[{json.dumps(key, ensure_ascii=False)}]'


class Audit:
    def __init__(self):
        self.rows = []
        self.total = Counter()
        self.errors = []

    def structure(self, cur, bak, path):
        if type(cur) is not type(bak):
            self.errors.append(f'{path}: type changed')
        elif isinstance(cur, dict):
            if cur.keys() != bak.keys():
                self.errors.append(f'{path}: keys changed')
            for key in sorted(cur.keys() & bak.keys()):
                self.structure(cur[key], bak[key], child_path(path, key))
        elif isinstance(cur, list):
            if len(cur) != len(bak):
                self.errors.append(f'{path}: length changed')
            for i, (a, b) in enumerate(zip(cur, bak)):
                self.structure(a, b, f'{path}[{i}]')
        elif not isinstance(cur, str) and cur != bak:
            self.errors.append(f'{path}: non-text value changed')

    def choices(self, events, path):
        active = {}
        for index, event in enumerate(events):
            if not isinstance(event, dict) or 'code' not in event:
                continue
            code, indent = event['code'], event.get('indent', 0)
            params = event.get('parameters', [])
            where = f'{path}[{index}]'
            if code == 102:
                if not params or not isinstance(params[0], list):
                    self.errors.append(f'{where}: invalid choices')
                    continue
                if indent in active:
                    self.errors.append(f'{where}: previous choice block not closed')
                active[indent] = (params[0], set())
            elif code == 402:
                block = active.get(indent)
                if block is None or len(params) < 2:
                    self.errors.append(f'{where}: branch has no matching choice block')
                    continue
                labels, seen = block
                i = params[0]
                if type(i) is not int or not 0 <= i < len(labels):
                    self.errors.append(f'{where}: invalid choice index')
                elif i in seen or params[1] != labels[i]:
                    self.errors.append(f'{where}: duplicate index or mismatched choice label')
                if type(i) is int:
                    seen.add(i)
            elif code == 404:
                block = active.pop(indent, None)
                if block is not None and block[1] != set(range(len(block[0]))):
                    self.errors.append(f'{where}: missing choice branch')
        if active:
            self.errors.append(f'{path}: unclosed choice block')

    def _cmp(self, cur, bak, path, src, role, visible, code=None, depth=0):
        if depth > 32:
            self.errors.append(f'{src}:{path}: nesting exceeds 32; audit incomplete')
            return
        # Native display strings are literal text, even when they look like JSON.
        decode = visible is None and code not in (355, 655, 122, 356)
        inner, decoded = maybe_json(cur) if decode else (cur, False)
        original, original_decoded = maybe_json(bak) if decode else (bak, False)
        if decoded or original_decoded:
            if not (decoded and original_decoded):
                self.errors.append(f'{src}:{path}: encoded JSON shape changed')
                return
            self.structure(inner, original, f'{src}:{path}::<json>')
            self._cmp(inner, original, path + '::<json>', src, role, visible, code, depth + 1)
        elif isinstance(cur, dict) and isinstance(bak, dict):
            for key in sorted(cur.keys() & bak.keys()):
                self._cmp(cur[key], bak[key], child_path(path, key), src, role, visible, code, depth + 1)
        elif isinstance(cur, list) and isinstance(bak, list):
            for i, (a, b) in enumerate(zip(cur, bak)):
                self._cmp(a, b, f'{path}[{i}]', src, role, visible, code, depth + 1)
        elif isinstance(cur, str) and isinstance(bak, str):
            if not cur.strip() and not bak.strip():
                return
            if not CJK.search(cur) and not CJK.search(bak):
                return
            self.total[(role, visible)] += 1
            self.rows.append({'src': src, 'role': role, 'visible': visible,
                              'path': path, 'text': cur, 'original': bak,
                              'status': 'unchanged' if cur == bak else 'changed',
                              'has_kana': bool(KANA.search(cur))})

    def walk_events(self, cur, bak, path, src):
        if isinstance(cur, dict) and isinstance(bak, dict):
            if 'code' in cur and 'parameters' in cur:
                code = cur['code']
                role, visible = CMD.get(code, (f'code{code}', None))
                cp, bp = cur['parameters'], bak.get('parameters', [])
                if not isinstance(cp, list) or not isinstance(bp, list):
                    self.errors.append(f'{src}:{path}: parameters must be arrays')
                    return
                for i, (a, b) in enumerate(zip(cp, bp)):
                    vis = visible
                    if code == 101:
                        vis = i == 4
                    elif code == 357:
                        vis = False if i < 3 else None
                    elif code in (320, 324, 325):
                        vis = i == 1
                    self._cmp(a, b, child_path(path, 'parameters') + f'[{i}]', src, role, vis, code)
                return
            for key in sorted(cur.keys() & bak.keys()):
                self.walk_events(cur[key], bak[key], child_path(path, key), src)
        elif isinstance(cur, list) and isinstance(bak, list):
            if any(isinstance(e, dict) and e.get('code') in (102, 402, 404) for e in cur):
                self.choices(cur, f'{src}:{path}')
            for i, (a, b) in enumerate(zip(cur, bak)):
                self.walk_events(a, b, f'{path}[{i}]', src)

    def walk_db(self, cur, bak, src, dbname, path='$', native_fields=True):
        if isinstance(cur, list) and isinstance(bak, list):
            for i, (a, b) in enumerate(zip(cur, bak)):
                self.walk_db(a, b, src, dbname, f'{path}[{i}]', native_fields)
        elif isinstance(cur, dict) and isinstance(bak, dict):
            if 'code' in cur and 'parameters' in cur:
                return
            for key in sorted(cur.keys() & bak.keys()):
                # Walk containers too, but leave command payload classification to walk_events.
                if key in ('list', 'pages', 'events'):
                    self.walk_db(cur[key], bak[key], src, dbname, child_path(path, key), False)
                    continue
                if native_fields and key in DB_VISIBLE.get(dbname, ()):
                    visible = True
                elif key in ('note', 'meta', 'switches', 'variables') or (
                        key == 'name' and (dbname in EDITOR_DATABASES or not native_fields)):
                    visible = False
                else:
                    visible = None
                self._cmp(cur[key], bak[key], child_path(path, key), src, f'字段.{key}', visible)

    def walk_plugin(self, cur, bak, path, src):
        self._cmp(cur, bak, path, src, '插件参数', None)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--current', required=True)
    ap.add_argument('--backup', required=True)
    ap.add_argument('--plugins')
    ap.add_argument('--plugins-backup')
    ap.add_argument('--out', default='audit_visible_jp.txt')
    ap.add_argument('--json-out', help='Full inventory, exact selectors, classification and errors')
    ap.add_argument('--kana-only', action='store_true', help='Only display kana candidates in text samples')
    ap.add_argument('--max-sample', type=int, default=200)
    args = ap.parse_args(argv)
    if bool(args.plugins) != bool(args.plugins_backup):
        ap.error('--plugins and --plugins-backup must be supplied together')
    cur_dir, bak_dir = Path(args.current), Path(args.backup)
    if not cur_dir.is_dir() or not bak_dir.is_dir():
        ap.error('--current and --backup must be directories')
    au = Audit()
    current = {p.name: p for p in cur_dir.glob('*.json')}
    backup = {p.name: p for p in bak_dir.glob('*.json')}
    if not current or not backup:
        au.errors.append('No data JSON files found; audit incomplete')
    for name in sorted(current.keys() ^ backup.keys()):
        au.errors.append(f'{name}: file missing from current or backup')
    for name in sorted(current.keys() & backup.keys()):
        try:
            cur = json.loads(current[name].read_text(encoding='utf-8-sig'))
            bak = json.loads(backup[name].read_text(encoding='utf-8-sig'))
            au.structure(cur, bak, name)
            au.walk_events(cur, bak, '$', name)
            stem = current[name].stem
            dbname = 'Map' if re.fullmatch(r'Map\d+', stem) else stem
            au.walk_db(cur, bak, name, dbname)
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            au.errors.append(f'{name}: {exc}')
    if args.plugins:
        try:
            cur = load_plugins(Path(args.plugins))
            bak = load_plugins(Path(args.plugins_backup))
            au.structure(cur, bak, 'plugins.js')
            for i, (a, b) in enumerate(zip(cur, bak)):
                if a['name'] != b['name'] or a['status'] != b['status']:
                    au.errors.append(f'plugins.js[{i}]: plugin identity/order/status changed')
                au.walk_plugin(a.get('parameters', {}), b.get('parameters', {}),
                               f'$[{i}]["parameters"]', 'plugins.js')
        except (OSError, ValueError, TypeError, KeyError, RecursionError) as exc:
            au.errors.append(f'plugins.js: {exc}')
    candidates = [r for r in au.rows if r['status'] == 'unchanged' or r['has_kana']]
    lines = ['审计状态: ' + ('不完整/校验失败' if au.errors else '完成'),
             '范围: data/*.json 与可选 plugins.js；不扫描插件源码、图片、存档或文档。',
             '候选不等于漏译；changed 不等于已翻译。未知可见性必须检查实际插件。',
             '::<json> 表示解码后的虚拟路径；写回时必须重新编码其外层字符串。', '']
    for visible, title in [(True, '原生显示字段'), (None, '待判定字段/脚本/插件参数'),
                           (False, '编辑器/标识符/元数据')]:
        rows = [r for r in candidates if r['visible'] is visible]
        unchanged = sum(r['status'] == 'unchanged' for r in rows)
        lines.append(f'{title}: 未改动 CJK {unchanged}; 改动后仍含假名 {len(rows) - unchanged}')
        samples = [r for r in rows if not args.kana_only or r['has_kana']]
        for r in samples[:max(0, args.max_sample)]:
            lines.append(f"  [{r['src']}] {r['path']} {r['role']} {r['status']}: {r['text'][:200]!r}")
        if len(samples) > max(0, args.max_sample):
            lines.append(f'  文本报告截断了 {len(samples) - max(0, args.max_sample)} 条；用 --json-out 获取完整清单。')
    lines.extend(['', '错误:'] + au.errors)
    Path(args.out).write_text('\n'.join(lines), encoding='utf-8')
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({'schema_version': 1, 'complete': not au.errors,
                                                  'rows': au.rows, 'errors': au.errors},
                                                 ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'候选 {len(candidates)} / 校验错误 {len(au.errors)}; 报告: {args.out}')
    return 1 if au.errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
