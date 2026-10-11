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
It does not overwrite backups or working files. A recorded installed version or pending
install/rollback is recognized through `reports/install_state.json`. An unrecorded change stops resumption;
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

## Reuse and artifact lifecycle

Resume and reuse task data and tools before extracting or writing helpers. Keep one
current build/report set; validate replacements before retiring obsolete task-owned
trials. Preserve required backups and user files. Image workflow details belong in
`image-redraw.md`; packaging and general cleanup boundaries belong in `release.md`.

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

## Selective installation, recovery and cleanup

For supported top-level data JSON, `js/plugins.js` and decoded `img/*.png`, use the
same workspace entry. Plugin changes still need their separate syntax/semantic review;
this entry does not certify arbitrary plugin edits. Encrypted images, plugin source,
fonts and saves require their carrier-specific procedure; do not rename them to bypass
the path whitelist. The accepted game from an older manual workflow is not automatically
adopted into a new install journal; inspect and preserve its existing evidence.

```sh
python -B <tool>/scripts/translation_workspace.py plan-install --task <task>
python -B <tool>/scripts/translation_workspace.py install --task <task>
```

`plan-install` reuses full JSON difference verification and approved image checks,
then writes one `reports/install_manifest.json`: runtime-relative path, workspace
output/backup and source/target SHA256 for each changed file, plus the data patch manifest
reference. Installation rechecks current data/image/style configuration and plugin
structure; a saved list cannot bypass subsequent changes. For a revised data build,
pass `--current <build/data> --manifest <text/patch.json>`. It does not create a full
game copy. Inspect this concrete list and use existing installation authorization,
or obtain it when absent. Then:

```sh
python -B <tool>/scripts/translation_workspace.py install --task <task> --write
python -B <tool>/scripts/translation_workspace.py rollback --task <task>
python -B <tool>/scripts/translation_workspace.py rollback --task <task> --write
```

Install/rollback without `--write` only preflight. Every selected source, backup,
output and live file is checked before any game write. Writes replace individual
files atomically and verify hashes; the multi-file operation is **not** atomic.
A pending journal precedes the first write. After interruption, resume the same
installation plan or run rollback; finish a pending rollback before a new install.
External edits refuse both operations. Rollback returns all journaled files to
pristine backups, not the previous translation revision. Stop the game while writing.

New successful installs keep a cumulative record of earlier installed files. Omitting
an earlier entry does not revert it; if scope changes to retain an installed original,
make that rollback explicit. After a complete rollback, a partial install keeps other
files pristine. Keep the journal and backups; a missing journal makes a changed game
unrecognized, rather than silently rebasing the original snapshot.

```sh
python -B <tool>/scripts/translation_workspace.py clean --task <task>
python -B <tool>/scripts/translation_workspace.py clean --task <task> --write
```

Cleanup is deliberately narrow: only image outputs retired into the image state's
obsolete list, inside `images/translated`, with their recorded hashes unchanged.
It refuses current outputs, active installation artifacts, backups and outside paths.
It leaves unregistered/user files alone. This is not a general recursive build/cache
deletion command; inspect older task-owned trials before separately approved cleanup.

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

Choose the runtime/delivery target from the user's request. A full independent game copy
is optional, not the default: prefer a selective patch or approved direct installation
when duplicating runtime assets has no concrete benefit. If requested/justified, keep
one full copy under `build/`; never launch source-only data. Check save/log destinations.
Record actual runtime observations or user acceptance, not just static checks or a
running process. If tool/security policy blocks testing, report the limitation without
adding a server, alternate browser or game clone to bypass it.

Task-mode scripts validate resolved paths, including existing symlinks/junctions, before
writing. They do not provide an OS sandbox or defend against another process replacing
paths concurrently. Standalone explicit-path calls remain available; they do not enforce
this workspace boundary. Use task mode for the translation workflow.
