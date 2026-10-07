# Text map

Exact locations of every text carrier. Paths are JSON paths relative to the file.

## data/Map*.json and data/CommonEvents.json

Event-command lists share one command shape, but their containers differ:

```
MapNNN.json: events[i].pages[j].list[k]
CommonEvents.json: [i].list[k]
Troops.json: [i].pages[j].list[k]
command = { code: <int>, indent: <int>, parameters: [...] }
```

`Game_Interpreter.executeCommand` dispatches by `code` (`methodName = "command" + code`). The set of
native codes is defined by the engine. Plugins can override or add handlers; inspect the shipped
core and plugin set rather than treating this table as exhaustive.

### Codes that carry text

| code | Command | Text location | Action |
|---|---|---|---|
| 401 | Show Text (first line) | `parameters[0]` | translate |
| 405 | Show Scrolling Text line | `parameters[0]` | translate |
| 102 | Show Choices | `parameters[0]` — an **array** of choice strings | translate |
| 402 | When [choice] | `parameters[1]` — the **label**; `parameters[0]` is the branch index (0/1/2) | translate; must equal the matching 102 entry |
| 103 | Input Number | variable ID and digit count | never translate |
| 320 | Change Name | `parameters[1]` | translate |
| 355 / 655 | Script / its continuation | `parameters[0]` — JS source | inspect case by case |
| 357 | Plugin Command (MZ format) | `parameters[0]` = plugin name, `parameters[1]` = method (**never translate**); **remaining parameters may be a nested `dict`/JSON string** | translate the display values only |

#### `code 357` carries a second, nested payload

A plugin command's parameters are **not** uniformly flat strings. A common shape is:

```json
{ "code": 357, "parameters": ["TextPicture", "set", "テキストピクチャの設定",
                              { "text": "\\c[15]ヒガシの国" }] }
```

`parameters[3]` here is an **object**, and its `.text` is the string the player reads. An extractor
that iterates `parameters` and tests `isinstance(v, str)` silently drops it. The plugin-command name
(`TextPicture`) and method (`set`) are runtime lookup keys. `parameters[2]` is an editor
display label, ignored by the native `command357`; `parameters[3].text` reaches the TextPicture
renderer. Other plugins' argument values need inspection: they can be identifiers too.

**Recurse into every parameter.** Walk dicts and lists at any depth and collect every string leaf,
not just the top level. One status screen in one game hid 75 untranslated strings this way — in a
neighbouring command of the *same* screen the same values were already translated, so the screen
rendered half-Chinese and visibly wrong.

#### `テキスト = <value>` is a label *and* content

`code 657` commonly stores an editor annotation such as `command = value`. The native MZ
interpreter has no `command657`; the actual command executes from `357.parameters[3]`.
Do not count the annotation as player-visible. Inspect overrides before treating it as runtime text.
If synchronising it for editor readability, preserve the left side and copy the corresponding
confirmed display value; never translate resource names or enum values merely because they follow `=`:

| Original | Label (keep) | Value (translate) |
|---|---|---|
| `テキスト = ヒガシの国` | `テキスト = ` | `ヒガシの国` → `东方之国` |
| `テキスト = \c[15]処女` | `テキスト = ` | `\c[15]処女` → `\c[15]处女` |

Preserve control codes in the value (`\c[n]`, `\V[n]`, `\{`, `\}`).

### Codes to leave alone

| code | Command | Why |
|---|---|---|
| 108 / 408 | Comment | editor only, never rendered |
| 111 / 411 | Conditional Branch | script expressions |
| 122 | Control Variables | operands/scripts; a string assigned to a variable may be displayed elsewhere, so inspect its consumers |
| 101 | Show Text header | `parameters[0..3]` = face/position metadata; MZ natively renders `parameters[4]` as the speaker name (MV has no native fifth field) | collect only the MZ speaker field; leave face resource names alone |
| other codes | — | inspect engine/plugin consumers; absence from this table is not proof of invisibility |

### Rules for this carrier

- Keep `102` labels and their `402.parameters[1]` labels consistent for editor readability.
  Native runtime routing uses the numeric `402.parameters[0]`, not the label: never change that index.
