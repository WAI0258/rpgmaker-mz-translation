# Evidence and validation boundaries — v1.2

The tool version is v1.2, independent of the engine version. Inspect the target game's core and
plugin overrides before applying version-specific rules.

## Primary evidence

- [Official MZ Messages help](https://rpgmakerofficial.com/product/MZ_help-en/01_10_01.html): native speaker names and control characters.
- [Official MZ Utils source](https://developer.rpgmakerweb.com/rpg-maker-mz/Utils.js.html): encryption header and XOR window.
- [Official MV core repository](https://github.com/rpgtkoolmv/corescript/blob/master/js/rpg_objects/Game_Interpreter.js): numeric choice routing.
- [MZ v1.1.0 core source mirror](https://github.com/stak/rmmz-corescript/blob/master/rmmz_objects.js): 101, 356/357, 402 and fallbackFonts. This is a versioned engine-source mirror, not an official latest-version guarantee.
- [TextPicture implementation mirror](https://github.com/stak/rmmz-corescript/blob/master/plugins/TextPicture.js): args.text reaches the renderer.
- [GNU gettext contexts](https://www.gnu.org/software/gettext/manual/html_node/Contexts.html): identical source text can require different translations by context.
- [W3C ITS 2.0](https://www.w3.org/TR/its20/): separate translatability, localization notes and terminology metadata. These concepts inform our inventory; the JSON report does not claim ITS conformance.
- [Freitag et al., TACL 2021](https://aclanthology.org/2021.tacl-1.87/): explicit MQM error annotation with document context. Its news-translation study does not establish an optimal game-translation batch size or certify this tool.
- [Python os.replace](https://docs.python.org/3.13/library/os.html#os.replace): replacement semantics. Single-file replacement is not a multi-file transaction or a guarantee against power loss.

- [RFC 6901 JSON Pointer](https://www.rfc-editor.org/rfc/rfc6901): exact value selection, escaping,
  array indices and failure on ambiguous member names.
- [RFC 8259 JSON](https://www.rfc-editor.org/rfc/rfc8259): JSON grammar and interoperability risks of
  duplicate keys. The patch tools conservatively reject duplicates/nonstandard numeric constants.
- [More Status Menu Pages, plugin author documentation](https://www.yanfly.moe/wiki/More_Status_Menu_Pages_%28YEP%29):
  note fields can hold displayed titles/prose as well as program relationships; this disproves
  universal "notes are never displayed" rules. It does not establish which plugins this game loads.

## Workspace acceptance

Translation tasks initialize one external workspace and pass its `workspace.json` with
`--task` to the writer, verifier and audit. See `workspace.md` for commands and defaults.
Workspace tests cover game/target identity, backup digests, default and overridden paths,
initial/translated selection, working-copy writes, report collisions, Windows junctions
or symlinks, hard-linked outputs and process-local temp/cache settings. Resolved-path checks
are not an OS sandbox or a concurrent-filesystem defense; third-party outputs and gameplay
must still be checked in the selected environment. Standalone explicit-path calls do not
provide the task boundary. CLI usage/task-configuration rejection returns argparse status 2
without creating reports; completed check results continue to use 0/1.

## Four independent acceptance checks

1. Integrity: use the reviewed source-bound manifest with `verify_untouched.py`. Every actual
   difference must select an approved scalar, preserve type and match expected old/new values.
   Unapproved strings, keys, types, array lengths, event codes/indentation and non-text values fail.
   Raw note/meta tokens and bytes outside edited tokens are separately compared against the backup.
   Explicit configuration entries do not waive protection of program identifiers.
2. Coverage: review native display candidates, unknown consumers and protected notes that might
   contain plugin-rendered text. Retain decisions for unchanged/excluded/uncertain strings. A whitelist
   narrows known candidates; inspect what it excludes too. CJK/kana and equality do not certify coverage.
3. Meaning: review dialogue in context for mistranslation, omission/addition, terminology, and speaker
   or pronoun errors. Record concrete source/path/context and decisions. Syntactic safety does not
   verify a review rationale or prove that a displayed name is unused as a plugin lookup key.
4. Rendering/runtime: launch the target build and test affected scenes, choices, plugin UI, fonts,
   edited images, relevant saves and mechanisms driven by touched carriers. For note-driven passive
   equipment/recovery, verify the actual stat/turn behavior. Record tests performed, tests not
   performed and results; unit tests or a static PASS cannot certify game-specific gameplay.


## Optional image acceptance

Image editing has two user decisions: approve the scope, then approve an original → translated
preview compare before batch processing or installation. Follow `image-redraw.md`; OCR is optional
and no recognition engine is bundled. The checks above supplement those decisions rather than
replacing them. Real-game visual and runtime acceptance remains separate from codec unit tests.

## Inventory contract

`audit_visible_jp.py --json-out` schema 2 exports all paired CJK-related leaves, including original/current
text, display visibility, `category` (display/program/editor/unknown), status and exact selectors.
`selector` is a list of RFC 6901 pointers; additional pointers explicitly enter JSON-encoded strings.
The readable `::<json>` marker is not itself a writable JSON path. Selectors need consumer/context
review and expected values; their presence is not permission to edit.

Safety checks are not language-filtered. Default auditing compares structure and known frozen program
fields even for ASCII-only changes. `--manifest` adds exhaustive approved-difference verification for
data JSON, including explicit configuration. `plugins.js` is inspected separately with its existing
parameter/identity checks; a data manifest does not cover plugin source, images or saves.

No data, malformed/duplicate JSON, structural/protection/choice failures or manifest mismatches make
`complete` false and return exit 1. Exit 0 describes the checks performed, not semantic completeness.
The text report samples candidates; it is not the full inventory. There is no semantic-quality scorer.

The writer, independent checker and acceptance commands are documented in `safe-patching.md`.
Reports must be outside input data directories. Directory digests bind a supplied backup, not its
historical authenticity. One-writer operation and retained backups are required; staging/rename is
not a power-loss-proof transaction or a live-game installation mechanism.
