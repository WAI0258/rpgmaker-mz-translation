# Patch delivery and cleanup

Deliver a playable build or a selective patch containing only changed/runtime-required
files, or install the reviewed changes directly when approved. Keep the external translation workspace, pristine backups and decision records
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

1. For a delivery artifact, prepare it under workspace `build/`. For approved direct
   installation, use the reviewed current outputs without another complete game copy.
   Review the selected file list; exclude workspace artifacts.
2. Validate JSON/plugin parameters and the actual patch contents, including font references.
3. Test the selected runtime target when available; a full clone is not mandatory.
   Honour approved direct installation with changed-file backups, full source/target
   preflight and post-write verification. Record actual observations or user acceptance;
   static checks do not establish runtime acceptance.
4. Check compatibility with prior saves when in scope; do not modify player saves implicitly.
5. Retain the workspace and rollback files unless the user separately requests cleanup.


Use the shared installation/recovery/cleanup commands in `workspace.md` for supported
carriers. Preserve their manifest/journal rather than adding per-game delivery scripts.
Use one current report for installed, retained, cleaned and unresolved results.
