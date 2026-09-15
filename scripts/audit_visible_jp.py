#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""RPG Maker 汉化完整性审计：按「角色 × 可见性」统计剩余未译文本。

判据：与原始备份在同一路径上完全相同、且含 CJK 的字符串 = 未改动（漏译候选）。
不依赖「含假名」判据，因此不会漏掉纯汉字的日文词（肉体遍歴 / 経験人数 …）。

用法：
    python audit_visible_jp.py --current data --backup 原版备份/data \
        [--plugins js/plugins.js] [--plugins-backup 原版备份/js/plugins.js] \
        [--out report.txt] [--kana-only]

无第三方依赖。
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

KANA = re.compile(r"[\u3040-\u309f\u30a0-\u30ff\uff66-\uff9f]")
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff]")

# 事件命令 → (角色名, 玩家可见?)
CMD = {
    401: ("显示文本", True), 405: ("显示文本续行", True),
    102: ("显示选项", True), 402: ("选项文本", False),  # 402 是编辑器里的分支标签
    355: ("脚本", True), 655: ("脚本续行", True),
    657: ("插件指令", True),   # 注意：键名是标识符不能译，见下方 value 判定
    356: ("插件指令MV", True),
    122: ("控制变量", True),   # 类型 4 = 脚本字符串，常是界面标签
    320: ("改名字", True), 324: ("改昵称", True), 325: ("改简介", True),
    101: ("头像设置", False), 108: ("注释", False), 408: ("注释行", False),
    111: ("条件分支", False), 412: ("分支结束", False), 117: ("公共事件", False),
    118: ("标签", False), 119: ("跳转标签", False),
    357: ("插件指令名(MV格式)", False),
}

DB_VISIBLE = {
    "Actors": {"name", "nickname", "profile"},
    "Classes": {"name"},
    "Items": {"name", "description", "message1", "message2", "message3", "message4"},
    "Weapons": {"name", "description", "message1", "message2", "message3", "message4"},
    "Armors": {"name", "description", "message1", "message2", "message3", "message4"},
    "Skills": {"name", "description", "message1", "message2", "message3", "message4"},
    "States": {"name", "message1", "message2", "message3", "message4"},
    "Enemies": {"name"},
    "Map": {"displayName"},
    "System": {"currencyUnit", "gameTitle"},
}
DB_LIKE = set(DB_VISIBLE) - {"Map"}


def load_plugins(path: Path):
    t = path.read_text(encoding="utf-8-sig", errors="replace")
    i = t.find("var $plugins")
    j = t.find("[", i)
    d, k = 0, j
    while k < len(t):
        c = t[k]
        if c == "[":
            d += 1
        elif c == "]":
            d -= 1
            if d == 0:
                break
        k += 1
    return json.loads(t[j:k + 1])


def maybe_json(v, d=0):
    if d > 10 or not isinstance(v, str):
        return v, d
    s = v.strip()
    if s[:1] in "[{" and s[-1:] in "]}":
        try:
            return maybe_json(json.loads(s), d + 1)
        except Exception:
            return v, d
    return v, d


class Audit:
    def __init__(self):
        self.rows = []
        self.total = Counter()

    def add(self, src, role, visible, path, text):
        self.rows.append({"src": src, "role": role, "visible": visible,
                          "path": path, "text": text})
        self.total[(role, visible)] += 1

    # ---- 事件命令 ----
    def walk_events(self, cur, bak, path, src):
        if isinstance(cur, dict):
            if "code" in cur and "parameters" in cur:
                code = cur["code"]
                role, vis = CMD.get(code, (f"code{code}", None))
                cp, bp = cur.get("parameters") or [], (bak or {}).get("parameters") or []
                for i in range(min(len(cp), len(bp))):
                    self._cmp(cp[i], bp[i], f"{path}.parameters[{i}]", src, role, vis, code)
                for k in cur:
                    if k in bak and k not in ("parameters", "code"):
                        self.walk_events(cur[k], bak[k], f"{path}.{k}", src)
                return
            for k in cur:
                if k in bak:
                    self.walk_events(cur[k], bak[k], f"{path}.{k}", src)
        elif isinstance(cur, list):
            for i in range(min(len(cur), len(bak or []))):
                self.walk_events(cur[i], bak[i], f"{path}[{i}]", src)

    def _cmp(self, a, b, path, src, role, vis, code):
        if isinstance(a, dict) and isinstance(b, dict):
            for k in a:
                if k in b:
                    self._cmp(a[k], b[k], f"{path}.{k}", src, role, vis, code)
        elif isinstance(a, list) and isinstance(b, list):
            for i in range(min(len(a), len(b))):
                self._cmp(a[i], b[i], f"{path}[{i}]", src, role, vis, code)
        elif isinstance(a, str):
            if not a.strip() or not CJK.search(a):
                return
            # 657 插件指令：key = value，键名是标识符不译，只看 value 部分
            if code in (657, 356) and " = " in a:
                key, _, val = a.partition(" = ")
                if not val.strip() or val.strip() in ("true", "false") or re.fullmatch(r"[\d.\-]+", val.strip()):
                    return
                # 只记录 value 部分 —— 键名里的假名是合法的，不能计入残留
                self.total[(role + "(值)", vis)] += 1
                if a == b and CJK.search(val):
                    self.add(src, role + "(值)", vis, path, val)
                return
            self.total[(role, vis)] += 1
            if a == b:
                self.add(src, role, vis, path, a)

    # ---- 数据库字段 ----
    def walk_db(self, cur, bak, src, dbname):
        if isinstance(cur, dict):
            for k, v in cur.items():
                if k not in bak:
                    continue
                if isinstance(v, str) and isinstance(bak[k], str):
                    vis = None
                    if k in DB_VISIBLE.get(dbname, ()) or k.startswith("terms"):
                        vis = True
                    elif k in ("note", "meta", "params"):
                        vis = False
                    if vis is not None and v.strip() and CJK.search(v):
                        self.total[(f"字段.{k}", vis)] += 1
                        if v == bak[k]:
                            self.add(src, f"字段.{k}", vis, f"[{dbname}].{k}", v)
                else:
                    self.walk_db(v, bak[k], src, dbname)
        elif isinstance(cur, list):
            for i in range(min(len(cur), len(bak or []))):
                self.walk_db(cur[i], bak[i], src, dbname)

    # ---- 插件参数（递归穿透嵌套 JSON）----
    def walk_plugin(self, v, bakv, path, src, depth=0):
        if depth > 12:
            return
        if isinstance(v, dict) and isinstance(bakv, dict):
            for k in v:
                if k in bakv:
                    self.walk_plugin(v[k], bakv[k], f"{path}.{k}", src, depth)
        elif isinstance(v, list) and isinstance(bakv, list):
            for i in range(min(len(v), len(bakv))):
                self.walk_plugin(v[i], bakv[i], f"{path}[{i}]", src, depth)
        elif isinstance(v, str):
            inner, nd = maybe_json(v)
            if nd:
                binner, bnd = maybe_json(bakv)
                self.walk_plugin(inner, binner if bnd else None, path, src, depth + 1)
                return
            if not v.strip() or not CJK.search(v):
                return
            self.total[("插件参数", True)] += 1
            if v == bakv:
                self.add(src, "插件参数", True, path, v)


