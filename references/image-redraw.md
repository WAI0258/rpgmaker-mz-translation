# Optional image-text translation

Text baked into a bitmap is a separate translation pass. Use this procedure only when inspection
finds text that needs translation and the user chooses to process it. Ordinary dialogue or database
translation does not authorize image editing. Images the user chooses to retain stay unchanged;
record that scope when reporting completion.

This workflow was learned from a game's custom balloons and status panels. It does not bundle an
OCR engine or a universal redraw script. OCR is optional: visual transcription and measured regions
may be sufficient. The encryption helper only handles the container, not recognition or translation.

## 1. Inspect and ask about scope

Inspect copies of the assets, decrypting to a work directory where needed. Do not overwrite game
files. Report the actual candidate files/groups and their uses, with thumbnails when useful.
Offer **leave unchanged / translate selected groups / translate all confirmed text**. Let the user
choose title logos and art lettering separately from ordinary UI labels.

- Check custom assets even in sprite, portrait or tile directories. Directory names and component
  counts cannot establish that an image contains no text.
- OCR boxes, scores and geometry are candidate hints. Retain detection results for review; do not
  discard a possible label solely because its confidence is low. Inspect skipped candidates too.
- Read text at magnification and in game context. Verify OCR transcriptions and symbols visually;
  record uncertain readings rather than inventing a translation.
- Engine defaults, English labels and digits are not automatically translation targets. Decide from
  the source/target languages and the user's scope, rather than assuming a fixed number of images.

**Wait for the user's scope decision before making translation samples.** If the user declines,
record the decision and continue the other translation work.

## 2. Make a compare and obtain approval

Back up each selected original outside the game/build tree before editing and record its checksum.
Keep the pristine source and translated output separate. Read the original from that backup whenever
rendering a compare; never label an already edited image as the original.

Choose samples that represent the methods needed in the approved scope: plain labels, balloons,
framed panels, semi-transparent backgrounds, or title art where applicable. Include difficult cases
such as long translations, coloured labels and symbols. One easy sample does not cover a different
background or layout family.

For each sample, show:

- The original and translated preview side by side at the same scale, plus magnified text crops.
- The source transcription and proposed translation, including any uncertainty or omitted text.
- Font, size, line breaks and colours; point out changes to positioning or art style.
- RGBA previews on both light and dark backgrounds when transparency is involved.

Samples belong only in the work directory. Ask the user to approve the wording, font, layout and
appearance, or revise/retain the original. **Approval to inspect or make a sample is not approval to
batch redraw or install. Wait for approval of the compare before either action.** Record the accepted
samples, file groups and style. A newly discovered image family or material style change needs a
supplementary compare and approval before processing it.

If the reading is uncertain, the backdrop cannot be restored reliably, or art lettering cannot be
matched adequately, explain that limitation in the compare and offer to retain the original.

## 3. Redraw within the approved scope

Work from pristine copies using the accepted samples as the visual reference. Keep a per-file record
of source text, translation, label regions and deliberate unchanged labels. Do not mix translation
passes based on different source snapshots.

### Choose the method from the actual background

| Asset family | Suitable approach | What must be protected |
|---|---|---|
| Text inside a uniform balloon | Recover the interior, restore the backdrop, then typeset | Outline, tail, neighbouring art |
| Framed status/profile panel | Restore only the selected label regions; lay out in measured cells | Rules, badges, other labels |
| Semi-transparent panel | Restore the local RGB **and alpha**, then composite text | Backdrop opacity and colours |
| Text over textured art or a logo | Use a restoration/art method demonstrated in the approved sample, or retain | Texture, shading, lettering style |

Thresholds and margins must be measured for the asset. A technique that works for a white balloon
is not a general eraser for panels or artwork.

### Locate and restore

- Measure label coordinates from the original; store boxes outside the rewriting logic. An expected
  label region with no detected ink needs review, not silent skipping.
- A light-interior mask has holes where dark text lies. Hole filling can recover a simple enclosed
  balloon interior, but inspect the result before using it: a hole may be intentional decoration.
- Keep erase regions inside the verified interior and outside protected borders. Intersecting a
  padded row region with the interior can work for a uniform balloon; blindly dilating the whole
  shape can damage slanted edges.
- Separate text and rules in panels. An over-dilated rule mask can swallow descenders or collapse
  the usable cell. Measure the cell from the original geometry and inspect the resulting protection
  mask. Centre text in the intended cell, not across a separator or an arbitrarily selected cell.
- Detect coloured and semi-transparent strokes too. Dark/opaque-only thresholds can miss them.
  Preserve semantic colour coding; leave approved identical labels pixel-for-pixel unchanged.
- Restore the actual local backdrop, including RGB and alpha. Clearing a semi-transparent label
  to alpha zero creates holes; painting opaque white also changes the backdrop. A modal alpha alone
  cannot distinguish every text stroke from its background. Use verified neighbouring backdrop
  samples for uniform regions; use the approved restoration method for non-uniform ones.

### Font and layout

Choose the typeface before tuning layout, using the approved sample and source style. A game font
is a candidate only if it covers the translation and fits the artwork; check availability and the
license before distributing any font. Dropping a plain font onto gradient/stroked logo lettering
may change the artwork substantially and requires the user's decision.

- Verify glyph coverage for all translated characters, punctuation and symbols. If building a font
  subset, include every image translation table as well as JSON text. Register newly added tables.
- Inspect fallback symbols for mismatched size or baseline. Choose a suitable supported fallback;
  do not silently replace a symbol or punctuation with a different one merely to make it fit.
- Measure rendered ink and effects, not font size or advance alone. Use actual cell/interior bounds
  and approved margins; a short source line's blank space is not a suitable padding rule.
- Prefer semantic line breaks. Check that the laid-out text preserves the complete translation,
  accounting only for deliberate layout breaks. Never truncate lines to fit a slot.
- Adjust wrapping or font size within the approved style. A shorter translation must preserve meaning
  and be reviewed. Large source line spacing does not justify enlarging a small UI label.

## 4. Validate, then install

Before installing any batch:

1. Open every edited image and inspect magnified source/result regions for misread text, omission,
   residue, clipping, incorrect slots and colour changes. Compare against the accepted style.
2. Assert dimensions and intended image mode are preserved. Check complete translation text and
   rendered ink against its assigned region. Fixed labels use measured original slots; re-segmented
   row counts are unreliable when taller target glyphs join neighbouring rows.
3. Compare protected frame/art pixels with the pristine source. Check pixels outside authorized edit
   regions remain unchanged. Treat unexpected differences as failures, rather than allowing an
   arbitrary silhouette tolerance that could hide border damage.
4. Inspect transparent results on light and dark backgrounds. Pixel counts or a white-only preview
   cannot certify that source strokes are gone or backdrop alpha is correct.
5. For encrypted assets, re-encrypt with the original key using `scripts/encrypt_img.py`, decrypt the
   output again, fully load the image, and compare decoded pixels with the approved working output.
   See `text-map.md` for the container format. Codec validation alone is not visual acceptance.

Install only the approved, validated outputs, retaining backups and the prior live versions. If live
files no longer match the expected originals, stop and review the conflict before replacing them.
Launch the game and inspect the edited assets in their actual scenes, including backgrounds, scaling
and plugin placement. Report any runtime verification that could not be performed.

Keep approval records, translation tables and compares outside the release build. Follow `release.md`
for packaging; retain the pristine backups separately. Report processed, deliberately retained and
unresolved groups separately, without calling unreviewed images fully translated.
