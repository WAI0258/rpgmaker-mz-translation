---
name: rpgmaker-mz-translation
description: "Translates RPG Maker MV/MZ games by editing their text carriers directly: event-command dialogue and database fields in data/*.json, nested parameters in js/plugins.js, strings hardcoded in js/plugins/*.js, text baked into encrypted img/*.png_, and text stored in save/*.rmmzsave. This skill should be used when asked to translate, localize, or audit a RPG Maker MV/MZ game, when asked where a RPG Maker game's text lives or which files to edit, or when a patched game still shows untranslated text in its UI."
license: MIT
agent_created: true
metadata:
  version: "1.2"
---

# RPG Maker MV/MZ Translation

## Scope

The engine layer (finding text, editing text, auditing, saves, images) is language-agnostic.
Verified on Japanese → Chinese. Other language pairs need a profile under `scripts/lang/`; see
`references/lang-pair-ja-zh.md` for the shape of one.

Read `references/validation.md` for the v1.2 inventory contract, evidence and acceptance boundaries.

## Working defaults for Mr.WAI

Use necessary story/operational information as scope; preserve all meaningful source
content. Reuse tools and task data, approve representative samples once per method,
and continue the approved stage. Keep one current artifact set and remove obsolete
trials. Prefer a selective patch or authorized direct installation; no default game clone.
See `references/image-redraw.md` for scope, fidelity and image approval, and
`references/workspace.md` for reuse, delivery and cleanup. These standing preferences
do not grant installation permission for a different game.

## Text carriers

Text is not in one place. It lives in five carriers:

| Carrier | Content | Handled by |
|---|---|---|
| `data/*.json` | event dialogue, choices, plugin commands, database names/descriptions | `references/text-map.md` |
| `js/plugins.js` | plugin parameters; values are nested JSON strings | `references/text-map.md` |
| `js/plugins/*.js` | UI strings hardcoded in plugin source | `references/text-map.md` |
| `img/*.png_` | text baked into encrypted images | `scripts/encrypt_img.py`, then `references/image-redraw.md` |
| `save/*.rmmzsave` | text frozen in player saves | `scripts/saves_codec.py` |

Read `references/text-map.md` before extracting anything. It lists the event-command codes that
carry text, the exact fields to translate, and the fields to leave alone.

## Workspace

For a translation task, once task editing is authorized, initialize/resume with
`python -B <tool>/scripts/translation_workspace.py init --game <game>`.
The target defaults to `zh-CN`; otherwise pass `--target-language <target>`.
The default workspace is `<game-directory-name>_translation_work` beside the game;
respect a user-selected external location via `--workspace`. Use the printed absolute
`workspace.json` as `<task>` in all task commands. Read `references/workspace.md`
for paths, resumption and external-tool/runtime checks. Do not initialize for a merely
read-only question or require users to repeat these default rules in their prompt.

Keep all task artifacts in this workspace: backups, glossary, translations, manifests,
reports, compares, temporary files, caches and builds. Game differences belong in data,
not new per-game scripts. Use `scripts/image_workflow.py` for supported image work;
see `references/image-redraw.md` for its manifest and approval commands. The workspace
entry also handles selective installation, rollback and recorded obsolete-image cleanup.
Never modify the skill
installation or scatter per-game artifacts into other directories. Use Python `-B`,
absolute tool paths and task-mode scripts; run other commands through the workspace
runner with explicit local outputs. The runner configures child cwd/temp/cache settings,
not an OS sandbox. Inspect tools that ignore these settings before using them.

## Procedure

1. **Back up.** Initialization captures pristine data JSON and `plugins.js` in `backup/`
   and makes independent working copies. Verify those backups before edits; keep them intact.
   Back up each other carrier under the same workspace before its first edit too.
2. **Extract.** Run `python -B <tool>/scripts/audit_visible_jp.py --task <task>`.
   Read `reports/inventory.json` for the full inventory; `reports/audit.txt` is a summary.
   This script scans only `data/*.json` and optional `plugins.js`; inspect plugin source, images, saves and bundled docs
   separately. The complete inventory separates display, program, editor and unknown candidates;
   `selector` gives pointer chains suitable for the patch manifest, not automatic write permission.
   Unknown plugin arguments require source inspection. `::<json>` marks a virtual path inside a
   JSON-encoded string: decode and re-encode that enclosing value when writing back.
   **Recurse into every event parameter, at any depth** — plugin commands put display text inside
   nested objects (`parameters[3].text`), which a `isinstance(str)` filter drops without error.
3. **Translate.** Batch by dialogue/scene or UI context; size batches to the available context budget.
   Keep one glossary file as the single source of truth for recurring names; feed it with every batch.
   **Semantic spot-check every draft before accepting it:** read consecutive entries together and
   confirm the sentences connect. A draft that splits one sentence across two lines and merges two
   elsewhere keeps the entry count and the control codes valid, so structural checks pass while the
   whole batch is misaligned. See `references/pitfalls.md`.
4. **Apply.** Read `references/safe-patching.md`. For `data/*.json`, build a reviewed path manifest
   with source digests, expected old values and targets. Preflight `scripts/apply_translation.py`,
   then use `--task <task> --write` to create `build/translated/data`; never globally replace strings or mask by
   value. Explicitly select decoding boundaries for serialized plugin arguments. Record consumers
   for non-native fields and list configuration changes separately. Run `scripts/verify_untouched.py`
   with `--task <task>` before installation; it checks all actual differences and untouched bytes.
   Unknown/excluded candidates need a decision record, not silent omission. Preserve control codes.
5. **Post-process.** Handle ruby text and fonts through the same JSON manifest; regenerate the
   working data if the plan changes rather than mutating an already verified copy. Font assets are
   a separate carrier. Validate `js/plugins.js` after any write (see below).
