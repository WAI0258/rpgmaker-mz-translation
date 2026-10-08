# Pitfalls

These observations suggest checks, not universal engine rules. Verify game-specific thresholds and consumers.

## Detection

**Do not use script detection as the criterion for "untranslated".**
A rule such as "translate if it contains kana" (`[\u3040-\u309f\u30a0-\u30ff]`) skips every Japanese
word written entirely in kanji: `肉体遍歴`, `性感帯開発度`, `経験人数`, `変態度`, `出産経験`, `初体験`.
These look like Chinese and pass as translated.

Use instead:

> A leaf is an untranslated candidate when it is **equal to the original parsed value at the same
> path** and contains CJK.

This catches unchanged kanji-only candidates but is not a translation verdict. Legitimately retained
terms may be unchanged; adding punctuation to Japanese makes it changed without translating it.
Also review changed text containing kana and inspect changed kanji-only text semantically.

**Do not use a display whitelist as proof of complete coverage.** Known display paths are useful
for prioritization; inspect unknown/protected and excluded candidates too. Walk every field recursively. Fields that have been missed this way: glossary UI labels under
`party._glossarySetting`, plugin-owned parameter arrays, map names, and display-name override fields
stored under non-obvious keys.

## Scope inflation

A raw "unchanged and contains CJK" count runs into tens of thousands of entries, nearly all of them
correctly untouched. Before reporting, classify and exclude:

| Category | Why it stays untranslated |
|---|---|
| `code: 657` annotations | editor metadata by default; inspect runtime overrides |
| `357.parameters[0..1]` | runtime lookup keys; script bodies and argument values need separate inspection |
| Comments (`108` / `408`) | editor only |
| `note` fields | metadata parsed by tag name |
| Credits / contributor lists | real people's names |
| Resource names and enum values | breaking them breaks loading |

The remaining count depends on the game; never infer completeness from a small count.

## Ruby text

`\RB[kanji,kana]` attaches a reading to kanji. Change only the kanji side:
`\RB[陰茎,ペニス]` → `\RB[阴茎,ペニス]`.

Two encodings occur in the same file set: `\RB[...]` and `\x1bRB[...]` (ESC `0x1B` instead of
backslash). Match both — a regex on `\\RB` alone silently misses the ESC form:

```
(?:\\|\x1b)RB\[([^,\]]+),([^\]]+)\]
```

## Silent feature breakage

Translating a plugin parameter that the plugin compares against event data disables the feature with
no error. Before translating a plugin parameter, check whether the plugin uses its value as a lookup
key or a comparison operand. If it does, keep the original.

The same trap hides in the source of the plugin itself:

- `getParamString(['ShakePower', 'シェイク強さ'])` — the Japanese form is a fallback **key**, not a
  label. If `plugins.js` stores the value under that key, translating it makes the lookup return
  nothing and the setting silently falls back to the code default.
- `enemy.meta['HPバーX']` — matches a `<HPバーX>` note tag. Translating it breaks the match.

## The same text can be display content and program input

A measured incident had a database `name` containing `MP再生値:10` beside
`note: "<MP再生値:10>"`. Replacing the escaped source text without its JSON quotes changed both,
including the text inside the tag. The enabled `RegenerationFixed` plugin could no longer find
`MP再生値`, so fixed MP recovery disappeared. Native MP regeneration does not read this tag:
`SimplePassiveSkillMZ` adds the referenced armour to the actor's trait objects, and
`RegenerationFixed` reads metadata from those objects and adds fixed recovery.

The subsequent masking script still replaced by value, despite carrying paths. Identical display
and note values were both masked; identical display and resource values could both be replaced.
A count of one does not prove permission to edit; a count of two does not identify the safe occurrence.

Use `scripts/apply_translation.py` and `safe-patching.md`: select the exact path, verify the old
value and source digests, then validate every actual change against that plan independently. Do not
copy the masking approach or create another global replacer. `note`/`meta` are frozen by default.
They may contain plugin-rendered prose, so investigate the consumer instead of declaring them
universally invisible. A dedicated exception must preserve tag syntax and program dependencies.

