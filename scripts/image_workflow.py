#!/usr/bin/env python3
"""Reusable, declarative image translation: plan/approve/render/check/compare/delivery.

Pillow is required only for image commands. No OCR, automatic scope classification,
font download, generative redraw or game-specific executable code is performed.
"""
import argparse
import hashlib
import html
import json
import math
from pathlib import Path
import re
import io
from urllib.parse import quote

from json_safety import strict_loads, atomic_bytes, digest, inside, regular, write_json


def pillow():
    try:
        from PIL import Image, ImageChops, ImageDraw, ImageFont
    except ImportError as exc:
        raise ValueError('image commands need Pillow in the selected Python runtime; do not install it silently') from exc
    return Image, ImageChops, ImageDraw, ImageFont


def load_plan(task, manifest=None):
    path = task.path(manifest or 'images/manifest.json')
    regular(path)
    plan = strict_loads(path.read_text(encoding='utf-8'))
    if plan.get('schema_version') != 1 or not isinstance(plan.get('styles'), dict) or not isinstance(plan.get('assets'), list):
        raise ValueError('invalid image manifest')
    seen = set()
    for asset in plan['assets']:
        name = asset['file']
        if (not isinstance(name, str) or '\\' in name or ':' in name or Path(name).is_absolute() or
                '..' in Path(name).parts or name != Path(name).as_posix() or not name.endswith('.png')):
            raise ValueError('image file must be a relative decoded PNG path below img/')
        if name.casefold() in seen:
            raise ValueError('duplicate image file')
        seen.add(name.casefold())
        if asset.get('decision') not in ('translate', 'retain', 'uncertain') or not asset.get('reason', '').strip():
            raise ValueError('each image needs a scope decision and reason')
        task.image_source(name, asset.get('source_sha256'))
        if asset['decision'] == 'translate' and (asset.get('source_verified') is not True or not asset.get('regions')):
            raise ValueError('translation needs verified transcription and measured regions: ' + name)
    return plan


def state(task):
    p = task.path('images/state.json')
    if not p.exists():
        return {'schema_version': 1, 'approvals': {}, 'results': {}, 'obsolete': []}
    regular(p)
    value = strict_loads(p.read_text(encoding='utf-8'))
    if (value.get('schema_version') != 1 or not isinstance(value.get('approvals'), dict) or
            not isinstance(value.get('results'), dict) or not isinstance(value.get('obsolete'), list)):
        raise ValueError('unsupported image state')
    return value


def style_hash(style):
    font = Path(style['font']).resolve()
    regular(font, allow_hardlinks=True)  # System fonts are read-only inputs, often hard-linked on Windows.
    return hashlib.sha256((json.dumps(style, sort_keys=True, ensure_ascii=False) + digest(font)).encode()).hexdigest()


def approve(task, plan, style, note):
    if not note.strip():
        raise ValueError('record the actual user approval')
    current = state(task)
    current['approvals'][style] = {'sha256': style_hash(plan['styles'][style]), 'note': note}
    write_json(task.output('images/state.json'), current)


def mask_for(size, regions):
    Image, _, Draw, _ = pillow()
    mask = Image.new('L', size)
    draw = Draw.Draw(mask)
    for region in regions:
        if 'box' in region:
            box = region['box']
            if len(box) != 4 or any(type(v) is not int for v in box):
                raise ValueError('boxes use integer exclusive endpoints')
            x0, y0, x1, y1 = box
            if not (0 <= x0 < x1 <= size[0] and 0 <= y0 < y1 <= size[1]):
                raise ValueError('box outside image')
            draw.rectangle((x0, y0, x1 - 1, y1 - 1), fill=255)
        elif 'polygon' in region:
            points = region['polygon']
            if len(points) < 3 or any(len(p) != 2 or any(type(v) is not int for v in p) or not (0 <= p[0] < size[0] and 0 <= p[1] < size[1]) for p in points):
                raise ValueError('invalid polygon')
            draw.polygon([tuple(p) for p in points], fill=255)
        else:
            raise ValueError('region needs a box or polygon')
    return mask


