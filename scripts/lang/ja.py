#!/usr/bin/env python3
"""Japanese source profile.

Character-level helpers for handling Japanese text. These support rewriting operations only.

Do NOT use `has_kana()` as the criterion for "is this translated". A Japanese word written entirely
in kanji contains no kana and would be skipped. Combine backup comparison with contextual review; see
`references/pitfalls.md`.
"""

import re

HIRAGANA = r"\u3040-\u309f"
KATAKANA = r"\u30a0-\u30fa\u30fc-\u30ff"
KANA_RE = re.compile(f"[{HIRAGANA}{KATAKANA}]")

# Both encodings occur: backslash and ESC (0x1B).
RUBY_RE = re.compile(r"(?:\\|\x1b)RB\[([^,\]]+),([^\]]+)\]")


def has_kana(text: str) -> bool:
    """True if `text` contains hiragana or katakana. The middle dot U+30FB is excluded."""
    return bool(KANA_RE.search(text))


def ruby_spans(text: str):
    """Yield (match, base, reading) for every ruby annotation, both encodings."""
    for m in RUBY_RE.finditer(text):
        yield m, m.group(1), m.group(2)


def simplify(text: str, table: dict) -> str:
    """Map traditional forms to simplified using a caller-supplied table.

    `table` maps a single character to its replacement, for example {"陰": "阴", "決": "决"}.
    Supply the full table for your project; a partial one leaves the rest unchanged.
    """
    return "".join(table.get(ch, ch) for ch in text)


def rewrite_ruby(text: str, simplify_table: dict) -> str:
    """Rewrite the kanji side of every ruby annotation, keeping the reading and the delimiter.

    Leaves an annotation untouched when its base already contains kana, which indicates the
    annotation is not a kanji-with-reading pair.
    """
    def repl(m):
        base, reading = m.group(1), m.group(2)
        if has_kana(base):
            return m.group(0)
        new_base = simplify(base, simplify_table)
        if new_base == base:
            return m.group(0)
        mark = m.group(0)[: m.group(0).index("RB")]
        return f"{mark}RB[{new_base},{reading}]"

    return RUBY_RE.sub(repl, text)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Japanese text helpers")
    ap.add_argument("text")
    ap.add_argument("--ruby", action="store_true", help="list ruby annotations")
    args = ap.parse_args()

    if args.ruby:
        for _, base, reading in ruby_spans(args.text):
            print(f"base={base!r} reading={reading!r} base_has_kana={has_kana(base)}")
    else:
        print(f"has_kana={has_kana(args.text)}")
