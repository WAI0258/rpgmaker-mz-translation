# Plugin parameter repair

## Symptom

One of:

- The game fails to start with `TypeError: param.match is not a function` (or another
  `... is not a function`) pointing at a plugin's parameter parser.
- `js/plugins.js` has grown far beyond its original size — from hundreds of KB to tens of MB.

## Cause

`js/plugins.js` stores each plugin's parameters as a map, and **every value must be a string**. This
is an engine contract. A translation or rewrite script that writes a non-string value (a list, tuple,
number, dict) breaks it:

- The plugin receives an array or object and calls a string method on it → startup crash.
- If the bad value is later passed through `str()`, the next run wraps the previous repr, and repeated
  runs nest further. A single parameter can grow past 100 MB.

## Damage shapes

A value that should be a string becomes a two-element list `[original, boolean]`, where the boolean is
a "translated yet?" marker:

```
"NeedPriceText": "手数料："          # correct
"NeedPriceText": ["手数料：", false] # damaged
```

With nesting, the outer layers are Python `str()` reprs:

```
['(\'(\\\'{"hit":"命中率",...}\\\', True)\', False)', False]
```

## Exemptions

`__collapsed` is an editor fold marker whose value is legitimately a list, for example `["Name"]`.
Never treat it as damage and never rewrite it.

## Diagnosis

1. Locate the plugin that owns the failing method:

   ```
   grep -n "param\.match" js/plugins/*.js
   ```

   A hit in a generic parameter caster (`cast(param, type)`, `predict(param)`) means the value type is
   wrong, not that the plugin code is broken.

2. Ignore `debug.log` host noise such as `CreateFile: cannot find the file` and GPU errors. Those come
   from the NW.js host and are unrelated to the crash. The real error appears in the in-game dialog.

3. If intermediate artifacts remain, use timestamps to localise the writing step. A clean intermediate
   artifact plus a damaged `plugins.js` places the fault in the write-back step, not extraction.

## Repair

```
# dry run — report only
python scripts/fix_plugin_params.py --plugins <js/plugins.js> --backup <backup/js/plugins.js> --dry-run

# repair — writes a temporary file, re-reads it, installs only if the structural diff is zero
python scripts/fix_plugin_params.py --plugins <js/plugins.js> --backup <backup/js/plugins.js>
```

The repair unwraps `[value, boolean]` containers until a plain string remains. Two forms exist and
both must be unwrapped:

- **pair** — an actual list/tuple `[value, boolean]`.
- **repr** — a string holding a Python tuple repr, `"('value', True)"`, restored with `ast.literal_eval`.

Built-in safety constraints — do not bypass them:

- Only unwrap two-element containers whose second element is a boolean. A legitimate JSON array
  parameter such as `["a","b","c"]` has length 3 and a non-boolean second element, so it is untouched.
- Never touch `__collapsed`.
- Reuse the original backup's header, footer and serialisation format; order keys as the original does.
- Install only when the structural diff against the backup is zero. Otherwise keep the working file.
- Save the damaged version separately (`.broken`) before writing.

## Verify

```
node scripts/verify_plugins_js.js --plugins <js/plugins.js> --backup <backup/js/plugins.js>
python scripts/fix_plugin_params.py --plugins <js/plugins.js> --check
```

Expect `RESULT: OK`. `verify_plugins_js.js` re-implements the plugin's `cast()` / `predict()` against
every nested parameter to confirm `param.match` can no longer be reached with a non-string value.

## Prevent

Add three fail-closed guards to whatever writes `plugins.js`. Any one failing means nothing is written:

1. Any translation value that is not a string → abort.
2. Any parameter value read back that is not a string → abort. Never paper over it with `str()`.
3. Before writing, re-check every parameter value's type → abort on any non-string.

Reference implementation:

```python
NON_STR_ALLOWED = {"__collapsed"}

def non_string_params(arr):
    return [(p["name"], k, type(v).__name__)
            for p in arr for k, v in (p.get("parameters") or {}).items()
            if not isinstance(v, str) and k not in NON_STR_ALLOWED]

bad = [i for i in items if i.get("dst") and not isinstance(i["dst"], str)]
if bad:
    return 2

raw = p["parameters"][field]
if not isinstance(raw, str):
    return 2

if non_string_params(arr):
    return 2
```

## Checklist

- [ ] Is `plugins.js` a normal size (typically hundreds of KB)?
- [ ] Which plugin owns the failing method? Is it a generic parameter parser?
- [ ] Is the `debug.log` error NW.js host noise?
- [ ] Can an intermediate artifact timestamp the bad write?
- [ ] Does `verify_plugins_js.js` report `RESULT: OK` after repair?
- [ ] Are the three write guards in place at the source?
- [ ] Are stale one-off repair scripts still present in the project? Route future work through the
      guarded pipeline only.
- [ ] Are redundant damaged copies (`.broken`, `_backup/plugins.js`) still consuming disk? Remove them
      once verified.

## Notes

- Repair requires a pristine backup of `plugins.js`. If none exists, stop and ask for one.
- `data/*.json` can suffer the same contamination. Apply the same reasoning, but compare structure
  against the backup first — nested arrays are normal in `data/`, so a false positive is costly.
