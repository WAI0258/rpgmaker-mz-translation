# Pitfalls

Each entry is a failure that has occurred. Check for them explicitly.

## Detection

**Do not use script detection as the criterion for "untranslated".**
A rule such as "translate if it contains kana" (`[\u3040-\u309f\u30a0-\u30ff]`) skips every Japanese
word written entirely in kanji: `肉体遍歴`, `性感帯開発度`, `経験人数`, `変態度`, `出産経験`, `初体験`.
These look like Chinese and pass as translated.

Use instead:

> A leaf is an untranslated candidate when it is **byte-identical to the original backup at the same
> path** and contains CJK.

This needs no assumption about glyph shapes and does not miss kanji-only words.

**Do not rely on a whitelist of JSON paths.** A narrow whitelist produces a false "nothing left"
result. Walk every field recursively. Fields that have been missed this way: glossary UI labels under
`party._glossarySetting`, plugin-owned parameter arrays, map names, and display-name override fields
stored under non-obvious keys.

## Scope inflation

A raw "unchanged and contains CJK" count runs into tens of thousands of entries, nearly all of them
correctly untouched. Before reporting, classify and exclude:

| Category | Why it stays untranslated |
|---|---|
| `code: 657` parameter keys (`key = value`) | the plugin reads them by name |
| `code: 355/357` script and plugin-command names | looked up by name |
| Comments (`108` / `408`) | editor only |
| `note` fields | metadata parsed by tag name |
| Credits / contributor lists | real people's names |
| Resource names and enum values | breaking them breaks loading |

After excluding these, a genuine miss list is usually single digits.

## Ruby text

`\RB[kanji,kana]` attaches a reading to kanji. Change only the kanji side:
`\RB[陰茎,ペニス]` → `\RB[阴茎,ペニス]`.

Two encodings occur in the same file set: `\RB[...]` and `\x1bRB[...]` (ESC `0x1B` instead of
backslash). Match both — a regex on `\\RB` alone silently misses the ESC form:

```
(?:\\)|\x1b)RB\[([^,\]]+),([^\]]+)\]
```

## Silent feature breakage

Translating a plugin parameter that the plugin compares against event data disables the feature with
no error. Before translating a plugin parameter, check whether the plugin uses its value as a lookup
key or a comparison operand. If it does, keep the original.

## Branch desynchronisation

`code: 102` choice labels and `code: 402` branch labels must stay identical. Editing one without the
other misroutes execution.

## Engine labels that look like text

`テキスト = <content>` stores a command label followed by content. The engine strips the label before
rendering; the player sees only `<content>`. Do not edit the label portion. Similar prefixes exist in
other plugins.

## Plugin parameter corruption

A non-string value written into `parameters` makes the game fail at startup
(`TypeError: param.match is not a function`) or inflates `plugins.js` to many times its size when
later runs re-wrap the previous output. See `plugin-param-repair.md`.

## Partial writes

A patch that matches some targets and not others leaves a mixed state that is harder to diagnose than
either extreme. Verify every expected old value first, and write nothing if any check fails.

## Saves are a separate front

Translating the game files does not update existing saves. A 「status」 or 「history」 screen that draws
`$gameVariables.value(N)` keeps showing the old language. Handle saves as their own pass.

## Encrypted images are a separate front

Text baked into `img/*.png_` is not reachable by editing JSON. Do not include it in a "translation
complete" claim unless it was actually processed.

## Fonts

If the target language needs glyphs the game's font lacks, translated text renders as blank boxes.
Add a subset font and point `System.json` → `advanced.mainFontFilename` at it. Verify by launching.

## Screenshots that contradict the files

When a user reports untranslated text with a screenshot, first search for that exact string in the
current game files:

- Found → a real miss; fix it.
- Not found, and not in the original either → the screenshot is from a different build, or the text
  comes from a save. Report the contradiction and ask for a screenshot from the current build instead
  of guessing.