6. **Audit.** Run the task audit after applying; it selects the translated data and its manifest
   for full data integrity. Review unchanged CJK and changed text still
   containing kana; neither class proves a translation error. Changed kanji-only text still needs
   semantic review. Exit 0 means the audit completed, not that translation is complete; exit 1 means
   input/structure/protection/choice or manifest validation failed. Review all unknown fields before claiming coverage.
   Then run a **proper-noun consistency pass** — batches are translated independently, so drift is
   invisible to any single-string check:
   - (a) review differing targets for the same source **in the same semantic context**; the same
     source can legitimately have different translations across speakers, senses or UI uses;
   - (b) group alternative spellings only after confirming they refer to the same entity/concept.
     Apply the glossary to that entity; do not automatically merge similar source strings;
   - (c) regex-scan the target text for surface variants of each name (e.g. `..莉娜`) to catch stray
     transliterations.
   A source name may legitimately become a pronoun when the addressee *is* that person (`アリナ` → 「你」
   when another character speaks *to* Arina) — review these, do not auto-fix.
   Every check you add must be able to fail: if you cannot name an input that would make it report
   a problem, it is measuring nothing. See `references/pitfalls.md`.
   **Cross-form check:** the same value often appears in more than one command form (a flat
   `command = value` string and a nested `parameters[n].text` object, for example). If one form is
   translated and the other is not, inspect both consumers: it may be a missed payload or merely an
   editor-only annotation (`657`). Do not infer player visibility from matching text alone.
7. **Image text (optional).** Inspect images read-only and report text-bearing candidates. Ask
   whether to leave them, translate selected groups, or translate all confirmed text; title art and
   ordinary UI can be separate choices. Normal text-translation approval does not authorize images.
   After scope approval, make representative samples from pristine backups in a work directory.
   Show an **original → translated preview compare**, including wording, font, layout, colours and
   transparency. Do not write samples into the game. **Wait for the user's approval of the compare
   before batch editing or installing images.** Continue within approved scope/style without
   repeated approval requests. A materially different restoration/visual treatment needs a new
   sample unless covered by the user's standing instruction; filenames/categories alone do
   not create another approval gate.
   Follow `references/image-redraw.md` for optional OCR, redraw methods and visual validation.
8. **Install.** Choose the user's requested selective patch or approved direct installation.
   Do not clone the full game by default; use a full test copy only when requested or when its
   concrete runtime benefit warrants the storage cost. Test the selected target when available.
   Show the changed-file list and obtain approval before replacing original game files;
   use existing explicit installation approval without asking again. Recheck live originals
   and retain rollback copies in the workspace.
9. **Deliver.** Keep work artifacts and backups in the workspace; exclude them from the
   delivered build or patch. Follow `references/release.md`; packaging does not authorize
   deleting the workspace or user-owned files.

## Hard rules

- Backup equality measures whether a string changed, not whether it is translated. Use it with
  source-language candidates and contextual review; kanji-only Japanese defeats kana-only checks.
  Preserve a decision record for reviewed unchanged strings and context-dependent translations.
- **Freeze `note`/`meta` by default.** Tags become runtime lookup keys; their values may be numbers,
  references, expressions or plugin-rendered prose. Do not infer universal invisibility. Verified
  display fragments require a dedicated plugin-specific procedure preserving program dependencies;
  the generic writer does not permit note overrides. Displayed names can also be lookup keys.
- **Permission belongs to a position, not a text value.** Use exact path patches and an independent
  approved-difference check. Neither counting occurrences nor masking note literals makes global
  replacement safe. Known resource/identifier changes must fail regardless of language or kana.
- Never modify identifier strings: plugin-command names, plugin parameter **keys**, `note` tag
  names, `meta` keys, resource file names, and `__collapsed`. This covers the *label* half of
  `command = value` parameters — translate the value only after confirming its runtime consumer.
- Plugin parameters whose value is matched by the plugin against event data must keep their
  original value. Translating them disables features silently. See `references/pitfalls.md`.
- Every value written into `js/plugins.js` `parameters` must be a string.
- Preserve control codes and placeholders verbatim: `\N[n] \V[n] \C[n] \I[n] \G \. \| \{ \} \$`
  and `%1`-style placeholders.
- Keep `code: 102` choice labels and their `code: 402` branch labels identical. The label is
  `402.parameters[1]`; `parameters[0]` is the branch index. Assert the pairing over the whole event
  list using choice-block boundaries and indentation — see `references/pitfalls.md`.
- **One writer per file at a time.** Independent passes based on stale snapshots can undo each other.
  Make a second concern a pass *after* the writer, not a second script re-deriving the same fields.
- Never invent keys such as `"0"` on a database object to simulate indexing. Use an exact JSON
  Pointer into the actual array/object structure. Check every difference against the path manifest.
- Fail closed: verify the expected old value before writing; re-read after writing.

## Validating plugins.js

Run after any write to `js/plugins.js`:

```
python -B <tool>/scripts/fix_plugin_params.py --plugins <workspace>/build/js/plugins.js --backup <workspace>/backup/js/plugins.js --check
node <tool>/scripts/verify_plugins_js.js --plugins <workspace>/build/js/plugins.js --backup <workspace>/backup/js/plugins.js
```

If either reports corruption (non-string parameter values), repair with
`fix_plugin_params.py` and read `references/plugin-param-repair.md`.

## Saves

`save/*.rmmzsave` is pako-deflated plain JSON, not binary. Use `scripts/saves_codec.py` to dump,
diff and rewrite. Saves are a separate front from the game data: a player's existing save keeps
old text after the game files are translated.

## Output language

Write translated text in the target language. Write your replies to the user in their language.
