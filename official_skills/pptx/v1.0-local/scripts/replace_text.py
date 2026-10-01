#!/usr/bin/env python3
"""Batch-apply a text plan to existing PPTX template shapes.

Plan shape (normally built by plan_from_lines.py from content_lines.tsv):
{
  "slides": [
    {"texts": [
      {"ref": "slide5:shape3", "action": "replace", "paragraphs": ["新标题"]},
      {"ref": "slide5:shape9", "action": "clear"},
      {"ref": "slide5:shape10", "action": "keep"}
    ]}
  ]
}

Also accepts a flat {"replacements": [...]} list for model convenience.
Refs come from inspect_deck.py and point to existing text shapes only.
Ops are grouped per slide so each slide XML is parsed once and written once.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from text_rules import _norm, _sanitize_text

_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_REF_RE = re.compile(r'^slide(\d+):shape(\d+)$')


ET.register_namespace('a', _A)
ET.register_namespace('p', _P)
ET.register_namespace('r', _R)
try:
    from ooxml_ns import register_all as _reg_ns
    _reg_ns()
except Exception:
    pass


def _paragraphs(rep: dict) -> list[str]:
    if 'paragraphs' in rep:
        vals = rep['paragraphs']
        if not isinstance(vals, list):
            sys.exit('paragraphs 必须是字符串数组')
        return [_sanitize_text(str(v)) for v in vals]
    return [_sanitize_text(x) for x in (str(rep.get('text', '')).splitlines() or [''])]


def _shape_ref(slide: int, shape: int) -> str:
    return f'slide{slide}:shape{shape}'


def _parse_ref(ref: str) -> tuple[int, int]:
    m = _REF_RE.match(ref)
    if not m:
        raise ValueError(f'非法 ref: {ref!r}，应类似 slide5:shape3')
    return int(m.group(1)), int(m.group(2))


def _slide_path(unpacked: Path, slide: int) -> Path:
    return unpacked / 'ppt' / 'slides' / f'slide{slide}.xml'


def _text_shapes(root: ET.Element) -> list[ET.Element]:
    return list(root.iter(f'{{{_P}}}sp'))


def _shape_text(shape: ET.Element) -> str:
    paragraphs: list[str] = []
    for para in shape.findall(f'.//{{{_A}}}p'):
        text = ''.join(t.text or '' for t in para.findall(f'.//{{{_A}}}t')).strip()
        if text:
            paragraphs.append(text)
    return '\n'.join(paragraphs).strip()


def _available_refs(unpacked: Path, slide: int | None = None) -> list[str]:
    refs: list[str] = []
    slide_files: list[Path]
    if slide is None:
        slide_files = sorted((unpacked / 'ppt' / 'slides').glob('slide*.xml'), key=lambda p: int(re.search(r'\d+', p.name).group()))
    else:
        slide_files = [_slide_path(unpacked, slide)]
    for p in slide_files:
        if not p.exists():
            continue
        s = int(re.search(r'\d+', p.name).group())
        root = ET.parse(p).getroot()
        for idx, shape in enumerate(_text_shapes(root), start=1):
            if shape.find(f'{{{_P}}}txBody') is not None:
                refs.append(_shape_ref(s, idx))
    return refs


def _set_para_text(para: ET.Element, text: str) -> None:
    a = lambda tag: f'{{{_A}}}{tag}'
    lines = (text or '').split('\n')
    runs = para.findall(a('r'))

    # 单行：沿用原行为，保留模板里多 run 的结构（如高亮词，反馈 row7）
    if len(lines) <= 1:
        texts = para.findall(f'.//{{{_A}}}t')
        if not texts:
            run = para.find(a('r'))
            if run is None:
                run = ET.Element(a('r'))
                endpr = para.find(a('endParaRPr'))
                # rPr 继承 endParaRPr 的字符格式（字号/颜色/字体等），避免裸 <a:rPr/>
                if endpr is not None:
                    rpr = copy.deepcopy(endpr)
                    rpr.tag = a('rPr')
                    run.append(rpr)
                else:
                    run.append(ET.Element(a('rPr')))
                # endParaRPr 必须是段落最后一个子元素：新 run 插到它之前（OOXML schema 硬约束）
                if endpr is not None:
                    para.insert(list(para).index(endpr), run)
                else:
                    para.append(run)
            t = run.find(a('t'))
            if t is None:
                t = ET.SubElement(run, a('t'))
            t.text = text
            return
        texts[0].text = text
        for extra in texts[1:]:
            extra.text = ''
        return

    # 多行：用 <a:br> 在同一段内软换行（反馈 row12），格式取首个 run 的 rPr
    tmpl_rpr = None
    if runs:
        rpr = runs[0].find(a('rPr'))
        if rpr is not None:
            tmpl_rpr = copy.deepcopy(rpr)
    endpr = para.find(a('endParaRPr'))
    for el in list(para):
        if el.tag in (a('r'), a('br')):
            para.remove(el)

    def _mk_run(line: str) -> ET.Element:
        r = ET.Element(a('r'))
        r.append(copy.deepcopy(tmpl_rpr) if tmpl_rpr is not None else ET.Element(a('rPr')))
        t = ET.SubElement(r, a('t'))
        t.text = line
        return r

    new_children: list[ET.Element] = []
    for i, line in enumerate(lines):
        if i > 0:
            br = ET.Element(a('br'))
            if tmpl_rpr is not None:
                br.append(copy.deepcopy(tmpl_rpr))
            new_children.append(br)
        new_children.append(_mk_run(line))

    if endpr is not None:
        idx = list(para).index(endpr)
        for off, ch in enumerate(new_children):
            para.insert(idx + off, ch)
    else:
        for ch in new_children:
            para.append(ch)


def _replace_shape_text(shape: ET.Element, paragraphs: list[str]) -> None:
    tx_body = shape.find(f'{{{_P}}}txBody')
    if tx_body is None:
        sys.exit('目标 shape 没有 p:txBody，不能替换文字')

    paras = tx_body.findall(f'{{{_A}}}p')
    if not paras:
        paras = [ET.SubElement(tx_body, f'{{{_A}}}p')]

    while len(paras) < len(paragraphs):
        new_para = copy.deepcopy(paras[-1])
        tx_body.append(new_para)
        paras.append(new_para)

    for para, text in zip(paras, paragraphs):
        _set_para_text(para, text)

    for para in paras[len(paragraphs):]:
        _set_para_text(para, '')


def _clear_shape_text(shape: ET.Element) -> None:
    tx_body = shape.find(f'{{{_P}}}txBody')
    if tx_body is None:
        return
    for para in tx_body.findall(f'{{{_A}}}p'):
        _set_para_text(para, '')


def _normalize_plan(plan: dict) -> list[dict]:
    """Return flat operations: {ref, action, paragraphs?, text?}."""
    ops: list[dict] = []
    if isinstance(plan, list):
        for rep in plan:
            op = dict(rep)
            op.setdefault('action', 'replace')
            ops.append(op)
        return ops
    if isinstance(plan.get('replacements'), list):
        for rep in plan['replacements']:
            op = dict(rep)
            op.setdefault('action', 'replace')
            ops.append(op)
        return ops

    for slide in plan.get('slides', []):
        slide_no = slide.get('slide')
        if isinstance(slide.get('replacements'), list):
            for rep in slide['replacements']:
                op = dict(rep)
                if 'slide' not in op and slide_no is not None:
                    op['slide'] = slide_no
                op.setdefault('action', 'replace')
                ops.append(op)
        for text_item in slide.get('texts', []):
            op = dict(text_item)
            if 'slide' not in op and slide_no is not None:
                op['slide'] = slide_no
            op.setdefault('action', 'replace')
            ops.append(op)
    return ops


def _resolve_op(op: dict) -> tuple[int, int]:
    if op.get('ref'):
        return _parse_ref(str(op['ref']))
    if 'slide' not in op or 'shape' not in op:
        raise ValueError(f'操作缺少 ref，或缺少 slide/shape: {op}')
    return int(op['slide']), int(op['shape'])


def _load_slide(unpacked: Path, slide: int, cache: dict[int, dict]) -> dict:
    """按页缓存解析后的 XML 树：同一页的多个 op 共用一次 parse，最后只写一次。"""
    if slide not in cache:
        path = _slide_path(unpacked, slide)
        if not path.exists():
            raise FileNotFoundError(f'找不到 {path}。可用 refs: {", ".join(_available_refs(unpacked)[:30])}')
        tree = ET.parse(path)
        cache[slide] = {'path': path, 'tree': tree, 'root': tree.getroot(), 'dirty': False}
    return cache[slide]


def _apply_op(unpacked: Path, op: dict, dry_run: bool, cache: dict[int, dict]) -> dict:
    slide, shape_idx = _resolve_op(op)
    ref = _shape_ref(slide, shape_idx)
    ctx = _load_slide(unpacked, slide, cache)
    root = ctx['root']
    shapes = _text_shapes(root)
    if shape_idx < 1 or shape_idx > len(shapes):
        raise IndexError(
            f'{ref} 不存在；第 {slide} 页共有 {len(shapes)} 个 shape。'
            f' 可用 refs: {", ".join(_available_refs(unpacked, slide))}'
        )
    shape = shapes[shape_idx - 1]
    before = _shape_text(shape)
    action = str(op.get('action', 'replace')).lower()
    if action not in {'replace', 'clear', 'keep'}:
        raise ValueError(f'{ref} 的 action 非法: {action!r}，只能是 replace/clear/keep')

    if action == 'replace':
        paragraphs = _paragraphs(op)
        if not any(p.strip() for p in paragraphs):
            raise ValueError(f'{ref} action=replace 但 paragraphs/text 为空')
        wanted = '\n'.join(paragraphs).strip()
        if not dry_run:
            _replace_shape_text(shape, paragraphs)
            after = _shape_text(shape)
            if _norm(wanted) not in _norm(after):
                raise RuntimeError(f'{ref} 写入后未读到目标文案；before={before!r}, after={after!r}, wanted={wanted!r}')
            ctx['dirty'] = True
    elif action == 'clear':
        if not dry_run:
            _clear_shape_text(shape)
            after = _shape_text(shape)
            if after:
                raise RuntimeError(f'{ref} 清空后仍有文本: {after!r}')
            ctx['dirty'] = True
    else:
        after = before

    result = {'ref': ref, 'action': action, 'ok': True, 'before': before}
    if not dry_run:
        result['after'] = _shape_text(shape)
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description='Batch replace text in existing PPTX shapes.')
    ap.add_argument('unpacked')
    ap.add_argument('plan_json')
    ap.add_argument('--dry-run', action='store_true', help='Validate and summarize without modifying files.')
    ap.add_argument('--report', help='Write JSON report to this path.')
    ap.add_argument('-q', '--quiet', action='store_true', help='Only write report/errors; suppress success text.')
    args = ap.parse_args()

    unpacked = Path(args.unpacked)
    try:
        plan = json.loads(Path(args.plan_json).read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        print(
            'content_plan.json 不是合法 JSON。长 PPT 请不要手写大 JSON；'
            '改写 content_lines.tsv，并运行 '
            'python scripts/plan_from_lines.py "$RUN/deck.selected.json" "$RUN/content_lines.tsv" > "$RUN/content_plan.json"。'
            f' JSON 错误: {exc}',
            file=sys.stderr,
        )
        return 2
    ops = _normalize_plan(plan)
    if not ops:
        print('文本计划为空：请提供 slides[].texts / slides[].replacements 或 replacements。', file=sys.stderr)
        return 2

    report = {'dry_run': args.dry_run, 'planned': len(ops), 'applied': 0, 'ops': [], 'errors': []}
    # 同一页的多个 op 共用一次 parse，全部应用完再每页只写一次（更高效、写入更原子）。
    cache: dict[int, dict] = {}
    for i, op in enumerate(ops, start=1):
        try:
            result = _apply_op(unpacked, op, args.dry_run, cache)
            report['ops'].append(result)
            if result['action'] in {'replace', 'clear'}:
                report['applied'] += 1
        except Exception as exc:
            report['errors'].append({'index': i, 'op': op, 'error': str(exc)})

    # 原子性：仅当本次没有任何 op 出错时才落盘。否则丢弃全部改动，让模型修正
    # content_plan 后在未改动的 unpacked 上干净重跑（apply_plan 出错即停）。
    if not args.dry_run and not report['errors']:
        for ctx in cache.values():
            if ctx['dirty']:
                ctx['tree'].write(ctx['path'], xml_declaration=True, encoding='UTF-8')

    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    if report['errors']:
        print(json.dumps({
            'hint': (
                '只修 content_plan.json，不要修改脚本。字段名必须是 paragraphs。'
                ' action=replace 时 paragraphs 不能是空数组；不需要替换的项改成 keep，'
                '需要删除模板文字的项改成 clear。'
            ),
            'valid_text_item': {
                'ref': 'slide5:shape3',
                'action': 'replace',
                'paragraphs': ['新文案'],
            },
            'errors': report['errors'][:8],
        }, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2
    if report['applied'] <= 0:
        print('没有任何 replace/clear 操作被应用；请检查 content_plan.json。', file=sys.stderr)
        return 2

    verb = '可应用' if args.dry_run else '已应用'
    if not args.quiet:
        print(f"{verb} {report['applied']}/{report['planned']} 个文本操作。")
    if args.report and not args.quiet:
        print(f"报告: {args.report}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
