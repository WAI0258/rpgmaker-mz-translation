#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""修复 RPG Maker MV/MZ 的 js/plugins.js 插件参数损坏。

损坏形态：参数值被写成 [值, 布尔] 列表（布尔是「是否已翻译」之类的标记），
嵌套时外面还会套 str() 产生的 Python repr。后果是游戏启动即报
TypeError: param.match is not a function，且 plugins.js 体积可能爆炸到几十 MB。

用法：
    # 只读体检
    python fix_plugin_params.py --plugins path/to/js/plugins.js --check

    # 干跑（只报告，不写文件）
    python fix_plugin_params.py --plugins path/to/plugins.js --backup path/to/原版备份.js --dry-run

    # 正式修复（先写 .fixed、回读校验、结构差异为 0 才安装）
    python fix_plugin_params.py --plugins path/to/plugins.js --backup path/to/原版备份.js

无第三方依赖。修复前请确保 --backup 指向原版 plugins.js。
"""
from __future__ import annotations

import argparse
import ast
import json
import shutil
import sys
from pathlib import Path

# 编辑器自带的折叠状态标记，值本来就是列表，属正常，不修
NON_STR_ALLOWED = {"__collapsed"}


# --------------------------------------------------------------------------- #
# 读写
# --------------------------------------------------------------------------- #
def split_js(path: Path):
    """把 plugins.js 拆成 (头部, 插件数组 JSON 文本, 尾部)。"""
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    i = text.find("var $plugins")
    if i < 0:
        i = text.find("$plugins")
    if i < 0:
        raise SystemExit(f"在 {path} 里找不到 $plugins 定义")
    j = text.find("[", i)
    depth, k = 0, j
    while k < len(text):
        c = text[k]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                break
        k += 1
    if k >= len(text):
        raise SystemExit(f"{path} 的 $plugins 数组没有闭合，文件可能已被截断")
    return text[:j], text[j:k + 1], text[k + 1:]


def load_plugins(path: Path):
    _, body, _ = split_js(path)
    try:
        return json.loads(body)
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path} 的 $plugins 不是合法 JSON：{e}")


# --------------------------------------------------------------------------- #
# 核心：拆包裹
# --------------------------------------------------------------------------- #
def is_pair(v) -> bool:
    """是不是事故产生的 [值, 布尔] 包裹。

    严格要求「长度 2 且第二元素是 bool」，这样 ["a","b","c"] 这类
    合法的 JSON 数组参数不会被误伤。
    """
    return isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[1], bool)


def unwrap(v):
    """反复拆包裹，返回 (结果, 拆包路径)。拆不动就原样返回。"""
    trail = []
    for _ in range(60):
        if is_pair(v):
            trail.append("pair")
            v = v[0]
            continue
        if isinstance(v, str):
            s = v.strip()
            if s[:1] in "([" and s[-1:] in ")]":
                try:
                    r = ast.literal_eval(v)
                except (ValueError, SyntaxError):
                    break
                if is_pair(r):
                    trail.append("repr")
                    v = r[0]
                    continue
            break
        break
    return v, trail


def non_string_params(arr):
    return [(p.get("name"), k, type(v).__name__)
            for p in arr for k, v in (p.get("parameters") or {}).items()
            if not isinstance(v, str) and k not in NON_STR_ALLOWED]


# --------------------------------------------------------------------------- #
# 结构比对（只比类型与长度，不比文本）
# --------------------------------------------------------------------------- #
def deep(v, d=0):
    """把「嵌套 JSON 字符串」逐层解开，便于比对结构。"""
    if d > 8 or not isinstance(v, str):
        return v
    s = v.strip()
    if s[:1] in "[{" and s[-1:] in "]}":
        try:
            return deep(json.loads(s), d + 1)
        except (json.JSONDecodeError, ValueError):
            return v
    return v


def struct_diff(cur, bak, where, out, limit=300):
    if len(out) > limit:
        return
    if type(cur) is not type(bak):
        out.append(f"{where}: {type(bak).__name__} -> {type(cur).__name__}")
        return
    if isinstance(cur, dict):
        for k in cur:
            if k not in bak:
                out.append(f"{where}.{k}: 新增")
            else:
                struct_diff(cur[k], bak[k], f"{where}.{k}", out, limit)
        for k in bak:
            if k not in cur:
                out.append(f"{where}.{k}: 丢失")
    elif isinstance(cur, list):
        if len(cur) != len(bak):
            out.append(f"{where}: 长度 {len(bak)} -> {len(cur)}")
        for i in range(min(len(cur), len(bak))):
            struct_diff(cur[i], bak[i], f"{where}[{i}]", out, limit)


# --------------------------------------------------------------------------- #
# 三个模式
# --------------------------------------------------------------------------- #
def mode_check(plugins: Path) -> int:
    arr = load_plugins(plugins)
    print(f"文件: {plugins}  ({plugins.stat().st_size:,} B)")
    print(f"插件数 = {len(arr)}")
    bad = non_string_params(arr)
    print(f"非字符串参数 = {len(bad)}  （__collapsed 折叠标记已豁免）")
    for b in sorted(bad):
        print("   %s.%s -> %s" % b)
    if bad:
        largest = max((len(v) for p in arr for k, v in (p.get("parameters") or {}).items()
                       if isinstance(v, (list, str)) and k not in NON_STR_ALLOWED), default=0)
        print(f"最大参数值 = {largest:,} B")
        print("结论: 异常 —— 请用 --dry-run 预览修复，再正式修复")
        return 1
    print("结论: 正常")
    return 0


def mode_fix(plugins: Path, backup: Path | None, dry_run: bool) -> int:
    arr = load_plugins(plugins)
    bak_list = load_plugins(backup) if backup else None
    bak = {p.get("name"): p for p in bak_list} if bak_list else None

    if bak:
        print(f"原版备份: {backup}  ({backup.stat().st_size:,} B)  {len(bak_list)} 插件")
    print(f"待修文件: {plugins}  ({plugins.stat().st_size:,} B)  {len(arr)} 插件")
    print()

    fixed = 0
    for p in arr:
        name = p.get("name")
        params = p.get("parameters") or {}
        bp = (bak or {}).get(name)
        # 有备份时按原版键序排列，避免任何顺序差异
        if bp is not None:
            old_keys = list((bp.get("parameters") or {}).keys())
            ordered = {k: params[k] for k in old_keys if k in params}
            for k in params:
                ordered.setdefault(k, params[k])
            p["parameters"] = params = ordered
            miss = set((bp.get("parameters") or {})) ^ set(params)
            if miss:
                print(f"  [注意] {name} 参数键与原版不一致: {sorted(miss)}")
        for k, v in list(params.items()):
            if isinstance(v, str) or k in NON_STR_ALLOWED:
                continue
            nv, trail = unwrap(v)
            if isinstance(nv, str):
                before = len(json.dumps(v, ensure_ascii=False))
                print(f"  [修] {name}.{k}: {before:,} B -> {len(nv):,} B  ({'>'.join(trail)})")
                params[k] = nv
                fixed += 1
            else:
                print(f"  [保留] {name}.{k}: 非字符串且非事故形态 -> {type(nv).__name__}")

    print()
    print(f"共修复 {fixed} 个参数")
    left = non_string_params(arr)
    print(f"修完后仍非字符串 = {len(left)}  {left if left else ''}")

    if dry_run:
        print("\n[干跑] 未写入任何文件。去掉 --dry-run 即执行修复。")
        return 0

    if left:
        print("\n仍有非字符串参数，放弃写入。请人工确认后再跑。")
        return 1

    # 序列化：沿用原版文件头/尾，一行一个插件
    if backup:
        head, _, tail = split_js(backup)
    else:
        head, _, tail = split_js(plugins)
    lines = [json.dumps(p, ensure_ascii=False, separators=(",", ":"))
             .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
             for p in arr]
    new_text = head + "[\n" + ",\n".join(lines) + "\n]" + tail

    tmp = plugins.with_suffix(".js.fixed")
    tmp.write_text(new_text, encoding="utf-8")
    print(f"\n[写出] {tmp}  {tmp.stat().st_size:,} B")

    # 回读校验
    chk = load_plugins(tmp)
    bad = non_string_params(chk)
    print(f"[校验] 非字符串参数 = {len(bad)}  {bad if bad else ''}")
    diffs = []
    if bak:
        for n in sorted(set(x.get("name") for x in chk) & set(bak)):
            cc = next(x for x in chk if x.get("name") == n)
            for k in (bak[n].get("parameters") or {}):
                struct_diff(deep((cc.get("parameters") or {}).get(k)),
                            deep((bak[n].get("parameters") or {}).get(k)),
                            f"{n}.{k}", diffs)
        print(f"[校验] 与原版结构差异 = {len(diffs)}")
        for d in diffs[:20]:
            print("    " + d)

    if bad or diffs:
        print("\n[结论] 校验未通过，已放弃安装。.fixed 文件保留供检查。")
        return 1

    shutil.copy2(plugins, plugins.with_suffix(".js.broken"))
    shutil.copy2(tmp, plugins)
    print(f"\n[安装] 已写入 {plugins}")
    print(f"[备份] 损坏版另存 {plugins.with_suffix('.js.broken')}（确认无误后可删）")
    print("[下一步] 跑 verify_plugins_js.js 复核，期望 RESULT: OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="修复 RPG Maker 插件参数损坏")
    ap.add_argument("--plugins", required=True, help="js/plugins.js 路径")
    ap.add_argument("--backup", help="原版 plugins.js 备份路径（强烈建议提供）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写文件")
    ap.add_argument("--check", action="store_true", help="只读体检")
    a = ap.parse_args()

    plugins = Path(a.plugins)
    if not plugins.exists():
        raise SystemExit(f"找不到 {plugins}")
    if a.check:
        return mode_check(plugins)
    backup = Path(a.backup) if a.backup else None
    if backup and not backup.exists():
        raise SystemExit(f"找不到备份 {backup}")
    if backup is None:
        print("⚠️  未提供 --backup，将无法做结构比对，也不会沿用原版文件头/尾。")
    return mode_fix(plugins, backup, a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
