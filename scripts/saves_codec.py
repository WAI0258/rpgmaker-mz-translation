#!/usr/bin/env python3
"""RPG Maker MV/MZ save file codec.

A .rmmzsave file is pako-deflated JSON written as UTF-8. It is not binary.

    decode: bytes -> utf-8 text -> take low byte of each char -> zlib.decompress -> utf-8
    encode: utf-8 -> zlib.compress(level=1) -> map each byte to a char -> utf-8 bytes

Usage:
    python saves_codec.py dump   <save.rmmzsave> [--out json.txt]
    python saves_codec.py encode <json.txt> <out.rmmzsave>
    python saves_codec.py diff   <save.rmmzsave> <backup.rmmzsave>
    python saves_codec.py scan   <dir-or-file>...   [--min-len N]

`scan` lists every string leaf containing non-ASCII, with its JSON path. Use it to find text frozen
into saves. It reports candidates only; decide visibility yourself.
"""

import argparse
import json
import os
import sys
import zlib


def decode_bytes(data: bytes) -> str:
    text = data.decode("utf-8")
    raw = bytes(ord(c) & 0xFF for c in text)
    return zlib.decompress(raw).decode("utf-8")


def encode_json(js: str) -> bytes:
    co = zlib.compressobj(1, zlib.DEFLATED, 15, 8, zlib.Z_DEFAULT_STRATEGY)
    raw = co.compress(js.encode("utf-8")) + co.flush()
    return "".join(chr(b) for b in raw).encode("utf-8")


def load(path: str):
    with open(path, "rb") as fh:
        return json.loads(decode_bytes(fh.read()))


def save(path: str, obj) -> None:
    with open(path, "wb") as fh:
        fh.write(encode_json(json.dumps(obj, ensure_ascii=False)))


def walk_strings(obj, path="", out=None):
    """Yield (path, value) for every string leaf. Not language specific."""
    if out is None:
        out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            walk_strings(v, f"{path}/{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            walk_strings(v, f"{path}[{i}]", out)
    elif isinstance(obj, str):
        out.append((path, obj))
    return out


def cmd_dump(args):
    obj = load(args.save)
    text = json.dumps(obj, ensure_ascii=False, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"written {args.out} ({len(text)} chars)")
    else:
        print(text)


def cmd_encode(args):
    with open(args.json, encoding="utf-8") as fh:
        js = fh.read()
    json.loads(js)  # validate before writing
    with open(args.out, "wb") as fh:
        fh.write(encode_json(js))
    print(f"written {args.out}")


def cmd_diff(args):
    cur = dict(walk_strings(load(args.save)))
    bak = dict(walk_strings(load(args.backup)))
    only_bak = sorted(set(bak) - set(cur))
    only_cur = sorted(set(cur) - set(bak))
    changed = sorted(p for p in set(cur) & set(bak) if cur[p] != bak[p])
    print(f"paths only in backup : {len(only_bak)}")
    print(f"paths only in current: {len(only_cur)}")
    print(f"changed values       : {len(changed)}")
    for p in changed[: args.limit]:
        print(f"  {p}\n    - {bak[p][:120]!r}\n    + {cur[p][:120]!r}")
    if len(changed) > args.limit:
        print(f"  ... {len(changed) - args.limit} more")


def cmd_scan(args):
    targets = []
    for t in args.targets:
        if os.path.isdir(t):
            targets += [os.path.join(t, f) for f in sorted(os.listdir(t)) if f.endswith(".rmmzsave")]
        else:
            targets.append(t)
    for path in targets:
        try:
            obj = load(path)
        except Exception as exc:  # noqa: BLE001
            print(f"[skip] {path}: {exc}")
            continue
        hits = [(p, s) for p, s in walk_strings(obj)
                if len(s) >= args.min_len and any(ord(c) > 0x2E7F for c in s)]
        if hits:
            print(f"\n=== {os.path.basename(path)}: {len(hits)} non-ASCII strings ===")
            for p, s in hits:
                print(f"  {p}\n    {s[:140]!r}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("dump"); p.add_argument("save"); p.add_argument("--out")
    p.set_defaults(func=cmd_dump)

    p = sub.add_parser("encode"); p.add_argument("json"); p.add_argument("out")
    p.set_defaults(func=cmd_encode)

    p = sub.add_parser("diff")
    p.add_argument("save"); p.add_argument("backup")
    p.add_argument("--limit", type=int, default=40)
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("scan")
    p.add_argument("targets", nargs="+")
    p.add_argument("--min-len", type=int, default=2, dest="min_len")
    p.set_defaults(func=cmd_scan)

    args = ap.parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
