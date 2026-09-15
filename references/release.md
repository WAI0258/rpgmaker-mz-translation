# Release cleanup

## Goal

Ship a build as clean as the original release. Every artifact created by the translation work must be
gone, and nothing that belongs to the game or to the user may be removed.

Run this step before any delivery or packaging. It is part of the pipeline, not an optional tidy-up.

## Delete

| Category | Examples |
|---|---|
| The translation working directory, in full | scripts, batches, backups, reports, term tables, intermediate JSON |
| Extraction / translation / audit scripts | `*.py`, `*.js` written for this job |
| Intermediate artifacts and reports | `*_dump.json`, `*_map.json`, `*.txt` reports, `*.html` reports |
| Hand-written notes | `*.md` added during the work |
| Temporary backups inside the data tree | `data/*.bak`, `*.broken`, `*.orig` — only after validation has passed |
| Runtime logs produced during the work | `debug.log` and similar (the engine regenerates them; deleting is harmless) |

## Keep

- **Every original game file**: executables, libraries, `*.pak`, `index.html`, `package.json`, shipped
  fonts, and all resource directories.
- **Files the translation added that the build requires**: the target-language font subset, referenced
  by `System.json` → `advanced.mainFontFilename`. Removing it renders the translation as blank boxes.
- **The translated `data/*.json` and `js/plugins.js`** — content is now in the target language, but
  file names and structure must remain byte-for-byte structurally identical to the original.

## Never touch

- **Launcher and injection files belonging to the user's own tooling.** If the user launches the game
  through a third-party loader (for example MTool), the files it generated — launch `.bat` files,
  injected DLLs, path markers, locale loaders — are the user's, not the project's. Skip them. Deleting
  them breaks the user's workflow.
- **Agent memory directories** (for example `.workbuddy/`, `.claude/`). Unrelated to the game; exclude
  when packaging rather than deleting.

## Verify

1. Walk the whole tree for `*.bak`, `*.tmp`, `*.py`, `*.md`, `*.log`, and any `_`-prefixed directory.
   Compare against the keep list. Expect zero hits.
2. Confirm `data/` and `js/` file names and structure match the original exactly.
3. Launch `Game.exe`. Confirm it starts, text renders correctly, and no error dialog appears.
4. Read a save from before the translation. Confirm frozen text was handled or is understood to be
   out of scope.

## Delete safely

Prefer the OS recycle bin, or rename to a `.del` suffix and remove after confirmation. Translation
working directories often hold the only pristine copy of the original files — an irreversible delete
destroys the rollback path.

Bulk deletions may be intercepted by the platform's own bulk-delete guard above a threshold. Split
into smaller batches or let the user confirm.
