#!/usr/bin/env python3
"""Summarize an unpacked PPTX for fast template editing.

Outputs compact JSON with the current presentation order, original slide file
numbers, stable text refs, and existing image slots. Models should copy refs
such as ``slide5:shape3`` into text plans instead of guessing slide/shape IDs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from text_rules import sha_norm


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
    off = shape.find(f'.//{{{_A}}}off')
    ext = shape.find(f'.//{{{_A}}}ext')
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

    images: list[dict] = []
    for idx, pic in enumerate(root.iter(f'{{{_P}}}pic'), start=1):
        nv = pic.find(f'.//{{{_P}}}cNvPr')
        name = nv.get('name', '') if nv is not None else ''
        images.append({'ref': f'slide{slide}:image{idx}', 'index': idx, 'name': name})

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
            print(f"slide{slide.get('slide')} order={slide.get('order')} title={slide.get('title', '')!r}")
            for t in slide.get('texts', []):
                print(f"  {t.get('ref')} [{t.get('kind')}] {str(t.get('text', '')).replace(chr(10), ' / ')[:100]}")
        return 0
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