A structural comparison that permits every string change is insufficient. The original auditor
recorded changed notes but did not fail them. The first incident checker also skipped event `code`
and `indent`, ignored new metadata, confused bool/int equality and called parsed equality byte
identity. Regression tests must make those defects fail, while allowing valid files with zero notes.

## Audits that stop at quoted literals

A scanner written for `'…'` / `"…"` finds none of the strings a plugin builds with a template literal:
`` this.push("addText", `\C[2]${target.name()}は快感に喘いでいる！\C[0]`) ``. Backtick literals are
where interpolated messages live, and they are exactly the strings that reach the screen.

Scan the script **line by line** for the source language and discard lines that are pure comment
(`//`, `*`, `/*` with no quote or backtick). Confirm against an independent pass rather than trusting
one regex.

## One sentence, two carriers

An author who prototypes logic in an event and then moves it into a plugin often leaves both copies in
the shipped build: the same message exists as a `355`/`655` script command inside
`data/CommonEvents.json` **and** hardcoded in `js/plugins/*.js`. Translating only one leaves the game
switching language depending on which path executes — and the data-side copy can make the plugin-side
gap invisible to a grep over the plugin folder.

After finishing one carrier, re-scan the other for the same sentences.

## Branch desynchronisation

Keep `102` options and `402.parameters[1]` branch labels aligned for editor readability.
Native MV/MZ routing depends on the numeric `402.parameters[0]` and event indentation, not the label.
Writing a translation into the numeric index breaks routing; changing only the label does not.

Walk the whole event list with a choice block per indentation level. Open on `102`, close on the
matching `404`, and pair only the `402` commands belonging to that block. Require an integer index
in range, one branch per index, and `branch_label == choices[index]`. A membership test accepts
swapped labels; an unbounded scan pairs unrelated consecutive or nested choices.

## Engine labels that look like text

`テキスト = <content>` stores a command label followed by content. The engine strips the label before
rendering; the player sees only `<content>`. Do not edit the label portion. Similar prefixes exist in
other plugins.

**First confirm the runtime consumer.** For `657`, the string is normally an editor annotation;
native MZ executes the corresponding `357` argument object. If a plugin actually renders a
`command = value` string, preserve its label and translate only the confirmed display value —
`テキスト = ヒガシの国` ships a display value (`ヒガシの国` → `东方之国`) that a reader never sees
the label for. Classifying the entire parameter as a label skips real content. Split on the first
` = `, keep the left side, translate the right side (control codes included).

## An extractor that type-checks drops nested payloads

An extractor that walks event commands and tests `isinstance(parameters[i], str)` silently discards
every parameter that is a `dict` or a nested JSON string. Nothing errors; the report is simply short.

Observed: `code 357` carries its display text at `parameters[3].text`, an object one level down.
A status screen built entirely from these commands rendered with Japanese values while the rest of
the game was Chinese. A neighbouring `657` editor annotation had already been translated,
which concealed the unchanged runtime argument during an annotation-based review. The actual
display comes from `357.parameters[3]`, unless a plugin overrides that behaviour.

**Recurse to arbitrary depth.** Collect every string leaf under `parameters` — dict, list, and
JSON-encoded string alike. Then verify: for a screen whose values appear in two command forms,
confirm **both** forms were translated. A disagreement across related values is a review signal; check which ones actually render before
calling it a runtime translation gap.

**Inspect the runtime payload systematically.** A flat `657` annotation can help locate the adjacent
`357` command, but is not a second runtime carrier. Compare related values, then translate the
confirmed display arguments in `parameters[3]`; editor annotations may be synchronised separately. Hand-listing the strings you happen
to notice leaves the rest behind — a first pass fixed 5 values on one screen and missed 2 more on the
next round, because the list came from what was visible in a screenshot, not from the data.

