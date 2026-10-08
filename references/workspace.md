# Translation workspace

A translation task has one artifact root, outside both the game and the skill directory.
The default is a sibling of the selected game: `<game-directory-name>_translation_work`.
The user supplies the game and target language; the Agent initializes the workspace.
Read-only location/audit questions do not authorize initialization or a full translation.

## Initialize or resume

Use absolute tool/game paths and Python `-B`:

```sh
python -B <tool>/scripts/translation_workspace.py init --game <game>
```

The default target is `zh-CN`; use `--target-language <language>` for a different target.
Use `--workspace <absolute-path>` only when the user chooses a different artifact root.
The parent directory must exist. Root-level and `www/` MV/MZ layouts are recognized by
core filenames; this detects the engine family, not its version or plugin semantics.
Ambiguous/custom layouts fail rather than guessing. Inspect the actual core for versions.

The initializer prints the absolute `workspace.json` task path. It captures top-level
`data/*.json` and `js/plugins.js`, with byte digests, and creates independent initial
working copies. It never writes into the game. Other carriers must be backed up under
`backup/` before editing, preserving their runtime-relative paths. They are not included
in the initial data/plugin digest ledger; validate them separately.

Re-running initialization validates task/game/target identity and pristine backups.
It does not overwrite backups or working files. A changed live game stops resumption;
inspect the difference instead of rebasing backups silently. An existing unrelated or
incomplete directory is refused; preserve it for inspection or choose a new directory.
`show --task <workspace.json>` validates and prints the stored task without requiring
live data equality, allowing inspection/recovery from the preserved snapshot.

## Locations

| Path under the workspace | Purpose |
| --- | --- |
| `workspace.json` | Game identity, target language and initial backup digests |
| `backup/` | Pristine originals; never use as report/output destinations |
| `text/` | Glossary, translations, decisions and `patch.json` |
| `images/` | Decoded images, OCR, redraws and original/preview compares |
| `build/source/data/` | Independent initial data copy for extraction |
| `build/js/plugins.js` | Working plugin parameters |
| `build/translated/data/` | Default data output, created only by a successful write |
| `build/` | Additional checked builds and distributable patches |
| `reports/` | Audit, inventory, validation and delivery reports |
| `tmp/` | Temporary files and configurable caches |
| `progress.md` | One task checkpoint and links to current artifacts |

Do not create per-game scripts, logs or translations in the tool directory, game tree,
Agent memory directories or another ad hoc artifact root. Client-owned internal state
is controlled by the client, not this skill; do not add translation artifacts there.

## Task commands

Pass the returned task path to the bundled audit/writer/verifier. Relative overrides are
resolved from the workspace, never the caller's current directory. The task source/backup
is fixed to `backup/data`; overrides cannot escape the root or write into backups, the task
configuration or the default patch manifest. Existing hard-linked output files are refused.

```sh
python -B <tool>/scripts/audit_visible_jp.py --task <workspace.json>
python -B <tool>/scripts/apply_translation.py --task <workspace.json> --describe
```

The audit writes `reports/audit.txt` and `reports/inventory.json`, including the working
plugin parameters. Before a translated data directory exists, it reads `build/source/data`.
`--describe` prints digests read-only; save them under `reports/` if needed.
Draft the reviewed manifest at `text/patch.json`, following `safe-patching.md`, then:

```sh
python -B <tool>/scripts/apply_translation.py --task <workspace.json>
python -B <tool>/scripts/apply_translation.py --task <workspace.json> --write
python -B <tool>/scripts/verify_untouched.py --task <workspace.json>
python -B <tool>/scripts/audit_visible_jp.py --task <workspace.json>
```

The verifier writes `reports/verify.json`. Audit and verification automatically use the
manifest for the default translated directory; a missing manifest fails instead of
silently running partial checks. Without translated data, verification requires exact
initial-copy equality. For another build, specify both `--current` and `--manifest`.

The writer requires a new output directory. After revising the plan, choose another output
under `build/`, for example `--output build/revision-2/data`, and create its parent first.
Pass that current directory and manifest to both checks. Never patch an accepted build
incrementally or overwrite it merely to make the default command run again.

## Other tools and runtime checks

The runner supplies workspace cwd and child-process temporary/cache settings:

```sh
python -B <tool>/scripts/translation_workspace.py run --task <workspace.json> -- <command> <arguments>
```

It sets `TMPDIR`, `TEMP`, `TMP`, `XDG_CACHE_HOME`, pip/npm caches and disables Python
bytecode for that child. It does not alter user/system settings. Use absolute tool paths
and explicitly select outputs under the workspace for other bundled scripts and external
tools. Check their actual cache/output behavior; environment settings are not a sandbox.
If a required tool cannot keep its artifacts here, stop and explain before using it.

For gameplay testing, prepare an independent complete game copy under `build/`, including
its runtime assets. Do not launch the source-only data copy. Check where the game/launcher
writes saves and logs before running; some external programs ignore cwd/temp settings.
Do not claim runtime acceptance when only static checks ran.

Images still require scope and compare approval. Before installing any files into the
original game, show the changed-file list and get approval; recheck expected live originals.
Retain backups in this workspace. Exclude the workspace from deliveries; do not delete it
as part of packaging.

Task-mode scripts validate resolved paths, including existing symlinks/junctions, before
writing. They do not provide an OS sandbox or defend against another process replacing
paths concurrently. Standalone explicit-path calls remain available; they do not enforce
this workspace boundary. Use task mode for the translation workflow.
