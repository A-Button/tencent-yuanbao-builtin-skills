#!/usr/bin/env python3
"""Adjust shape autofit and geometry on existing PPTX template shapes.

让模型在读到 check_layout 的 overflow/overlap 报告后，能自主修复版式而**不必**改文案：
  - autofit：把文本框设为 normAutofit（字自动缩小适配固定框，最常用）/ spAutoFit
    （框适配字）/ noAutofit；可选 fontScale / lnSpcReduction（百分点，9000=90%）。
  - geometry：移动/缩放文本框（设置或增量调整 a:xfrm 的 off/ext）。

输入 ops（JSON 数组，每个 op 一个 ref）：
  {"ref":"slide5:shape3","autofit":"normal","fontScale":90}
  {"ref":"slide7:shape2","box":{"dx":-200000,"dcx":400000}}   # 增量(EMU)
  {"ref":"slide7:shape2","box":{"x":914400,"y":914400,"cx":3657600,"cy":1828800}}  # 绝对(EMU)
  {"ref":"slide5:shape3","fontColor":"FFFFFF"}   # 改字色修低对比度（6 位十六进制）
  {"ref":"slide5:shape3","anchor":"ctr"}         # 文本垂直居中 ctr/t/b

autofit 取值：normal|norm|normAutofit / shape|spAutoFit / none|noAutofit。
ref 编号与 inspect_deck/replace_text 一致（按 p:sp 文档序）。越出画布仅记 warning，不阻断。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

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

_AUTOFIT_ALIASES = {
    'normal': 'normAutofit', 'norm': 'normAutofit', 'normautofit': 'normAutofit',
    'shrink': 'normAutofit', 'fit': 'normAutofit',
    'shape': 'spAutoFit', 'spautofit': 'spAutoFit', 'grow': 'spAutoFit',
    'none': 'noAutofit', 'noautofit': 'noAutofit', 'off': 'noAutofit',
}


def _parse_ref(ref: str) -> tuple[int, int]:
    m = _REF_RE.match(ref or '')
    if not m:
        raise ValueError(f'非法 ref: {ref!r}，应类似 slide5:shape3')
    return int(m.group(1)), int(m.group(2))


def _slide_path(unpacked: Path, slide: int) -> Path:
    return unpacked / 'ppt' / 'slides' / f'slide{slide}.xml'


def _slide_size(unpacked: Path) -> tuple[int, int]:
    pres = unpacked / 'ppt' / 'presentation.xml'
    try:
        sz = ET.parse(pres).getroot().find(f'{{{_P}}}sldSz')
        if sz is not None:
            return int(sz.get('cx', '0')), int(sz.get('cy', '0'))
    except (ET.ParseError, FileNotFoundError, TypeError, ValueError):
        pass
    return 0, 0


def _set_autofit(shape: ET.Element, mode: str, font_scale, ln_spc) -> None:
    tx_body = shape.find(f'{{{_P}}}txBody')
    if tx_body is None:
        raise ValueError('该 shape 无 p:txBody，不能设 autofit')
    body_pr = tx_body.find(f'{{{_A}}}bodyPr')
    if body_pr is None:
        body_pr = ET.Element(f'{{{_A}}}bodyPr')
        tx_body.insert(0, body_pr)
    # 移除已有的三选一 autofit 子元素
    for tag in ('noAutofit', 'normAutofit', 'spAutoFit'):
        for el in body_pr.findall(f'{{{_A}}}{tag}'):
            body_pr.remove(el)
    af = ET.Element(f'{{{_A}}}{mode}')
    if mode == 'normAutofit':
        if font_scale is not None:
            af.set('fontScale', str(int(font_scale * 1000) if font_scale <= 100 else int(font_scale)))
        if ln_spc is not None:
            af.set('lnSpcReduction', str(int(ln_spc * 1000) if ln_spc <= 100 else int(ln_spc)))
    # autofit 须在 prstTxWarp 之后（若有），否则作 bodyPr 首个子元素
    warp = body_pr.find(f'{{{_A}}}prstTxWarp')
    body_pr.insert(list(body_pr).index(warp) + 1 if warp is not None else 0, af)


def _set_font_color(shape: ET.Element, color: str) -> None:
    """把文本框内所有 run 的字色设为指定 srgb（用于修复低对比度）。

    给每个 a:r 的 rPr 写入 <a:solidFill><a:srgbClr val=.../></a:solidFill>；缺 rPr 则新建。
    末段 endParaRPr 也同步，避免新输入继承旧色。
    """
    hexv = (color or '').strip().lstrip('#').upper()
    if not re.fullmatch(r'[0-9A-F]{6}', hexv):
        raise ValueError(f'fontColor 非法（需 6 位十六进制如 FFFFFF）: {color!r}')
    tx_body = shape.find(f'{{{_P}}}txBody')
    if tx_body is None:
        raise ValueError('该 shape 无 p:txBody，不能设字色')

    # CT_TextCharacterProperties 的 schema 顺序是 ln → 填充组(取其一：noFill/solidFill/
    # gradFill/blipFill/pattFill/grpFill) → 效果组 → highlight → ...。若该 run 带描边
    # <a:ln>（常见于加粗大字/描边数字），solidFill 必须插在 ln **之后**，插到首位会把顺序
    # 弄反，产生 schema 非法的 XML——PowerPoint/后续重打包可能直接丢弃或忽略这个 fill，
    # 表现为"脚本说改色成功，但打开/复检时颜色根本没变"。
    _FILL_TAGS = ('noFill', 'solidFill', 'gradFill', 'blipFill', 'pattFill', 'grpFill')

    def _apply(rpr: ET.Element) -> None:
        # 填充组互斥，只能有一个：先把旧的（不论哪种）全部清掉，避免和新 solidFill 并存。
        for tag in _FILL_TAGS:
            for old in rpr.findall(f'{{{_A}}}{tag}'):
                rpr.remove(old)
        sf = ET.Element(f'{{{_A}}}solidFill')
        clr = ET.SubElement(sf, f'{{{_A}}}srgbClr')
        clr.set('val', hexv)
        ln = rpr.find(f'{{{_A}}}ln')
        insert_at = list(rpr).index(ln) + 1 if ln is not None else 0
        rpr.insert(insert_at, sf)

    touched = 0
    for para in tx_body.findall(f'{{{_A}}}p'):
        for run in para.findall(f'{{{_A}}}r'):
            rpr = run.find(f'{{{_A}}}rPr')
            if rpr is None:
                rpr = ET.Element(f'{{{_A}}}rPr')
                run.insert(0, rpr)
            _apply(rpr)
            touched += 1
        epr = para.find(f'{{{_A}}}endParaRPr')
        if epr is not None:
            _apply(epr)
    if touched == 0:
        raise ValueError('该 shape 无文本 run，无法设字色')


def _set_anchor(shape: ET.Element, anchor: str) -> None:
    """设文本垂直对齐：ctr/t/b（写 bodyPr@anchor）。"""
    mode = {'ctr': 'ctr', 'center': 'ctr', 'middle': 'ctr',
            't': 't', 'top': 't', 'b': 'b', 'bottom': 'b'}.get(str(anchor).lower())
    if not mode:
        raise ValueError(f'anchor 取值非法: {anchor!r}（用 ctr/t/b）')
    tx_body = shape.find(f'{{{_P}}}txBody')
    if tx_body is None:
        raise ValueError('该 shape 无 p:txBody，不能设 anchor')
    body_pr = tx_body.find(f'{{{_A}}}bodyPr')
    if body_pr is None:
        body_pr = ET.Element(f'{{{_A}}}bodyPr')
        tx_body.insert(0, body_pr)
    body_pr.set('anchor', mode)


def _set_geometry(shape: ET.Element, box: dict, canvas: tuple[int, int]) -> list[str]:
    warns: list[str] = []
    sp_pr = shape.find(f'{{{_P}}}spPr')
    if sp_pr is None:
        raise ValueError('该 shape 无 p:spPr，不能改几何')
    xfrm = sp_pr.find(f'{{{_A}}}xfrm')
    if xfrm is None:
        # 没有显式 xfrm（继承自占位符）：增量无基准，只能用绝对值新建。
        if any(k in box for k in ('dx', 'dy', 'dcx', 'dcy')):
            warns.append('该 shape 无显式 xfrm，增量调整无基准，已跳过；请用绝对 x/y/cx/cy')
            return warns
        xfrm = ET.Element(f'{{{_A}}}xfrm')
        sp_pr.insert(0, xfrm)
    off = xfrm.find(f'{{{_A}}}off')
    if off is None:
        off = ET.SubElement(xfrm, f'{{{_A}}}off'); off.set('x', '0'); off.set('y', '0')
    ext = xfrm.find(f'{{{_A}}}ext')
    if ext is None:
        ext = ET.SubElement(xfrm, f'{{{_A}}}ext'); ext.set('cx', '0'); ext.set('cy', '0')
    x = int(off.get('x', '0')); y = int(off.get('y', '0'))
    cx = int(ext.get('cx', '0')); cy = int(ext.get('cy', '0'))
    x = int(box.get('x', x)) + int(box.get('dx', 0))
    y = int(box.get('y', y)) + int(box.get('dy', 0))
    cx = int(box.get('cx', cx)) + int(box.get('dcx', 0))
    cy = int(box.get('cy', cy)) + int(box.get('dcy', 0))
    if cx <= 0 or cy <= 0:
        raise ValueError(f'宽高必须为正：cx={cx} cy={cy}')
    off.set('x', str(x)); off.set('y', str(y))
    ext.set('cx', str(cx)); ext.set('cy', str(cy))
    scx, scy = canvas
    if scx and scy and (x < 0 or y < 0 or x + cx > scx or y + cy > scy):
        warns.append(f'调整后超出画布（x={x},y={y},cx={cx},cy={cy} vs {scx}x{scy}）')
    return warns


def apply_ops(unpacked: Path, ops: list[dict]) -> dict:
    canvas = _slide_size(unpacked)
    report = {'planned': len(ops), 'applied': 0, 'ops': [], 'errors': [], 'warnings': []}
    cache: dict[int, dict] = {}
    for i, op in enumerate(ops, start=1):
        try:
            slide, shape_idx = _parse_ref(op.get('ref'))
            if slide not in cache:
                path = _slide_path(unpacked, slide)
                if not path.exists():
                    raise FileNotFoundError(f'找不到 {path}')
                tree = ET.parse(path)
                cache[slide] = {'path': path, 'tree': tree, 'root': tree.getroot(), 'dirty': False}
            ctx = cache[slide]
            shapes = list(ctx['root'].iter(f'{{{_P}}}sp'))
            if shape_idx < 1 or shape_idx > len(shapes):
                raise IndexError(f'{op.get("ref")} 不存在；第 {slide} 页有 {len(shapes)} 个 shape')
            shape = shapes[shape_idx - 1]
            did = []
            if op.get('autofit') is not None:
                mode = _AUTOFIT_ALIASES.get(str(op['autofit']).lower())
                if not mode:
                    raise ValueError(f'autofit 取值非法: {op["autofit"]!r}')
                _set_autofit(shape, mode, op.get('fontScale'), op.get('lnSpcReduction'))
                did.append(f'autofit={mode}')
                ctx['dirty'] = True
            if isinstance(op.get('box'), dict):
                warns = _set_geometry(shape, op['box'], canvas)
                for w in warns:
                    report['warnings'].append({'ref': op.get('ref'), 'detail': w})
                did.append('box')
                ctx['dirty'] = True
            if op.get('fontColor') is not None:
                _set_font_color(shape, str(op['fontColor']))
                did.append(f'fontColor={op["fontColor"]}')
                ctx['dirty'] = True
            if op.get('anchor') is not None:
                _set_anchor(shape, str(op['anchor']))
                did.append(f'anchor={op["anchor"]}')
                ctx['dirty'] = True
            if not did:
                raise ValueError('op 无 autofit/box/fontColor/anchor 任一可执行项')
            report['ops'].append({'ref': op.get('ref'), 'did': did, 'ok': True})
            report['applied'] += 1
        except Exception as exc:
            report['errors'].append({'index': i, 'op': op, 'error': str(exc)})

    if not report['errors']:
        for ctx in cache.values():
            if ctx['dirty']:
                ctx['tree'].write(ctx['path'], xml_declaration=True, encoding='UTF-8')
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description='Adjust shape autofit/geometry by ref.')
    ap.add_argument('unpacked')
    ap.add_argument('ops_json', help='JSON 数组文件；每个 op 含 ref + autofit/box')
    ap.add_argument('--report', help='把 JSON 报告写到该路径')
    args = ap.parse_args()

    try:
        ops = json.loads(Path(args.ops_json).read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        print(f'ops JSON 解析失败: {exc}', file=sys.stderr)
        return 2
    if not isinstance(ops, list):
        print('ops 必须是 JSON 数组', file=sys.stderr)
        return 2

    report = apply_ops(Path(args.unpacked), ops)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding='utf-8')
    print(text)
    return 2 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