**A kanji-only Japanese string defeats a kana check.** `人間(女)` contains no kana at all; the only
glyph difference may be useful, but glyph shape does not prove translation status. Compare the
runtime `357` value with its original and contextual translation decision; a sibling `657` annotation
is only supporting evidence and may legitimately differ.

## Plugin parameter corruption

A non-string value written into `parameters` makes the game fail at startup
(`TypeError: param.match is not a function`) or inflates `plugins.js` to many times its size when
later runs re-wrap the previous output. See `plugin-param-repair.md`.

## Partial writes

A patch that matches some targets and not others leaves a mixed state that is harder to diagnose than
either extreme. Verify every expected old value first, and write nothing if any check fails.

## Text-mode writes rewrite line endings on Windows

`open(p, "w", encoding="utf-8")` and `io.open(..., newline="")` are **not** equivalent on Windows, and
the combination is the worst case: reading with `newline=""` correctly preserves the file's LF endings,
but the subsequent text-mode write then translates every `\n` to `\r\n`. One pass turned 12 LF game
files into CRLF without touching a single string.

The engine does not care (JSON parses either way), but it breaks byte-level comparison against the
pristine copy, so every later "did anything else change?" check reports noise and the real signal is
lost.

**Write game data as bytes.** Read `p.read_bytes()`, do the replacement on the encoded token, assert
the result still parses, then `p.write_bytes(...)`. Round-tripping through text mode is what introduces
the drift. When a text-mode write already happened, `data.replace(b"\r\n", b"\n")` restores it —
verify against the backup that CRLF presence and trailing-newline presence both match the original.

## Structural checks must compare against the pristine copy

Anchoring "is this file still valid?" to a self-generated report is circular — the report was produced
by the same pass that may have broken the file. Diff every touched file against the backup instead:
BOM presence, line-ending style, trailing newline, JSON parse, and a skeleton fingerprint (key set,
array lengths, numbers, booleans) with string values excluded. Only string values may differ.

## Saves are a separate front

Translating the game files does not update existing saves. A 「status」 or 「history」 screen that draws
`$gameVariables.value(N)` keeps showing the old language. Handle saves as their own pass.

## Images are an optional, separate front

Text baked into images is not reachable by editing JSON. Report it separately and ask whether the
user wants it translated; ordinary text approval does not authorize image edits. Provide an
original → translated preview compare after scope approval, then wait for compare approval before
batch processing or writeback. Record images deliberately retained as part of the agreed scope.

See `image-redraw.md` for inspection, optional OCR, background restoration, font/layout pitfalls and
visual acceptance. Heuristics and OCR scores narrow the search; neither proves that a skipped image
has no text. Do not quote a stock asset count as a limit on a custom game's image text.

## Fonts

If the target language needs glyphs the game's font lacks, translated text renders as blank boxes.
Add a subset font and point `System.json` → `advanced.mainFontFilename` at it. Verify by launching.

- Build the character set from the **final on-disk display text** (the translated values), not from
  the original source: the original still contains source-script kanji that will never be rendered,
  and its presence hides misses that actually matter.
- The original font may itself be incomplete. A shipped Japanese font often has `★`/`♥` but no
  emoji, so the game has always fallen back to a system font for those. Merging a monochrome emoji
  font into the subset makes the build self-contained instead of depending on the player's machine.
  Drop `U+FE0F` before checking outlines — a variation selector legitimately has no glyph.
- Native MZ `Game_System.mainFontFace()` reads `advanced.fallbackFonts`. The configured fonts
  still have to exist and provide the required glyphs; check the shipped core/plugins and preview
  on the target machine. A configured family name alone does not ensure portable coverage.
- The number-font slot (`advanced.numberFontFilename`) usually only draws digits (`Sprite_Damage`,
  gauge values, timer) — it does not need a target-language font.

## Batch drafts that pass every structural check

A batch can be wrong in a way that count checks, control-code checks and glossary checks all
accept. Observed: one draft **split a single sentence across two lines** and **merged two sentences
into one line** elsewhere. The two errors cancelled — 81 lines in, 81 lines out — so the batch
validated perfectly while every sentence in it was misaligned.

