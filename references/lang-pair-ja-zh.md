# Language pair: Japanese → Chinese

## Choosing a language pair

The engine layer in `SKILL.md` is language-agnostic. A language pair contributes three things:

- **Source-side script detection** — used only for character-level operations (ruby handling), never
  as the "is it translated" criterion.
- **Target-side font requirement** — whether the game needs a font installed.
- **Pair-specific traps** — failure modes that arise only for this combination.

Put the source-side logic in `scripts/lang/<code>.py`. State the rest in a file like this one.

## Model the pair at the character level

Half-width and full-width forms are distinct. Japanese punctuation and brackets (`、。「」『』（）`)
appear in source text and are commonly preserved or mapped to their Chinese equivalents by convention
— decide once per project and apply consistently through the glossary.

## Japanese source

### Ruby

`\RB[kanji,reading]` and `\x1bRB[kanji,reading]` both occur. Only the kanji side is translated.
Readings are kept. See `pitfalls.md`.

Ruby bases frequently contain traditional forms of characters (`陰`, `決`, `闘`, `挿`, `愛`, `絶`,
`獲`, `処`) that must be mapped to their simplified equivalents when the kanji side is rewritten.
Map per character; do not attempt a general transliteration.

### Names

Character names appear in several independent places, and a name changed by an in-game event is
stored per save:

- Database: `Actors.json` → `name` / `nickname`
- Event: `code: 320` parameters
- Runtime override written by plugins into actor objects under a separate key
- Saves: the override as captured at save time

A translate pass over the game files does not update names already written into a save. Verify the
in-game rename event's value and make the save pass match it.

## Chinese target

### Font

Chinese glyphs are usually absent from a Japanese game's shipped font. Either:

- Add a subset font covering the characters the translation actually uses, place it under `fonts/`,
  and set `System.json` → `advanced.mainFontFilename`; or
- Confirm the existing font already covers the translation.

Verify in-game. A missing glyph renders as a blank box, not an error.

### Ruby after translation

Once the kanji side is translated, the retained reading no longer matches the glyph. Two options:

- Keep it (some localisations show the original reading as flavour).
- Strip the ruby markup entirely, leaving plain text.

Decide per project; do not mix.

## The overlapping-script trap

Kanji and Chinese characters overlap, so a Japanese string written entirely in kanji is
indistinguishable from Chinese by inspection. Every listed word below is Japanese and must be
translated, despite being readable as Chinese at a glance:

```
肉体遍歴  性感帯開発度  経験人数  変態度  出産経験  性器状態  名家の子  初体験
```

Backup comparison finds unchanged candidates; changed text still requires contextual review. Glyph heuristics alone cannot certify translation.