- Pair a `402` with its enclosing `102` at the same indent, ending at the matching `404`.
  Compare `402.parameters[1] == choices[402.parameters[0]]`; membership alone misses swaps.
- `657` is normally editor metadata. Keep its keys and identifier values intact; inspect overrides.
- For `357`, preserve `parameters[0..1]`; `parameters[2]` is editor metadata. Inspect display
  values in `parameters[3]`, and
  **recurse into nested `dict`/JSON-string parameters** — the display text is often one level down.

## Database files

`DataManager._databaseFiles` fixes this list:

```
Actors.json  Classes.json  Skills.json  Items.json  Weapons.json  Armors.json
Enemies.json  Troops.json  States.json  Animations.json  Tilesets.json
CommonEvents.json  System.json  MapInfos.json
```

A game may add plugin-provided databases alongside these (for example `Quests.json`). Walk whatever
exists; do not hardcode this list as the set of files to read.

### Fields to translate

| File | Fields |
|---|---|
| `System.json` | `terms.basic.*`, `terms.commands.*`, `terms.params.*`, `terms.messages.*`, type lists, `currencyUnit`, `gameTitle`; switches/variables names are editor metadata unless a plugin displays them |
| `MapInfos.json` | `[i].name` is editor metadata by default; `MapNNN.displayName` is native display text — see the dedicated section below, it is a **separate carrier** |
| `Actors.json` | `name`, `nickname`, `profile` |
| `Classes/Items/Skills/Weapons/Armors/States/Enemies.json` | native display fields present in each schema (`name`, item/skill descriptions, skill/state messages); custom fields need consumer inspection |
| `Tilesets/Animations.json` | names are editor metadata by default; inspect plugins before translating |
| `Troops.json` | **both shapes** — see below |
| `CommonEvents.json` | **both shapes** — see below |

### Files that carry both flat fields and an event structure

`CommonEvents.json` and `Troops.json` are top-level **arrays** with event lists and editor fields.
Inspect both, but do not equate a field named `name` with player-visible text:

- `CommonEvents[i].name` — editor name by default; a plugin may explicitly display it.
- `CommonEvents[i].list[]` — event commands.
- `Troops[i].name` — editor name by default; `.description`, if present, is plugin-defined.
- `Troops[i].pages[j].list[]` — the troop's **battle events**, which is where plugin-authored
  battle messages live. A `Troops`-as-flat-DB reader loses all of them (940 occurrences in one
  game).

Walk both: classify flat fields by their consumer and recurse into the appropriate event list. Index
troops by their `pages[j]` position — the `id` field is not a positional match.

`System.json` also holds `advanced.mainFontFilename` — the font the game loads. Change it when the
target language needs a font the game does not ship.

### Fields never to translate

`note`, `meta`, `id`, any `*Id` field, `animationId`, script expressions, image and audio file names,
`encryptionKey`.

`note` holds metadata tags such as `<tag: 150>` that plugins parse by name.

## `data/MapNNN.json` top level — `displayName`

**This is a distinct carrier from `MapInfos.json`, and translating only `MapInfos[].name` leaves
player-visible Japanese on screen.**

| | `MapInfos[i].name` | `MapNNN.displayName` |
|---|---|---|
| Lives in | the map-tree array | the top level of each map file |
| Shown to the player | no (editor tree only) | **yes** — screen top-left |
| Read by | — | `Game_Map.prototype.displayName()` → `$dataMap.displayName` (`rmmz_objects.js`) → `Window_MapName` (`rmmz_windows.js`) |

One game shipped 49 translated `MapInfos` names next to 49 untranslated `displayName` values, so the
map label in the corner stayed Japanese while everything else read Chinese.

Extraction notes:

- `MapNNN.json` top level is a **single object**, not an array. A reader that only walks
  `events[i].pages[j].list[]` never reaches `displayName`, and a generic array-DB field reader will
  not fire either. Read the top-level field explicitly.
- `displayName` is absent on many maps; skip empties.
- It is plain display text — translate it, and keep it consistent with the same place's
  `MapInfos` name so the map tree and the on-screen label agree.
- Note the separator characters vary per entry (`｜`, `:`, `|`, `？？？`). Preserve them; they are
  the author's own formatting.

## js/plugins.js

Shape:

```
[ { name, status, description, parameters: { <key>: <value> } } ]
```

