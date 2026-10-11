# Image-text translation

Translate images within the user's selected scope. Ordinary text translation alone
is not image-edit permission. Apply standing scope/style decisions without repeating
approval questions. Record translated, retained, uncertain and unreviewed separately.

## Scope and source fidelity

| Use | Default for Mr.WAI |
| --- | --- |
| Story, skill/equipment descriptions, status, meaningful menu/quest information | Translate |
| Familiar English: Loading, Game Over, MISS, PRICE, SOLDOUT, simple navigation | Retain unless selected; accepted existing translations may stay |
| Simple readable posters, brands, cosmetic inscriptions, engine branding | Retain unless meaningful to understanding or selected |
| Stock BG/library signs | Retain; plot clues/navigation/objectives override this |

Decide from game context, not filenames, directories or presence of text. Inspect
custom portraits, sprites and tiles too. OCR is optional evidence: magnify and verify
characters, tags, questions/answers, parentheses, numbers, fees and symbols. Inspect
low-confidence candidates; record uncertain readings without inventing or deleting.
Re-read the actual sentence before excluding content on semantic grounds, including
whether it describes a current profile or a past recollection.

Keep game facts in one manifest, not per-game scripts or repeated inline programs.
Reuse existing tools and pristine backups. Prefer local removal and deterministic
text placement on restorable balloons/panels; generative redraw needs a demonstrated
reason and accepted sample because it may change art, layout or wording.

## Shared entry and task data

`scripts/image_workflow.py` handles decoded RGB/RGBA PNGs, solid or planar-gradient
restoration, typesetting, pixel checks and one generated compare. It needs Pillow and
an installed target-language font; it does not install dependencies, perform OCR or
reconstruct arbitrary texture. Encrypted containers use `scripts/encrypt_img.py` and
`text-map.md` separately.

Keep `images/manifest.json` as the input and `images/state.json` as generated results
and style approvals. `file` is below runtime `img/`; originals are backed up once in
`backup/img/<file>` and current outputs are `images/translated/<file>`. No executable
code in values. Replace this example's hash, transcription, geometry and font:

```json
{
  "schema_version": 1,
  "styles": {
    "panel": {"font": "C:/Windows/Fonts/msyh.ttc", "size": 18,
              "line_spacing": 24, "angle": 0, "restore": "solid"}
  },
  "assets": [{
    "file": "pictures/panel.png", "source_sha256": "<original PNG SHA256>",
    "decision": "translate", "reason": "Required story information",
    "source_verified": true, "alpha_policy": "preserve",
    "protected": [{"box": [200, 0, 320, 240]}],
    "regions": [{
      "box": [12, 12, 190, 100], "xy": [18, 18], "style": "panel",
      "source": "Visually verified original including all tags and remarks",
      "target": "完整译文（包括备注）", "lines": "完整译文（包括备注）",
      "color": [0, 0, 0, 255], "background": {"color": [255, 255, 255, 255]}
    }]
  }]
}
```

Boxes use exclusive right/bottom endpoints. Slanted boundaries can use
`polygon: [[x,y], ...]`. For `restore: "gradient"`, use region background
`{"samples": [[x0,y0,x1,y1], ...]}`: visually verified blank source areas spanning
both axes. The fitted RGBA plane cannot certify blank samples or reconstruct texture.
Retain/uncertain rows need file, source hash, decision and reason, without regions.

Measure erase regions inside the actual background and outside art, borders, tails,
rules and fees. Masks that recover a balloon interior may swallow decoration or
miss coloured/semitransparent text; verify them visually. Never use flat paint on a
gradient, clear semitransparent labels to zero alpha, or ignore meaningful colour.
`alpha_policy: "within_regions"` requires reviewed local alpha restoration.

Choose font/style before tuning positions. Check glyphs, fallback baselines and font
licensing before distribution; font subsets must include image translations too.
Use measured ink/cell bounds and semantic line breaks, not source row counts or font
size alone. Do not truncate meaning, split numbers/words/ellipses, or strand punctuation.

## Samples, approval and reuse

```sh
python -B <tool>/scripts/image_workflow.py plan --task <task>
python -B <tool>/scripts/image_workflow.py render --task <task> --sample --asset pictures/panel.png
python -B <tool>/scripts/image_workflow.py compare --task <task>
```

Repeat `--asset` for representative cases: long wording, coloured labels, framing,
slanted or transparent backgrounds. Show pristine/result at equal scale, magnified
regions, source/target including uncertainty, and font/layout changes. Inspect alpha
on light and dark backgrounds. A plain sample does not validate a different restoration.

After actual user approval, record the demonstrated style once:

```sh
python -B <tool>/scripts/image_workflow.py approve --task <task> --style panel --note "User accepted panel sample wording and appearance"
python -B <tool>/scripts/image_workflow.py render --task <task>
python -B <tool>/scripts/image_workflow.py check --task <task>
python -B <tool>/scripts/image_workflow.py compare --task <task>
```

Approval binds style configuration and font bytes; changed style needs an accepted
sample. Continue approved scope/method without per-batch questions. New wording and
coordinates need source/layout review. A materially different treatment needs a new
sample unless already covered by standing instructions. One compare is cheap to
regenerate; omit it after approval if requested. Retain uncertain/unrestorable art.

`reuse_from: "pictures/earlier.png"` reuses an earlier asset in the same batch only
when region configuration, format and editable source pixels match. Transfer only
those pixels; recipient art/fees remain original. Different editable backgrounds fail
and require independent rendering. Never transfer the whole image to an alias.

## Checks and delivery

Checks reject target/lines mismatch, common numeric/word/ellipsis splits, stranded
punctuation, missing-glyph rasters, clipping, overlapping regions, modified protected
or outside pixels and unapproved alpha changes. They cannot prove source transcription,
translation accuracy, region completeness, clean restoration or font aesthetics.
Inspect every edited source/result region for omissions, residue and wrong placement;
a hash or pixel count alone cannot establish those facts. Investigate unexpected
pixel changes rather than weakening protection with blanket damage tolerances.

Samples cannot be installed. Approved batch configuration/style/output hashes are
rechecked by the workspace installer; uncertain rows are listed and excluded, not
called translated. Encrypted delivery must round-trip through decoding and preserve
the approved pixels. Use `workspace.md` for installation/recovery/cleanup and
`release.md` for packaging. If scope changes to retain an already installed asset,
make rollback explicit. Keep current data/results and required backups; retire only
identified obsolete task artifacts, including temporary review crops. Inspect actual
scenes when possible; distinguish static checks, installation and runtime/user acceptance.
