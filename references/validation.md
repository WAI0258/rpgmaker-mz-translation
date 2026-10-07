# Evidence and validation boundaries — v1.1

The tool version is v1.1, independent of the engine version. Inspect the target game's core and
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

## Four independent acceptance checks

1. Structure: file set, keys, types, list lengths, non-text values and choice indices remain intact.
   Expected configuration changes must be reviewed separately; the auditor conservatively flags them.
2. Coverage: review native display fields and every unknown field/consumer. Track approved unchanged
   terms and unknown plugin metadata; backup equality or kana alone cannot certify completeness.
3. Meaning: review dialogue in context for mistranslation, omission/addition, terminology, and speaker
   or pronoun errors. Record the concrete source/path/context and decision, rather than a vague score.
4. Rendering/runtime: launch the target build; test choices, plugin UI, fonts, edited images on light
   and dark backgrounds, and relevant saves. Unit tests cannot certify those game-specific paths.

## Optional image acceptance

Image editing has two user decisions: approve the scope, then approve an original → translated
preview compare before batch processing or installation. Follow `image-redraw.md`; OCR is optional
and no recognition engine is bundled. The checks above supplement those decisions rather than
replacing them. Real-game visual and runtime acceptance remains separate from codec unit tests.

## Inventory contract

`--json-out` exports all paired CJK-related leaves, including changed translations, original/current
text, visibility (`true` native display, `false` native editor/identifier, `null` unconfirmed), status,
and exact file/path selectors. Unknown plugin arguments are never automatically deemed display text.
`::<json>` is a virtual decoding boundary, not an ordinary writable JSON path: re-encode outer strings
after modifying a leaf. Translation context must supplement selectors; selectors alone do not resolve
meaning. No-match, malformed input and structural errors make `complete` false and return exit 1.
`complete` describes audit execution only. The text report samples candidates; it is not a full
translation table. There is no built-in source/target patch applier or semantic-quality scorer.