What does not catch it: entry count, control-code preservation, per-string length plausibility.

What does:

- **Semantic anchor comparison** — read consecutive entries of the draft together and ask whether
  the sentences actually connect. Cheap, and it found the whole batch immediately.
- A length-ratio + sentence-final-punctuation heuristic across a batch flags candidates. It also
  produces false positives on legitimately short labels (`防御`), so treat hits as "look here", never
  as "fix this".

Run the heuristic across **all** batches, not only the one that looks wrong — nothing in the data
marks the batch that contains the error.

## One writer per file

Two scripts that each write `data/*.json` will undo each other. Observed: a `sync_choice_branch`
script wrote 402 labels from the translation table, then an `apply_data` script re-derived the same
fields from the same table with a different rule and reverted them. Each script was correct alone
and the pair oscillated.

Give `data/` a single write point. If a second concern genuinely needs to modify the same files,
make it a **pass that runs after** the writer inside the same process, not a separate script that
re-derives the same fields. When two passes must both write, have the later one read the earlier
one's output as its baseline instead of the original backup.

## Debug writes are writes

A debugging snippet that writes `node[0] = value` on a parsed event list **modifies the game file**
when the object tree is later serialised. Observed: 8 files gained a spurious `"0"` key on 24
event nodes, and `apply_data` faithfully carried them into the shipped build.

Rules:

- Never address `data/*.json` content by container index. Locate by JSON path.
- A throwaway diagnostic that mutates the parsed tree must operate on a `copy.deepcopy`, or the
  write-back step must be skipped entirely for that run.
- **Structural comparison against the backup is the only reliable detector of this class.**
  It caught the pollution immediately because a `code: 401` node gained a key it should not have.
  Content checks cannot see it.

## Self-checks that cannot fail

A metric whose definition overlaps the thing it measures is constant, and reports success forever.
Three instances from one session, all on the same image task:

| Check | Why it is vacuous |
|---|---|
| "dark pixels inside the safe zone = 0" | The zone mask was built as `gray > 200`, which **excludes** dark pixels by definition. Always 0. |
| "pixels dark in both original and result = residue" | After erasing, those pixels hold the **new** text — also dark. Always hundreds. |
| "dark in both, minus new-text ink" | New-text ink was defined as `dark in result AND light in original`, so the intersection is empty by construction and the remainder is the new text. Always hundreds. |

Before trusting a check, ask: **what input would make this fail?** If nothing can, delete it — a
constant-true check is worse than no check, because it manufactures false confidence. For visual
work, residue is a **human** judgement: render a magnified crop and look.

## Font charset from renderable text only

Building the subset from "all strings in `data/`" inflates it with glyphs that are never drawn —
one build carried 104 extra outlines because it included `note` fields, `CommonEvents[].name`,
`code: 118/119` labels, and `code: 357` plugin-command names.

Collect the character set from **renderable** fields only:

- event command parameters whose code carries display text,
- database display fields (`name`, `description`, `message1`…`message4`, `profile`, `nickname`),
- `System.json` terms / type lists; include switch/variable names only when a plugin displays them,
- static text (`index.html`, `package.json`, bundled docs),
- display fields captured in saves.

Exclude identifier/editor portions: note keys, event names not displayed by plugins, comments,
labels and `357.parameters[0..2]`. Include confirmed display literals inside `355`/`655` scripts and
confirmed display arguments inside `357.parameters[3]`; do not exclude a whole command code.

Verify the result by scanning **that restricted set** against the finished `cmap` and requiring zero
misses. A miss here is a blank box in game; an extra glyph costs only file size.

## Keep a pristine copy of every file you edit

Backing up `data/` is not enough. Plugin sources under `js/plugins/` are edited too, and a build
directory frequently ships **without any original archive** — the working copy is the only copy.

- Back up each `js/plugins/*.js` at the moment you first touch it, not at the end.
- If you discover a file was edited with no backup, reconstruct it immediately while the exact
  old→new pairs are still known, then record that the reconstruction — not an untouched copy — is what
  the backup holds.
