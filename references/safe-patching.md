# Safe path patches — v1.2

Use the bundled writer for `data/*.json` instead of creating a per-game global replacement script.
It creates a new working data directory and never overwrites an existing directory. Plugin source,
`js/plugins.js`, images and saves remain separate carriers with their own validators; this writer
handles top-level data JSON files, including JSON strings inside event arguments/custom data.

## Workspace mode

Translation tasks use `translation_workspace.py init --game <game>` and the resulting
`workspace.json`. The initializer captures pristine backups and independent initial
copies; read `workspace.md` for paths and boundary checks. Keep the reviewed manifest at
`text/patch.json`. Describe/preflight/write/verify/audit then require only `--task <task>`:

```sh
python -B <tool>/scripts/apply_translation.py --task <task> --describe
python -B <tool>/scripts/apply_translation.py --task <task>
python -B <tool>/scripts/apply_translation.py --task <task> --write
python -B <tool>/scripts/verify_untouched.py --task <task>
python -B <tool>/scripts/audit_visible_jp.py --task <task>
```

The explicit-path examples below also support independent use; they do not enforce a
single workspace boundary. Do not mix them into task mode to bypass a rejected path.

## Workflow

1. Keep a pristine data backup outside the build. Inspect the active plugins and classify candidates
   as display, program input, editor information or unknown. Display status alone does not prove that
   a plugin never uses the same value as a lookup key.
2. Draft translations by context and position. Do not key the write plan only by source text; two
   equal strings may need different targets, or only one may be editable. Keep unchanged decisions
   and uncertain/excluded candidates in a separate decision record.
3. Obtain the source snapshot and file digests, read-only:

   ```sh
   python -B <tool>/scripts/apply_translation.py --source <backup/data> --describe
   ```

   Build the manifest below from this output. Keep it outside both data directories. Native display
   translations do not need thousands of individual user approvals; the Agent reviews the context.
   Non-native candidates need a concrete consumer review, not merely "looks like Japanese".
4. Preflight all files and patches (default is dry-run):

   ```sh
   python -B <tool>/scripts/apply_translation.py --source <backup/data> --manifest <patch.json> --output <work/new-data>
   ```

5. Add `--write` after review. The output directory must not exist and its parent must already exist.
   All documents and patches are validated before staging. The staged directory is independently
   checked and renamed into place only after verification. The source is rechecked for changes.
6. Verify the result independently and run the coverage/choice audit:

   ```sh
   python -B <tool>/scripts/verify_untouched.py --current <work/new-data> --backup <backup/data> --manifest <patch.json>
   python -B <tool>/scripts/audit_visible_jp.py --current <work/new-data> --backup <backup/data> --manifest <patch.json> --out <work/audit.txt> --json-out <work/inventory.json>
   ```

7. Review meaning and rendering. Install only the checked working copy, retaining live versions and
   backups. Stop if live data has diverged from the expected version; the writer is not an installer.
   Test the actual affected scenes/mechanics before claiming runtime acceptance.

## Manifest

```json
{
  "schema_version": 1,
  "source_sha256": "<complete data snapshot digest from --describe>",
  "files": [
    {
      "file": "Armors.json",
      "sha256": "<file digest from --describe>",
      "changes": [
        {"path": "/1/name", "old": "MPRate:10", "new": "MP恢复:10"}
      ]
    }
  ]
}
```

Digest placeholders must be replaced by actual lowercase 64-character SHA256 values. `files` contains
only edited files, but the snapshot digest binds **all** top-level JSON files and their names. It is
computed in sorted filename order from UTF-8 basename + NUL + binary file SHA256. Digests bind the
selected backup; they do not establish that an arbitrary backup is genuinely pristine.

Paths are [RFC 6901 JSON Pointers](https://www.rfc-editor.org/rfc/rfc6901): escape `~` as `~0` and `/`
as `~1`. Array indices are zero-based, with no leading zeros. No path evaluation code is executed.
A patch selects an existing scalar and must preserve its type and match `old` exactly. It does not
add/remove keys, reorder arrays, replace containers or change identifiers. Equal old/new values belong
in the decision record, not in the patch. Duplicate/conflicting selectors fail.

## Encoded JSON and consumer review

For an event parameter that contains serialized JSON, give an explicit list of pointers:

```json
{
  "path": ["/1/list/0/parameters/3", "/rows/0/text"],
  "old": "Continue",
  "new": "继续",
  "review": "Enabled PluginName.set passes args.rows[0].text to its text renderer; sibling resource keys are identifiers"
}
```

The first pointer selects an outer string. Decode it as JSON, then resolve the next pointer inside
it. More strings require more pointers. Inventory `selector` already exports this form; the readable
`$[...]::<json>` path is not an ordinary JSON Pointer. Use the original value, not the inventory's
current translated value, as `old` when preparing from a pristine backup.

Unknown/editor candidates require a nonempty `review` identifying their consumer and why the value
is safe to translate. This record is not a proof automatically checked against JavaScript; the Agent
must inspect the enabled consumer. Opaque JSON argument strings cannot be replaced wholesale to
bypass leaf checks. Literal JSON-looking **native dialogue** is ordinary displayed text, not an
implicit decoding boundary.

The writer changes only the selected raw value token. Nested JSON is patched inside the decoded
string before that one outer token is re-encoded. Bytes outside selected tokens, and unmodified
inner tokens, must survive. This preserves BOM, surrounding spacing, key order, line endings and
trailing newline; the edited token's escape spelling may change.

## Program data and explicit configuration

`note`/`meta` subtrees, known resource fields, IDs, event command structure and command/label
identifiers are frozen even if a manifest tries to approve them. A plugin may render text stored in
notes; record that consumer and use a dedicated reviewed plugin-specific procedure. This generic
writer intentionally provides no broad note override. Do not mistake default protection for proof
of invisibility or translation completeness.

Configuration changes such as a font filename or size require separate entries with
`"kind": "config"` and a concrete `review`. Each entry selects one existing scalar, matches its
old value and preserves its type. There is no "allow all numeric changes" exemption. Frozen program
fields cannot be changed through this configuration option.

Translation entries preserve control-code and `%1`-style placeholder tokens/counts; ruby base text
may change while its directive and reading remain. Check their placement and any plugin-specific
syntax separately. Choice labels and their indexed branch labels must be patched together.

## What verification establishes

- Strict JSON rejects duplicate object keys, invalid UTF-8, nonstandard constants and ambiguous paths.
- The independent checker compares every parsed difference to the manifest, including type changes,
  extra/deleted keys, event `code`/`indent`, non-string values and unexpected string changes.
- Raw note/meta tokens are compared separately; semantic equality is not called byte equality.
- Bytes outside approved tokens must match; nested payloads undergo the same diff and byte checks.
- Every declared change must actually be applied. Missing files, empty directories, self-comparison,
  wrong digests, stale old values or conflicting patches fail. Zero note fields can be legitimate and
  is reported as zero, not automatically treated as success or failure.

Without `--manifest`, `verify_untouched.py` requires an exact copy of the backup; it does not approve
arbitrary translations. The auditor without a manifest checks structure and known frozen fields,
while retaining language-filtered coverage candidates. Only `--manifest` enables exhaustive approved
change verification. Reports must be outside the data inputs and must not overwrite the manifest.

The writer publishes a new directory, not a multi-file live-game transaction. Use one writer and no
concurrent source/output edits. Filesystem races, power loss and unknown plugin behavior are outside
the guarantee; a static pass does not substitute for actual gameplay and visual checks.
