#!/usr/bin/env python3
"""Summarize an unpacked PPTX for fast template editing.

Outputs compact JSON with the current presentation order, original slide file
numbers, stable text refs, and existing image slots. Models should copy refs
such as ``slide5:shape3`` into text plans instead of guessing slide/shape IDs.
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from text_rules import sha_norm

try:
    from chart_utils import read_chart_data, slide_charts_unpacked
except ImportError:  # pragma: no cover - inspect_deck always sits beside chart_utils
    read_chart_data = None
    slide_charts_unpacked = None

try:
    from table_utils import slide_tables_unpacked
except ImportError:  # pragma: no cover - inspect_deck always sits beside table_utils
    slide_tables_unpacked = None


_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'


def _slide_num_from_target(target: str) -> int | None:
    m = re.search(r'slides/slide(\d+)\.xml$', target)
    return int(m.group(1)) if m else None


def _slide_size(unpacked: Path) -> dict[str, int]:
    """从 presentation.xml 读取幻灯片画布尺寸（EMU）。"""
    pres = unpacked / 'ppt' / 'presentation.xml'
    if not pres.exists():
        return {'cx': 0, 'cy': 0}
    try:
        root = ET.parse(pres).getroot()
        sz = root.find(f'{{{_P}}}sldSz')
        if sz is not None:
            return {'cx': int(sz.get('cx', '0')), 'cy': int(sz.get('cy', '0'))}
    except (ET.ParseError, TypeError, ValueError):
        pass
    return {'cx': 0, 'cy': 0}


def _autofit(shape: ET.Element) -> str:
    """返回该文本框的 autofit 模式：normAutofit / spAutoFit / noAutofit / inherit。"""
    body = shape.find(f'.//{{{_A}}}bodyPr')
    if body is None:
        return 'inherit'
    if body.find(f'{{{_A}}}normAutofit') is not None:
        return 'normAutofit'
    if body.find(f'{{{_A}}}spAutoFit') is not None:
        return 'spAutoFit'
    if body.find(f'{{{_A}}}noAutofit') is not None:
        return 'noAutofit'
    return 'inherit'


def _presentation_order(unpacked: Path) -> list[int]:
    pres = unpacked / 'ppt' / 'presentation.xml'
    rels = unpacked / 'ppt' / '_rels' / 'presentation.xml.rels'
    if not pres.exists() or not rels.exists():
        sys.exit(f'找不到 presentation.xml 或 rels: {unpacked}')

    rel_tree = ET.parse(rels)
    rid_to_slide: dict[str, int] = {}
    for rel in rel_tree.getroot().iter(f'{{{_REL_NS}}}Relationship'):
        num = _slide_num_from_target(rel.get('Target', ''))
        if num is not None:
            rid_to_slide[rel.get('Id', '')] = num

    tree = ET.parse(pres)
    order: list[int] = []
    for sld_id in tree.getroot().findall(f'.//{{{_P}}}sldId'):
        rid = sld_id.get(f'{{{_R}}}id')
        if rid in rid_to_slide:
            order.append(rid_to_slide[rid])
    return order


def _shape_text(shape: ET.Element) -> list[str]:
    paragraphs: list[str] = []
    for para in shape.findall(f'.//{{{_A}}}p'):
        text = ''.join(t.text or '' for t in para.findall(f'.//{{{_A}}}t')).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _shape_bounds(shape: ET.Element) -> dict[str, int] | None:
    # 只取当前对象自身 spPr/xfrm 的几何。不能用 `.//a:ext`：很多 Office
    # 文件会在 cNvPr/a:extLst 里先出现一个仅有 uri、没有 cx/cy 的扩展节点，
    # 旧实现会误命中它，把实际宽高读成 0，继而把满版背景和小图标都标成可替换。
    sp_pr = shape.find(f'{{{_P}}}spPr')
    xfrm = sp_pr.find(f'{{{_A}}}xfrm') if sp_pr is not None else None
    if xfrm is None:
        return None
    off = xfrm.find(f'{{{_A}}}off')
    ext = xfrm.find(f'{{{_A}}}ext')
    if off is None or ext is None:
        return None
    try:
        return {
            'x': int(off.get('x', '0')),
            'y': int(off.get('y', '0')),
            'cx': int(ext.get('cx', '0')),
            'cy': int(ext.get('cy', '0')),
        }
    except (TypeError, ValueError):
        return None


def _rels_targets(unpacked: Path, slide: int) -> dict[str, str]:
    path = unpacked / 'ppt' / 'slides' / '_rels' / f'slide{slide}.xml.rels'
    if not path.exists():
        return {}
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return {}
    out: dict[str, str] = {}
    for rel in root.iter(f'{{{_REL_NS}}}Relationship'):
        rid = rel.get('Id')
        target = rel.get('Target')
        if rid and target:
            out[rid] = posixpath.normpath(posixpath.join('ppt/slides', target))
    return out


def _blip_embed(el: ET.Element) -> str | None:
    blip = el.find(f'.//{{{_A}}}blip')
    if blip is None:
        return None
    return blip.get(f'{{{_R}}}embed')


# 与 check_images.py / replace_image.py 的相对面积策略保持一致。
# 大图（达到半页）按背景/主视觉保护；过小图按 icon/装饰资源保护。
_FULLBLEED_BG_FRAC = 0.50
_SMALL_ICON_FRAC = 0.02
_TEXT_OVERLAP_BG_FRAC = 0.50


def _bounds_overlap_area(a: dict[str, int], b: dict[str, int]) -> int:
    ix = max(0, min(a['x'] + a['cx'], b['x'] + b['cx']) - max(a['x'], b['x']))
    iy = max(0, min(a['y'] + a['cy'], b['y'] + b['cy']) - max(a['y'], b['y']))
    return ix * iy


def _is_protected_backdrop(bounds: dict[str, int] | None, area_frac: float | None,
                            text_bounds: list[dict[str, int]]) -> bool:
    """判定该视觉槎是不是"给文字当背景/满版背景"——逻辑与 check_images.py 的
    `_is_text_backdrop`/`is_fullbleed` 完全一致，暴露给模型在生图前就避开，
    别等 check_images 事后 blocking 才发现（省一轮生成+一轮回滚的来回）。"""
    if area_frac is not None and area_frac >= _FULLBLEED_BG_FRAC:
        return True
    if not bounds:
        return False
    for tb in text_bounds:
        tarea = tb['cx'] * tb['cy']
        if tarea <= 0:
            continue
        if _bounds_overlap_area(bounds, tb) / tarea >= _TEXT_OVERLAP_BG_FRAC:
            return True
    return False


def _visual_slots(unpacked: Path, slide: int, root: ET.Element, slide_size: dict[str, int] | None,
                   text_bounds: list[dict[str, int]] | None = None) -> list[dict]:
    """Expose every existing visual carrier that can safely swap media without adding objects."""
    rels = _rels_targets(unpacked, slide)
    slots: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(slot_type: str, source_ref: str, embed: str | None, bounds: dict[str, int] | None, name: str = '') -> None:
        if not embed:
            return
        key = (slot_type, source_ref)
        if key in seen:
            return
        seen.add(key)
        area_frac = None
        if bounds and slide_size and slide_size.get('cx') and slide_size.get('cy'):
            area_frac = round((bounds['cx'] * bounds['cy']) / (slide_size['cx'] * slide_size['cy']), 4)
        protected_backdrop = _is_protected_backdrop(bounds, area_frac, text_bounds or [])
        protected_small = area_frac is not None and area_frac < _SMALL_ICON_FRAC
        protected = protected_backdrop or protected_small
        if protected_backdrop:
            protected_reason = ('给文字当背景或占画布至少 50%，模板已配合版式精选；'
                                '禁止替换，保留原图（check_images 会硬性 blocking）')
        elif protected_small:
            protected_reason = ('占画布不足 2%，按图标/装饰占位保护；禁止用生成图片替换，'
                                '保留模板原资源（check_images 会硬性 blocking）')
        else:
            protected_reason = None
        slots.append({
            'ref': f'slide{slide}:visual{len(slots) + 1}',
            'index': len(slots) + 1,
            'type': slot_type,
            'source_ref': source_ref,
            'name': name,
            'embed': embed,
            'media': rels.get(embed),
            'bounds': bounds,
            'area_frac': area_frac,
            'replaceable': not protected,
            'protected_backdrop': protected_backdrop,
            'protected_small_visual': protected_small,
            'protected_reason': protected_reason,
        })

    for idx, pic in enumerate(root.iter(f'{{{_P}}}pic'), start=1):
        nv = pic.find(f'.//{{{_P}}}cNvPr')
        name = nv.get('name', '') if nv is not None else ''
        add('pic', f'slide{slide}:image{idx}', _blip_embed(pic), _shape_bounds(pic), name)

    for idx, shape in enumerate(root.iter(f'{{{_P}}}sp'), start=1):
        sp_pr = shape.find(f'{{{_P}}}spPr')
        if sp_pr is None or sp_pr.find(f'{{{_A}}}blipFill') is None:
            continue
        nv = shape.find(f'.//{{{_P}}}cNvPr')
        name = nv.get('name', '') if nv is not None else ''
        add('shape_fill', f'slide{slide}:shape{idx}', _blip_embed(sp_pr), _shape_bounds(shape), name)

    return slots


def _slide_capabilities(texts: list[dict], visuals: list[dict], charts: list[dict], tables: list[dict]) -> dict:
    body_chars = sum(len(str(t.get('text', ''))) for t in texts if t.get('kind') == 'body')
    title_count = sum(1 for t in texts if t.get('kind') == 'title')
    text_density = 'low'
    if body_chars > 260 or len(texts) >= 12:
        text_density = 'high'
    elif body_chars > 120 or len(texts) >= 7:
        text_density = 'medium'

    if charts:
        best_use = 'data_chart'
    elif tables:
        best_use = 'table_grid'
    elif len(visuals) >= 2:
        best_use = 'multi_visual'
    elif len(visuals) == 1:
        best_use = 'hero_visual'
    elif title_count and body_chars <= 80:
        best_use = 'section_or_quote'
    else:
        best_use = 'text_layout'
    return {
        'visual_slots_count': len(visuals),
        'chart_slots_count': len(charts),
        'table_slots_count': len(tables),
        'text_slots_count': len(texts),
        'body_chars': body_chars,
        'text_density': text_density,
        'best_use': best_use,
    }


def _guess_kind(paragraphs: list[str], bounds: dict[str, int] | None,
                slide_size: dict[str, int] | None = None) -> str:
    text = '\n'.join(paragraphs).strip()
    if not text:
        return 'empty'
    short = len(text) <= 24
    if len(paragraphs) <= 2 and short:
        return 'title'
    # 装饰判定改为相对画布比例（不再写死绝对 EMU）：很矮或很窄的小文本框，
    # 多为页脚/页码/品牌角标等装饰。缺画布尺寸时跳过该判定。
    if bounds and slide_size and slide_size.get('cy') and slide_size.get('cx'):
        if bounds['cy'] < slide_size['cy'] * 0.035 or bounds['cx'] < slide_size['cx'] * 0.065:
            return 'decorative_candidate'
    if len(text) <= 18 and (text.isupper() or text.isdigit()):
        return 'decorative_candidate'
    return 'body'


_CJK_RE = re.compile(r'[\u4e00-\u9fff]')
_LATIN_RE = re.compile(r'[A-Za-z]')


def _script_kind(text: str) -> str:
    """'cn'（含中文）/ 'latin'（纯拉丁、无中文）/ 'other'。"""
    if _CJK_RE.search(text):
        return 'cn'
    if _LATIN_RE.search(text):
        return 'latin'
    return 'other'


def _annotate_pairs(text_shapes: list[dict], slide_size: dict | None) -> None:
    """给中英文成对框打 `pair_hint`：模板里常见"中文标题框 + 紧邻英文译文框"，
    模型只改其一就会错位。把彼此最近、且水平对齐/竖直相邻的 cn↔latin 框互相标注，
    提示成对替换。仅是提示，不强约束。"""
    if not slide_size or not slide_size.get('cx') or not slide_size.get('cy'):
        return
    sw, sh = slide_size['cx'], slide_size['cy']
    items = []
    for t in text_shapes:
        b = t.get('bounds')
        if not b or not b.get('cx') or not b.get('cy'):
            continue
        items.append((t, _script_kind(t.get('text', '')), b))
    near = max(sw, sh) * 0.18  # 中心距阈值：约画布 18%
    for t, kind, b in items:
        if kind not in ('cn', 'latin'):
            continue
        cx = b['x'] + b['cx'] / 2
        cy = b['y'] + b['cy'] / 2
        best = None
        for t2, kind2, b2 in items:
            if t2 is t or kind2 == kind or kind2 == 'other':
                continue
            cx2 = b2['x'] + b2['cx'] / 2
            cy2 = b2['y'] + b2['cy'] / 2
            dist = ((cx - cx2) ** 2 + (cy - cy2) ** 2) ** 0.5
            # 水平方向有重叠（同栏）才算一对，避免跨栏误配
            x_ov = min(b['x'] + b['cx'], b2['x'] + b2['cx']) - max(b['x'], b2['x'])
            if dist <= near and x_ov > 0:
                if best is None or dist < best[0]:
                    best = (dist, t2)
        if best is not None:
            t['pair_hint'] = best[1]['ref']


def _summarize_slide(unpacked: Path, order: int, slide: int, max_chars: int,
                     slide_size: dict[str, int] | None = None) -> dict:
    path = unpacked / 'ppt' / 'slides' / f'slide{slide}.xml'
    if not path.exists():
        return {
            'order': order,
            'slide': slide,
            'slide_file': f'ppt/slides/slide{slide}.xml',
            'missing': True,
        }

    tree = ET.parse(path)
    root = tree.getroot()
    text_shapes: list[dict] = []
    for idx, shape in enumerate(root.iter(f'{{{_P}}}sp'), start=1):
        paragraphs = _shape_text(shape)
        if not paragraphs:
            continue
        nv = shape.find(f'.//{{{_P}}}cNvPr')
        name = nv.get('name', '') if nv is not None else ''
        shape_id = nv.get('id', '') if nv is not None else ''
        bounds = _shape_bounds(shape)
        full = '\n'.join(paragraphs)
        sample = full
        if len(sample) > max_chars:
            sample = sample[:max_chars].rstrip() + '...'
        text_shapes.append(
            {
                'ref': f'slide{slide}:shape{idx}',
                'shape': idx,
                'shape_id': shape_id,
                'name': name,
                'kind': _guess_kind(paragraphs, bounds, slide_size),
                'paragraphs': len(paragraphs),
                'text': sample,
                # orig_sha 对**未截断全文**取归一化哈希：verify 用它精确判断成品是否
                # 逐字等于模板原文（截断 text 仅供模型/人阅读，不参与对比）。
                'orig_sha': sha_norm(full),
                'bounds': bounds,
                'autofit': _autofit(shape),
            }
        )

    _annotate_pairs(text_shapes, slide_size)

    images: list[dict] = []
    for idx, pic in enumerate(root.iter(f'{{{_P}}}pic'), start=1):
        nv = pic.find(f'.//{{{_P}}}cNvPr')
        name = nv.get('name', '') if nv is not None else ''
        images.append({'ref': f'slide{slide}:image{idx}', 'index': idx, 'name': name})
    _text_bounds_for_backdrop = [t['bounds'] for t in text_shapes
                                  if t.get('bounds') and len((t.get('text') or '').strip()) >= 2]
    visual_slots = _visual_slots(unpacked, slide, root, slide_size, _text_bounds_for_backdrop)

    # 图表槽位：暴露当前（模板示例）类目/系列/数值，便于模型按主题用 edit_chart 本地化。
    charts: list[dict] = []
    if slide_charts_unpacked is not None and read_chart_data is not None:
        for ref, part in slide_charts_unpacked(unpacked, slide):
            try:
                data = read_chart_data(Path(part).read_text(encoding='utf-8'))
            except (OSError, UnicodeDecodeError):
                continue
            charts.append({
                'ref': ref,
                'type': data.get('type', ''),
                'categories': data.get('categories', []),
                'series': data.get('series', []),
            })

    # 表格槽位：表格内嵌在 slide XML（p:sp 扫不到），单独暴露其单元格网格，
    # 便于模型按主题用 edit_table 本地化（否则模板示例表格会原样留下）。
    tables: list[dict] = []
    if slide_tables_unpacked is not None:
        tables = slide_tables_unpacked(unpacked, slide)
    capabilities = _slide_capabilities(text_shapes, visual_slots, charts, tables)

    title = ''
    if text_shapes:
        title = text_shapes[0]['text'].splitlines()[0][:80]
    return {
        'order': order,
        'slide': slide,
        'slide_file': f'ppt/slides/slide{slide}.xml',
        'title': title,
        'texts': text_shapes,
        'image_slots': images,
        'visual_slots': visual_slots,
        'chart_slots': charts,
        'table_slots': tables,
        'capabilities': capabilities,
    }


def _scan_master_layout_texts(unpacked: Path) -> list[dict]:
    """扫描母版/版式里的静态文本（常见角标/脚注/页脚），便于发现写死在母版里的角标。

    这些文本无法通过 slideN:shapeM ref 改写——若需要改写角标，需直接编辑对应
    ppt/slideMasters 或 ppt/slideLayouts 下的 XML，或由设计侧把角标移到页面内。
    """
    out: list[dict] = []
    for sub in ('slideMasters', 'slideLayouts'):
        d = unpacked / 'ppt' / sub
        if not d.exists():
            continue
        for path in sorted(d.glob('*.xml'), key=lambda p: p.name):
            try:
                root = ET.parse(path).getroot()
            except ET.ParseError:
                continue
            for shape in root.iter(f'{{{_P}}}sp'):
                paras = _shape_text(shape)
                txt = '\n'.join(paras).strip()
                # 只报真实静态文字，跳过占位符提示文本（如“单击此处编辑”）
                if not txt or len(txt) > 60:
                    continue
                if re.search(r'单击|点击|编辑母版|母版标题|母版文本', txt):
                    continue
                # 跳过页码/日期字段占位（‹#›）与纯符号/数字（非真实角标文字）
                if not re.search(r'[\u4e00-\u9fffA-Za-z]', txt):
                    continue
                out.append({'file': f'ppt/{sub}/{path.name}', 'text': txt[:60]})
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description='Inspect unpacked PPTX slides in one compact JSON.')
    ap.add_argument('unpacked')
    ap.add_argument('--slides', help='Comma-separated slide numbers; default: current presentation order.')
    ap.add_argument('--max-chars', type=int, default=220)
    ap.add_argument('--summary', action='store_true', help='Print compact human-readable slide/text summary.')
    args = ap.parse_args()

    unpacked = Path(args.unpacked)
    if unpacked.suffix.lower() == '.pptx':
        sys.exit('inspect_deck.py 需要解包后的目录；请先运行 scripts/office/unpack.py。')
    if args.slides:
        slides = [int(x) for x in args.slides.split(',') if x.strip()]
    else:
        slides = _presentation_order(unpacked)

    slide_size = _slide_size(unpacked)
    result = {
        'slide_order': slides,
        'slide_size': slide_size,
        'slides': [
            _summarize_slide(unpacked, order, slide, args.max_chars, slide_size)
            for order, slide in enumerate(slides, start=1)
        ],
        'master_layout_texts': _scan_master_layout_texts(unpacked),
    }
    if args.summary:
        for slide in result['slides']:
            cap = slide.get('capabilities', {})
            print(
                f"slide{slide.get('slide')} order={slide.get('order')} title={slide.get('title', '')!r} "
                f"best_use={cap.get('best_use')} visuals={cap.get('visual_slots_count')} "
                f"charts={cap.get('chart_slots_count')} tables={cap.get('table_slots_count')} "
                f"text_density={cap.get('text_density')}"
            )
            for t in slide.get('texts', []):
                print(f"  {t.get('ref')} [{t.get('kind')}] {str(t.get('text', '')).replace(chr(10), ' / ')[:100]}")
            visuals = slide.get('visual_slots', [])
            if visuals:
                print(f"  visual_slots={len(visuals)} " + ', '.join(v.get('ref', '') for v in visuals[:6]))
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