- Do not delete the working directory until the user has a rollback path. Flag it explicitly when no
  original archive exists.

## A backup overwritten by your own restore

Restoring originals from the backup directory before re-running a rewrite is correct — until the
backup was itself taken *after* a first pass. The restore then feeds the rewritten art back in, the
source-string match fails, and the script reports a clean run over already-Chinese images.

The tell: a before/after sheet where **both halves look identical**. Confirm which you are looking
at by reading one region at 4×, and check the backup's own timestamp against the session that first
wrote the images.

Prevention:
- Take the backup **once**, before any write, and never let a `cp` into that directory run again
  without a fresh look at what is being copied.
- Keep a session log line naming the timestamp the backup was taken.
- Build before/after sheets by reading the **original from the backup at render time**. Reusing an
  exported crop from an earlier step compares the new art against a stale copy and hides the problem.

## Image-detection criteria that exclude the thing you are looking for

Two criteria that silently dropped every target:

- *Search for UI panels by white-background ratio.* Status sheets are transparent-backed with black
  rules — the white ratio is near zero and all of them were filtered out. Detect panels by **long
  straight runs plus stroke-shaped connected components**, never by background colour.
- *Find dark text with `luma < 120`.* Red and other coloured labels fail the threshold, the region
  reads as blank, and the label is skipped. Use *opaque AND luma < 200*.

Both fail silently: the report just gets shorter, and the miss is only visible in-game.

## Screenshots that contradict the files

When a user reports untranslated text with a screenshot, first search for that exact string in the
current game files:

- Found → a real miss; fix it.
- Not found, and not in the original either → the screenshot is from a different build, or the text
  comes from a save. Report the contradiction and ask for a screenshot from the current build instead
  of guessing.

**Take the search string from the image, not from memory.** Transcribing Japanese by hand produces
plausible-but-wrong characters, and a wrong query returns nothing — which then looks like
"the file disagrees" and sends the diagnosis the wrong way. Copy the exact substring.

Escalate the search before concluding, in this order — stopping early is what turns "not found" into
a wrong conclusion:

1. `data/` and `js/`
2. **every save directory that exists** — a build may ship `セーブデータ/save/` *and* write a second
   `save/` beside `index.html` at runtime. Check both; do not assume there is one
3. the whole game tree, every file, decoding as UTF-8, CP932 and UTF-16 — and for `*._` assets also
   test the header-XORed variant, since a keyword can live in an encrypted resource
4. **the pristine backup** — this is the only step that distinguishes "was never there" from
   "was removed", and a string that appears in the backup only inside ordinary dialogue is not a
   screen field
5. the data the screen actually reads: if the event references only `\V[n]` variables, list those
   variable numbers and look them up. A screen whose event cites no such field does not have one.

Report the contradiction with the evidence — the ranges searched and the counts. Do not invent a
translation for text that is not in the build, and do not keep re-searching the same tree with a
wider net: if 1,800 files across three encodings and both save directories contain nothing, the
string is not coming from this build. Ask which build or which screenshot produced it.

### Worked case: the string *was* in the build, under a second key

A screenshot showed Japanese map text in the screen corner while every searched file came back clean
for it. Step 1 (`data/` + `js/`) genuinely found nothing for the exact substring — the on-screen
string and the stored string were not byte-identical.

What broke the deadlock was locating the **Japanese keyword fragment** instead of the full string
(`森林地帯`), which pointed at ten map files, and then asking *which field* holds it. The answer was
`displayName` on each map's top level — a different carrier from the `MapInfos[].name` already
translated. Grep had missed it because the searched term was the full display string, which uses a
different separator (`｜` vs `：` vs `|`) than the one in the screenshot's phrasing.

Generalisation for step 1: **search a distinctive keyword, not the whole string.** Separators,
full-width digits and punctuation vary between the on-screen rendering and the stored value, and
several unrelated files will match a keyword that a whole-string search narrows to zero.
