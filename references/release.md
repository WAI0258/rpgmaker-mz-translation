# Patch delivery and cleanup

Deliver a playable build or a selective patch containing only changed/runtime-required
files. Keep the external translation workspace, pristine backups and decision records
for recovery; exclude them from deliveries. Packaging never authorizes their deletion.

## Include

- Checked translated game files, preserving required filenames and data structure.
- Fonts or other assets added by the translation that the game references.
- For a complete build, every required original runtime file and resource.
- Concise installation instructions appropriate to the delivery format.

## Exclude

- The translation workspace: backups, intermediate data, manifests, scripts, logs,
  reports, glossary and image compares.
- Agent memory directories such as `.workbuddy/` and `.claude/`.
- Temporary files created by this task, identified from its records rather than merely
  by an extension or filename prefix.

## Preserve user files

Do not delete original documentation, launchers, saves, libraries or third-party tooling
such as locale loaders and injected DLLs. A shipped `.js`, `.md`, `.py`, `.log` or
underscore-prefixed directory is not evidence that a file belongs to this task.
Never sweep the game directory with extension-based or prefix-based deletion rules.

If earlier work left task artifacts in the original game, identify exactly which files
were created by that work. Propose moving them into the workspace, check resolved source
and destination paths, and obtain authorization before changing the original tree.

## Verify

1. Build the delivery under workspace `build/`; review its file list against the task's
   changed-file list and required assets. Confirm no workspace artifacts are included.
2. Validate JSON/plugin parameters and the actual patch contents, including font references.
3. Test an independent full game copy when runtime testing is available; record launch,
   text rendering and affected gameplay checks, or state which were not performed.
4. Check compatibility with prior saves when in scope; do not modify player saves implicitly.
5. Retain the workspace and rollback files unless the user separately requests cleanup.
