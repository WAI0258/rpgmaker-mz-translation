---
name: rpgmaker-mz-translation
description: "Translates RPG Maker MV/MZ games by editing their text carriers directly: event-command dialogue and database fields in data/*.json, nested parameters in js/plugins.js, strings hardcoded in js/plugins/*.js, text baked into encrypted img/*.png_, and text stored in save/*.rmmzsave. This skill should be used when asked to translate, localize, or audit a RPG Maker MV/MZ game, when asked where a RPG Maker game's text lives or which files to edit, or when a patched game still shows untranslated text in its UI."
license: MIT
agent_created: true
---

# RPG Maker MV/MZ Translation

## Scope

The engine layer (finding text, editing text, auditing, saves, images) is language-agnostic.
Verified on Japanese → Chinese. Other language pairs need a profile under `scripts/lang/`; see
`references/lang-pair-ja-zh.md` for the shape of one.

## Text carriers

Text is not in one place. It lives in five carriers:

| Carrier | Content | Handled by |
|---|---|---|
| `data/*.json` | event dialogue, choices, plugin commands, database names/descriptions | `references/text-map.md` |
| `js/plugins.js` | plugin parameters; values are nested JSON strings | `references/text-map.md` |
| `js/plugins/*.js` | UI strings hardcoded in plugin source | `references/text-map.md` |
| `img/*.png_` | text baked into encrypted images | `scripts/encrypt_img.py` |
| `save/*.rmmzsave` | text frozen in player saves | `scripts/saves_codec.py` |

Read `references/text-map.md` before extracting anything. It lists the event-command codes that
carry text, the exact fields to translate, and the fields to leave alone.

## Procedure

1. **Back up.** Copy `data/` and `js/plugins.js` to a pristine backup outside the game tree.
   Do not modify anything until the backup exists. All later steps compare against it.
2. **Extract.** Run `python scripts/audit_visible_jp.py --current <game/data> --backup <backup/data>
   --plugins <game/js/plugins.js> --plugins-backup <backup/js/plugins.js> --out <report>`.
   It walks every carrier, resolves each leaf to a JSON path, and classifies by visible/not-visible.
   It reports; it does not decide. Judge visibility yourself against the plugin set this game ships.
3. **Translate.** Batch the output (~230 units per batch). Keep one glossary file as the single
   source of truth for recurring names; feed it with every batch.
4. **Apply.** Write back by JSON path with whole-string matching. Preserve control codes exactly.
   Abort the whole run if any expected old value does not match — never write a partial patch.
5. **Post-process.** Handle ruby text, install a font if the target language needs one, and
   validate `js/plugins.js` (see below).
6. **Audit.** Run the extractor again against the backup. Treat only the paths that still differ
   from the original as candidates; see `references/pitfalls.md` for why kana detection is wrong.
7. **Install.** Replace the live files, keeping the previous versions until the game launches clean.
8. **Clean up.** Remove every work artifact before shipping. Follow `references/release.md`
   exactly — it lists what to delete and what must never be touched.

## Hard rules

- A string qualifies as untranslated only if it is **identical to the original backup at the same
  path**. Do not use script detection (kana, CJK ranges) as the criterion — it silently skips
  Japanese words written entirely in kanji. See `references/pitfalls.md`.
- Never modify identifier strings: plugin-command names, plugin parameter **keys**, `note` tag
  names, `meta` keys, resource file names, and `__collapsed`.
- Plugin parameters whose value is matched by the plugin against event data must keep their
  original value. Translating them disables features silently. See `references/pitfalls.md`.
- Every value written into `js/plugins.js` `parameters` must be a string.
- Preserve control codes and placeholders verbatim: `\N[n] \V[n] \C[n] \I[n] \G \. \| \{ \} \$`
  and `%1`-style placeholders.
- Keep `code: 102` choice labels and their `code: 402` branch labels identical.
- Fail closed: verify the expected old value before writing; re-read after writing.

## Validating plugins.js

Run after any write to `js/plugins.js`:

```
python scripts/fix_plugin_params.py --plugins <js/plugins.js> --backup <backup/js/plugins.js> --check
node scripts/verify_plugins_js.js --plugins <js/plugins.js> --backup <backup/js/plugins.js>
```

If either reports corruption (non-string parameter values), repair with
`fix_plugin_params.py` and read `references/plugin-param-repair.md`.

## Saves

`save/*.rmmzsave` is pako-deflated plain JSON, not binary. Use `scripts/saves_codec.py` to dump,
diff and rewrite. Saves are a separate front from the game data: a player's existing save keeps
old text after the game files are translated.

## Output language

Write translated text in the target language. Write your replies to the user in their language.