- `parameters` keys are identifiers — never translate.
- Values are frequently **JSON encoded as a string**, sometimes several levels deep. Recurse through
  every string leaf and decide per leaf.
- `__collapsed` is an editor fold marker whose value is a list. Leave it as is.
- A value the plugin matches against event data must keep its original text. Translating it disables
  the feature without any error. Check whether the plugin compares the parameter to a string before
  translating it.
- Every value written back must remain a string. See `plugin-param-repair.md`.

## js/plugins/*.js

Most hits are editor parameter labels and comments — not player-visible. A minority of plugins
hardcode UI strings in source. Scan read-only, then confirm visibility per hit before editing.

A scan that only matches quoted literals (`'…'` / `"…"`) **misses template literals**, which is where
a plugin usually puts a built message: `` `\C[2]${target.name()}は快感に喘いでいる！\C[0]` ``. Scan
line by line for the target script instead of relying on a quoting regex.

Two classes of hit look like display text but must not be translated:

- **Parameter lookup aliases** — `getParamString(['ShakePower', 'シェイク強さ'])`. The Japanese form is
  a fallback *key*; if `plugins.js` stores the value under that key, translating it makes the lookup
  return nothing.
- **Meta-tag keys** — `enemy.meta['HPバーX']`. These match `<HPバーX>` note tags; translating them
  breaks the match.

`@plugindesc` / `@help` / `@param` / `@text` / `@desc` / `@default` and `registerCommand` argument
metadata are editor-only. Leave them.

**The same string often lives in two carriers.** A message a plugin builds in JS is frequently also
written out inline in a `355`/`655` script command in `data/CommonEvents.json` (authors copy the logic
into an event). Translating one and not the other leaves the game switching languages depending on
which path runs. After finishing `js/plugins/*.js`, re-scan `CommonEvents.json` for the same
sentences, and vice versa.

## Window title and bundled docs

Two carriers sit outside `data/` and `js/` and are genuinely player-visible:

- `package.json` → `window.title` and `index.html` → `<title>`: shown in the OS title bar / taskbar.
- `りーどみ.txt` / `ReadMe` / changelog `.txt` shipped beside the game: player documentation. Localise
  the ones that carry gameplay reference (control list, status-effect list); leave credit / licence
  files, whose body is proper nouns. Translate in place — the file name itself stays as shipped.

## img/*.png_ and audio/*.ogg_

RPGMV-style encryption; the key is `System.json` → `encryptionKey`. Editing an image requires
decrypt → edit → re-encrypt with the same key. For image text, follow the optional scope decision
and preview-compare approval gates in `image-redraw.md` before batch processing or writeback.

The container is fixed by the engine (`rmmz_core.js` → `Utils.decryptArrayBuffer`). Read it there
rather than guessing, because the failure is silent:

```
ciphertext = 16-byte header [52 50 47 4d 56 00 00 00 00 03 01 00 00 00 00 00]
             + (first 16 plaintext bytes XOR key) + remaining plaintext bytes
key = encryptionKey, 32 hex chars → 16 bytes
```

A `.png_` does **not** start with the PNG magic. Stripping 16 bytes and XOR-ing the next 16 must
yield `89 50 4e 47`; if it does not, the key or the offset is wrong. Decrypting without removing the
header, or XOR-ing the wrong window, produces a file the engine still accepts but renders as
garbage — always check the magic before editing. `scripts/encrypt_img.py` implements this.

Sample a few images before committing to an image pass: engine defaults (`GameOver`, `Splash`,
`Window`, RTP tiles/characters) carry no text, while a custom title screen usually does.


## save/*.rmmzsave

pako-deflated JSON. See `scripts/saves_codec.py`.

Fields that commonly hold frozen text:

- `variables._data[*]`
- `actors._data[i]._name` and `._name` overrides added by plugins (check every key, including
  double-underscore variants)
- `system._actionLog`
- `party._glossarySetting.*`
- `map._interpreter._list[*].parameters`
- `mapname`
- any plugin-owned stack or log array

For `テキスト = ` style strings, preserve the label and inspect the actual consumer before translating
the value; an editor annotation may have no runtime consumer. Plugin-internal identifiers stay as they are. See
`pitfalls.md`.