def wording(target, lines):
    if not isinstance(target, str) or not target or not isinstance(lines, str):
        raise ValueError('each region needs target and lines')
    if re.sub(r'\s', '', target) != re.sub(r'\s', '', lines):
        raise ValueError('typeset wording omits/adds content')
    offset = 0
    compact = re.sub(r'\s', '', target)
    boundaries = {len(re.sub(r'\s', '', target[:m.start()])) for m in re.finditer(r'\s+', target)}
    rows = lines.split('\n')
    for n, row in enumerate(rows):
        if not row or re.match(r'^[，。！？、：；）】%…]', row):
            raise ValueError('empty line or stranded punctuation/percentage/ellipsis')
        offset += len(re.sub(r'\s', '', row))
        if n + 1 < len(rows):
            left, right = compact[offset - 1], compact[offset]
            if (left.isdigit() and (right.isdigit() or right in '.%％')) or (left == right == '…'):
                raise ValueError('split number, percentage or ellipsis')
            if left.isascii() and right.isascii() and left.isalpha() and right.isalpha() and offset not in boundaries:
                raise ValueError('split word')


def solve(matrix, values):
    """Small least-squares plane; fail on inadequate/collinear background samples."""
    rows = [list(a) + [b] for a, b in zip(matrix, values)]
    for i in range(3):
        pivot = max(range(i, 3), key=lambda k: abs(rows[k][i]))
        rows[i], rows[pivot] = rows[pivot], rows[i]
        if abs(rows[i][i]) < 1e-9:
            raise ValueError('gradient background samples do not determine a plane')
        v = rows[i][i]
        rows[i] = [x / v for x in rows[i]]
        for k in range(3):
            if k != i:
                v = rows[k][i]
                rows[k] = [a - v * b for a, b in zip(rows[k], rows[i])]
    return [row[-1] for row in rows]


def backdrop(original, region, style):
    Image, _, _, _ = pillow()
    background = region['background']
    kind = style['restore']
    if kind == 'solid':
        colour = background['color']
        if len(colour) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in colour):
            raise ValueError('background colour must be RGBA bytes')
        return Image.new('RGBA', original.size, tuple(colour))
    if kind != 'gradient':
        raise ValueError('unsupported restoration; select a demonstrated solid/gradient style')
    samples = mask_for(original.size, [{'box': box} for box in background['samples']])
    width, height = original.size
    points = [(x / width, y / height, original.getpixel((x, y))) for y in range(0, height, 2) for x in range(0, width, 2) if samples.getpixel((x, y))]
    if len(points) < 6:
        raise ValueError('not enough verified blank background samples')
    vectors = [(1, x, y) for x, y, _ in points]
    matrix = [[sum(v[i] * v[j] for v in vectors) for j in range(3)] for i in range(3)]
    coeff = [solve(matrix, [sum(v[i] * p[2][c] for v, p in zip(vectors, points)) for i in range(3)]) for c in range(4)]
    fitted = Image.new('RGBA', original.size)
    edit = mask_for(original.size, [region])
    x0, y0, x1, y1 = edit.getbbox()
    for y in range(y0, y1):
        for x in range(x0, x1):
            fitted.putpixel((x, y), tuple(max(0, min(255, round(c[0] + c[1] * x / width + c[2] * y / height))) for c in coeff))
    return fitted


def pixel_changes(a, b):
    _, Chops, _, _ = pillow()
    channels = Chops.difference(a.convert('RGB'), b.convert('RGB')).split()
    rgb = Chops.lighter(Chops.lighter(channels[0], channels[1]), channels[2]).point(lambda v: 255 if v else 0)
    alpha = Chops.difference(a.getchannel('A'), b.getchannel('A')).point(lambda v: 255 if v else 0)
    return Chops.lighter(rgb, alpha), alpha