def main() -> int:
    ap = argparse.ArgumentParser(description="RPG Maker 汉化完整性审计")
    ap.add_argument("--current", required=True, help="当前 data 目录")
    ap.add_argument("--backup", required=True, help="原版 data 目录备份")
    ap.add_argument("--plugins", help="当前 js/plugins.js")
    ap.add_argument("--plugins-backup", help="原版 js/plugins.js")
    ap.add_argument("--out", default="audit_visible_jp.txt")
    ap.add_argument("--kana-only", action="store_true", help="只列含假名的（铁证）")
    ap.add_argument("--max-sample", type=int, default=200)
    a = ap.parse_args()

    cur_d, bak_d = Path(a.current), Path(a.backup)
    if not cur_d.is_dir() or not bak_d.is_dir():
        raise SystemExit("--current / --backup 必须都是目录")

    au = Audit()
    for p in sorted(cur_d.glob("*.json")):
        bp = bak_d / p.name
        if not bp.exists():
            continue
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            b = json.loads(bp.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"!! {p.name} 解析失败: {e}")
            continue
        au.walk_events(c, b, p.name, p.name)
        stem = p.stem
        if stem in DB_LIKE:
            au.walk_db(c, b, p.name, stem)
        if stem.startswith("Map"):
            au.walk_db(c, b, p.name, "Map")

    if a.plugins and a.plugins_backup:
        try:
            cp = {x["name"]: x for x in load_plugins(Path(a.plugins))}
            bp = {x["name"]: x for x in load_plugins(Path(a.plugins_backup))}
            for name in sorted(set(cp) & set(bp)):
                au.walk_plugin(cp[name].get("parameters") or {},
                               bp[name].get("parameters") or {}, name, name)
        except Exception as e:
            print(f"!! 插件层审计失败: {e}")

    L = []
    L.append("=" * 96)
    L.append(f"未改动且含 CJK 的字符串 = {len(au.rows):,} 条（当前 vs 原版，同路径逐条比对）")
    L.append("=" * 96)
    L.append("")
    L.append(f"{'角色':<24}{'可见':<8}{'未改动':>10}{'该类合计':>12}")
    L.append("-" * 96)
    by_role = Counter((r["role"], r["visible"]) for r in au.rows)
    for (role, vis), n in sorted(by_role.items(), key=lambda x: -x[1]):
        L.append(f"{role:<24}{str(vis):<8}{n:>10,}{au.total.get((role,vis),0):>12,}")

    vis = [r for r in au.rows if r["visible"] is True]
    kana = [r for r in vis if KANA.search(r["text"])]
    kanji = [r for r in vis if not KANA.search(r["text"])]
    L.append("")
    L.append(f"玩家可见 & 未改动 = {len(vis):,} 条")
    L.append(f"  ├─ 含假名（日文铁证） = {len(kana):,} 条")
    L.append(f"  └─ 纯汉字（日汉同形 / 专名，需人工判定） = {len(kanji):,} 条")
    L.append("")
    L.append(f"按角色分布（含假名）：")
    for k, n in Counter(r["role"] for r in kana).most_common(20):
        L.append(f"  {n:>7,}  {k}")
    L.append("")
    L.append(f"=== 含假名的玩家可见残留（前 {a.max_sample} 条）===")
    for r in kana[:a.max_sample]:
        L.append(f"  [{r['src']}] {r['role']}  {r['path']}")
        L.append(f"      {r['text'][:200]!r}")
    if kanji and not a.kana_only:
        L.append("")
        L.append(f"=== 纯汉字的玩家可见残留（前 {min(120, len(kanji))} 条，需人工判定）===")
        for r in kanji[:120]:
            L.append(f"  [{r['src']}] {r['role']}  {r['path']}")
            L.append(f"      {r['text'][:200]!r}")

    out = Path(a.out)
    out.write_text("\n".join(L), encoding="utf-8")
    print(f"未改动含CJK {len(au.rows):,} / 玩家可见 {len(vis):,} / 其中含假名 {len(kana):,}")
    print(f"报告: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
