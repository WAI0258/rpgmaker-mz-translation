# Text map

Exact locations of every text carrier. Paths are JSON paths relative to the file.

## data/Map*.json and data/CommonEvents.json

Both share one structure:

```
events[i].pages[j].list[k] = { code: <int>, indent: <int>, parameters: [...] }
```

`Game_Interpreter.executeCommand` dispatches by `code` (`methodName = "command" + code`). The set of
codes is fixed by the engine — do not infer it from a game's files.

### Codes that carry text

| code | Command | Text location | Action |
|---|---|---|---|
| 401 | Show Text (first line) | `parameters[0]` | translate |
| 405 | Show Text (continuation) | `parameters[0]` | translate |
| 102 | Show Choices | `parameters[0]` — an **array** of choice strings | translate |
| 402 | When [choice] | `parameters[0]` | translate; must equal the matching 102 entry |
| 103 | Choice cancel branch label | `parameters[0]` | translate |
| 320 | Change Name | `parameters[1]` | translate |
| 355 / 655 | Script / its continuation | `parameters[0]` — JS source | inspect case by case |
| 657 | Plugin Command | `parameters[0]` = command name (**never translate**); remaining parameters vary | translate values only |

### Codes to leave alone

| code | Command | Why |
|---|---|---|
| 108 / 408 | Comment | editor only, never rendered |
| 111 / 411 | Conditional Branch | script expressions |
| 122 | Control Variables | operands only, no display text |
| 101 | Show Text header | face/position metadata |
| everything else | — | no display text |

### Rules for this carrier

- 102 and 402 must stay in sync. Translating one without the other misroutes branches.
- Do not translate 657 `parameters[0]`. It is looked up by name.
- In 657, parameter keys are identifiers. Translate only human-readable values.

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
| `System.json` | `terms.basic.*`, `terms.commands.*`, `terms.params.*`, `terms.messages.*`, `armorTypes`, `weaponTypes`, `elements`, `skillTypes`, `switches[]`, `variables[]` |
| `MapInfos.json` | `[id].name` |
| `Actors.json` | `name`, `nickname`, `profile` |
| `Classes/Items/Skills/Weapons/Armors/States/Enemies/Troops/Tilesets/Animations.json` | `name`, `description`, `message1`…`message4`, `profile` |
| `CommonEvents.json` | as `Map*.json` — the event structure, not flat fields |

`System.json` also holds `advanced.mainFontFilename` — the font the game loads. Change it when the
target language needs a font the game does not ship.

### Fields never to translate

`note`, `meta`, `id`, any `*Id` field, `animationId`, script expressions, image and audio file names,
`encryptionKey`.

`note` holds metadata tags such as `<tag: 150>` that plugins parse by name.

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

## img/*.png_ and audio/*.ogg_

RPGMV-style encryption; the key is `System.json` → `encryptionKey`. Editing an image requires
decrypt → edit → re-encrypt with the same key. Treat as a separate workstream and confirm with the
user before starting.

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

Never translate engine command labels (`テキスト = ` style prefixes are stripped before display; see
`pitfalls.md`) or plugin-internal identifiers.