def validate_pixels(original, output, asset):
    _, Chops, _, _ = pillow()
    if original.size != output.size or original.mode != output.mode:
        raise ValueError('image size/mode changed')
    changed, alpha = pixel_changes(original.convert('RGBA'), output.convert('RGBA'))
    editable = mask_for(original.size, asset['regions'])
    protected = mask_for(original.size, asset.get('protected', []))
    for mask, message in [(Chops.multiply(changed, Chops.invert(editable)), 'pixels changed outside edit regions'), (Chops.multiply(changed, protected), 'protected art/rules/fees changed')]:
        if mask.getbbox():
            raise ValueError(message)
    if asset.get('alpha_policy', 'preserve') not in ('preserve', 'within_regions'):
        raise ValueError('unsupported alpha policy')
    if asset.get('alpha_policy', 'preserve') == 'preserve' and alpha.getbbox():
        raise ValueError('alpha changed without explicit region-scoped permission')
    return {'changed_pixels': changed.histogram()[255], 'alpha_changed_pixels': alpha.histogram()[255]}


def render(task, plan, sample=False, selected=None):
    Image, Chops, Draw, Font = pillow()
    current = state(task)
    task.output('images/state.json')
    prepared = []
    reusable = {}
    fingerprints = {name: style_hash(style) for name, style in plan['styles'].items()}
    if selected and not set(selected) <= {a['file'] for a in plan['assets'] if a['decision'] == 'translate'}:
        raise ValueError('selected samples must be declared translation assets')
    for asset in plan['assets']:
        if asset['decision'] != 'translate' or selected and asset['file'] not in selected:
            continue
        name = asset['file']
        backup = task.path('backup/img/' + name)
        source = backup if backup.exists() else task.image_source(name, asset['source_sha256'])
        regular(source)
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != asset['source_sha256']:
            raise ValueError('pristine source changed')
        original = Image.open(io.BytesIO(raw))
        original.load()
        if original.mode not in ('RGB', 'RGBA'):
            raise ValueError('only decoded RGB/RGBA images are supported')
        base = original.convert('RGBA')
        protected = mask_for(original.size, asset.get('protected', []))
        used = Image.new('L', original.size)
        donor = reusable.get(asset.get('reuse_from'))
        if asset.get('reuse_from') and donor is None:
            raise ValueError('reuse_from must reference an earlier translated asset')
        if donor:
            donor_asset, donor_original, donor_output = donor
            if asset['regions'] != donor_asset['regions'] or original.size != donor_original.size or original.mode != donor_original.mode:
                raise ValueError('alias reuse requires identical region configuration and image format')
            mask = Chops.multiply(mask_for(original.size, asset['regions']), Chops.invert(protected))
            donor_protected = mask_for(original.size, donor_asset.get('protected', []))
            if Chops.multiply(mask, donor_protected).getbbox():
                raise ValueError('alias region includes donor protected pixels')
            difference, _ = pixel_changes(original.convert('RGBA'), donor_original.convert('RGBA'))
            if Chops.multiply(difference, mask).getbbox():
                raise ValueError('alias background differs inside edit regions; render independently')
            base = Image.composite(donor_output.convert('RGBA'), base, mask)
        for region in asset['regions']:
            style = plan['styles'][region['style']]
            if not sample and current['approvals'].get(region['style'], {}).get('sha256') != fingerprints[region['style']]:
                raise ValueError('style not approved or changed since approval: ' + region['style'])
            wording(region['target'], region['lines'])
            if not region.get('source', '').strip():
                raise ValueError('missing source transcription')
            if donor:
                continue
            mask = mask_for(original.size, [region])
            mask = Chops.multiply(mask, Chops.invert(protected))
            if Chops.multiply(mask, used).getbbox():
                raise ValueError('overlapping text edit regions')
            used = Chops.lighter(used, mask)
            base = Image.composite(backdrop(original.convert('RGBA'), region, style), base, mask)
            font = Font.truetype(style['font'], style['size'])
            missing = bytes(font.getmask(chr(0x10ffff)))
            for character in set(region['target']) - set(' \t\r\n'):
                glyph = font.getmask(character)
                if not glyph.getbbox() or bytes(glyph) == missing:
                    raise ValueError('font lacks target glyph: ' + character)
            tile = Image.new('RGBA', original.size)
            draw = Draw.Draw(tile)
            color = region.get('color', [0, 0, 0, 255])
            if len(color) != 4 or any(type(v) is not int or not 0 <= v <= 255 for v in color) or color[3] == 0:
                raise ValueError('text needs a visible RGBA byte colour')
            x, y = region['xy']
            for n, line in enumerate(region['lines'].split('\n')):
                position = (x, y + n * style['line_spacing'])
                box = draw.textbbox(position, line, font=font)
                if box[0] < 0 or box[1] < 0 or box[2] > original.width or box[3] > original.height:
                    raise ValueError('text extends outside image before rasterization')
                draw.text(position, line, font=font, fill=tuple(color))
            angle = style.get('angle', 0)
            if not isinstance(angle, (int, float)) or not math.isfinite(angle):
                raise ValueError('invalid angle')
            if angle:
                radians = math.radians(angle)
                bounds = tile.getbbox()
                for px, py in ((bounds[0], bounds[1]), (bounds[2], bounds[1]), (bounds[2], bounds[3]), (bounds[0], bounds[3])):
                    rx = x + (px - x) * math.cos(radians) + (py - y) * math.sin(radians)
                    ry = y - (px - x) * math.sin(radians) + (py - y) * math.cos(radians)
                    if not (1 <= rx < original.width - 1 and 1 <= ry < original.height - 1):
                        raise ValueError('rotated text extends outside image')
                tile = tile.rotate(angle, resample=Image.Resampling.BICUBIC, center=(x, y))
            ink = tile.getchannel('A').point(lambda v: 255 if v else 0)
            if Chops.multiply(ink, Chops.invert(mask)).getbbox():
                raise ValueError('text overflows edit region or protected art: ' + name)
            base = Image.alpha_composite(base, tile)
        output = base.convert(original.mode)
        checks = validate_pixels(original, output, asset)
        # Resolve every destination before publishing any image.
        task.output('images/translated/' + name)
        prepared.append((asset, raw, backup, output, checks))
        reusable[name] = (asset, original, output)
    # No output is published until every selected image passes preflight/render checks.
    for asset, raw, backup, output, checks in prepared:
        name = asset['file']
        destination = task.output('images/translated/' + name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            with backup.open('xb') as file:
                file.write(raw)
        buffer = io.BytesIO()
        output.save(buffer, format='PNG')
        atomic_bytes(destination, buffer.getvalue())
        current['results'][name] = {'source_sha256': asset['source_sha256'], 'output_sha256': digest(destination), 'asset_sha256': hashlib.sha256(json.dumps(asset, sort_keys=True).encode()).hexdigest(), 'styles_sha256': {r['style']: fingerprints[r['style']] for r in asset['regions']}, 'sample': sample, **checks}
    active = {a['file'] for a in plan['assets'] if a['decision'] == 'translate'}
    for name in list(current['results']):
        if name not in active:
            entry = current['results'].pop(name)
            current['obsolete'].append({'path': 'images/translated/' + name, 'sha256': entry['output_sha256']})
    write_json(task.output('images/state.json'), current)
    return {'rendered': len(prepared), 'sample': sample}


def check(task, plan, installable=False):
    Image, _, _, _ = pillow()
    current = state(task)
    rows = []
    fingerprints = {name: style_hash(style) for name, style in plan['styles'].items()}
    for asset in plan['assets']:
        if asset['decision'] != 'translate':
            continue
        name = asset['file']
        result = current['results'].get(name, {})
        if installable and result.get('sample'):
            raise ValueError('sample cannot be installed; approve style and render batch')
        expected = hashlib.sha256(json.dumps(asset, sort_keys=True).encode()).hexdigest()
        if result.get('asset_sha256') != expected:
            raise ValueError('image configuration changed; render again: ' + name)
        source = task.path('backup/img/' + name)
        output = task.path('images/translated/' + name)
        regular(source)
        regular(output)
        if digest(source) != asset['source_sha256'] or digest(output) != result.get('output_sha256'):
            raise ValueError('image file changed after render: ' + name)
        for region in asset['regions']:
            wording(region['target'], region['lines'])
            if result.get('styles_sha256', {}).get(region['style']) != fingerprints[region['style']]:
                raise ValueError('rendered style changed; render again')
            if not result.get('sample') and current['approvals'].get(region['style'], {}).get('sha256') != fingerprints[region['style']]:
                raise ValueError('approved style changed; render again')
        original, target = Image.open(source), Image.open(output)
        rows.append({'file': name, 'source_sha256': asset['source_sha256'],
                     'target_sha256': result['output_sha256'], **validate_pixels(original, target, asset)})
    return {'complete': True, 'images': rows, 'unresolved': [a['file'] for a in plan['assets'] if a['decision'] == 'uncertain']}


def compare(task, plan):
    current = state(task)
    parts = ['<!doctype html><meta charset="utf-8"><title>Image translation review</title><style>body{font:16px system-ui}article{margin:24px}.pair{display:flex;gap:12px}img{max-width:48%;object-fit:contain;background:repeating-conic-gradient(#ddd 0% 25%,white 0% 50%) 50%/16px 16px}pre{white-space:pre-wrap}</style>']
    for asset in plan['assets']:
        name = asset['file']
        parts.append('<article id="' + html.escape(name, quote=True) + '"><h2>' + html.escape(name) + '</h2><p>' + html.escape(asset['decision'] + ': ' + asset['reason']) + '</p>')
        if name in current['results'] and asset['decision'] == 'translate':
            parts.append('<div class="pair"><img loading="lazy" src="../backup/img/' + quote(name, safe='/') + '"><img loading="lazy" src="translated/' + quote(name, safe='/') + '"></div>')
            for region in asset['regions']:
                parts.append('<pre>' + html.escape(region['source'] + '\n→ ' + region['target']) + '</pre>')
        parts.append('</article>')
    write = task.output('images/compare.html')
    write.write_text('\n'.join(parts), encoding='utf-8')
    return {'compare': str(write)}


def delivery(task, plan):
    return [{'path': 'img/' + row['file'], 'output': 'images/translated/' + row['file'],
             'backup': 'backup/img/' + row['file'], 'source_sha256': row['source_sha256'],
             'target_sha256': row['target_sha256']} for row in check(task, plan, installable=True)['images']]


def clean(task, write=False):
    """Delete only retired image outputs whose recorded hashes still match."""
    current = state(task)
    protected = {task.path('images/translated/' + name) for name in current['results']}
    protected.update(task.installed_outputs())
    candidates = []
    for row in current['obsolete']:
        path = task.output(row['path'])
        if not inside(path, task.path('images/translated')) or path in protected:
            raise ValueError('cleanup refuses protected or non-translation artifacts')
        if path.exists():
            regular(path)
            if digest(path) != row['sha256']:
                raise ValueError('retired output changed; inspect before cleanup')
            candidates.append(path)
    if write:
        for path in set(candidates):
            path.unlink()
        current['obsolete'] = []
        write_json(task.output('images/state.json'), current)
    return {'write': write, 'files': [str(path.relative_to(task.root)) for path in candidates]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['plan', 'approve', 'render', 'check', 'compare', 'delivery'])
    parser.add_argument('--task', required=True)
    parser.add_argument('--manifest')
    parser.add_argument('--sample', action='store_true')
    parser.add_argument('--asset', action='append', help='render only these manifest paths; repeat for representative samples')
    parser.add_argument('--style')
    parser.add_argument('--note', default='')
    args = parser.parse_args(argv)
    try:
        from translation_workspace import Workspace
        task = Workspace(args.task)
        plan = load_plan(task, args.manifest)
        if args.command == 'plan':
            result = [{'file': a['file'], 'decision': a['decision'], 'reason': a['reason']} for a in plan['assets']]
        elif args.command == 'approve':
            if not args.style:
                parser.error('approve requires --style and --note with actual user approval')
            approve(task, plan, args.style, args.note)
            result = {'approved_style': args.style}
        elif args.command == 'render':
            result = render(task, plan, args.sample, args.asset)
        elif args.command == 'check':
            result = check(task, plan)
        elif args.command == 'compare':
            result = compare(task, plan)
        else:
            result = {'schema_version': 1, 'files': delivery(task, plan)}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
        print('ERROR: ' + str(exc))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
