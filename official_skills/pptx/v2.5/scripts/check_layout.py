#!/usr/bin/env python3
"""PPT 几何复核：检测元素溢出画布、形状重叠、文本疑似溢出。

直接对 .pptx（zip）解析各页 spTree 中 shape 的位置/尺寸（EMU），含 grpSp 内嵌套
形状的坐标换算，无需第三方库。输出结构化问题清单（JSON 或人读文本，含 geom 坐标），
供 agent 定位并返修（缩短文案 / adjust_shape 设 autofit 或移动缩放文本框）。
残留模板文本的判定不在此处，由 verify_content 的 untouched_template_text 数据驱动完成。

用法：
    python check_layout.py output.pptx                # 人读报告
    python check_layout.py output.pptx --json         # JSON 输出
    python check_layout.py output.pptx --overlap 0.25  # 调整重叠面积阈值（默认 0.5）

退出码：blocking 问题返回 2，无 blocking 返回 0，解析失败返回 1。
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import tempfile
import zipfile
from pathlib import Path

from xml.etree import ElementTree as ET


_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_SLD_SZ = re.compile(r'<p:sldSz[^>]*cx="(\d+)"[^>]*cy="(\d+)"')

_SHAPE_TAGS = ('sp', 'pic', 'graphicFrame', 'cxnSp', 'grpSp')


def _emu_to_inch(emu: float) -> float:
    return emu / 914400.0


def _own_xfrm(elem: ET.Element) -> ET.Element | None:
    """该元素自身的 a:xfrm（spPr/grpSpPr/graphicFrame 的第一个 xfrm，先于任何子级）。"""
    return elem.find(f'.//{{{_A}}}xfrm')


def _xy(node: ET.Element | None, ax: str, ay: str) -> tuple[int, int] | None:
    if node is None:
        return None
    try:
        return int(node.get(ax, '0')), int(node.get(ay, '0'))
    except (TypeError, ValueError):
        return None


def _extract_props(elem: ET.Element, tag: str) -> dict:
    name = ''
    nv = elem.find(f'.//{{{_P}}}cNvPr')
    if nv is not None:
        name = nv.get('name', '')
    texts = [t.text or '' for t in elem.findall(f'.//{{{_A}}}t')]
    text = ''.join(texts).strip()
    paras: list[str] = []
    for para in elem.findall(f'.//{{{_A}}}p'):
        pt = ''.join(t.text or '' for t in para.findall(f'.//{{{_A}}}t'))
        paras.append(pt)
    # 字号（百分点，sz=1800 表示 18pt）：取该形状内**最小**字号做保守估算
    # （混排时最小字最容易塞不下，用它估行容量更不易误杀也不漏报）。
    sizes: list[float] = []
    for rpr in elem.iter():
        if rpr.tag in (f'{{{_A}}}rPr', f'{{{_A}}}defRPr', f'{{{_A}}}endParaRPr'):
            sz = rpr.get('sz')
            if sz:
                try:
                    sizes.append(int(sz) / 100.0)
                except ValueError:
                    pass
    font_pt = min(sizes) if sizes else None
    # normAutofit：PPT 会自动缩字以适配框，故不应把它判成"塞不下"的硬阻断。
    norm_autofit = elem.find(f'.//{{{_A}}}normAutofit') is not None
    return {'name': name, 'kind': tag, 'text': text, 'paras': paras,
            'font_pt': font_pt, 'norm_autofit': norm_autofit}


def _walk_shapes(parent: ET.Element, transform: tuple[float, float, float, float],
                 slide_no: int, counter: list[int], grouped: bool):
    """递归遍历 spTree，把（可能嵌套在 grpSp 里的）形状坐标换算到幻灯片 EMU 空间。

    transform=(tx,ty,sx,sy) 表示 slideX = tx + localX*sx，slideY = ty + localY*sy。
    grpSp 用 off/ext 与 chOff/chExt 推导子级的新 transform，支持任意层级嵌套。
    p:sp 的 ref 按文档序编号，与 inspect/verify/replace 的 root.iter(sp) 顺序一致。
    """
    tx, ty, sx, sy = transform
    for child in list(parent):
        tag = child.tag.split('}')[-1]
        if tag not in _SHAPE_TAGS:
            continue
        if tag == 'sp':
            counter[0] += 1
        xfrm = _own_xfrm(child)
        off = _xy(xfrm.find(f'{{{_A}}}off') if xfrm is not None else None, 'x', 'y')
        ext = _xy(xfrm.find(f'{{{_A}}}ext') if xfrm is not None else None, 'cx', 'cy')
        if off is None or ext is None:
            continue
        X = tx + off[0] * sx
        Y = ty + off[1] * sy
        CX = ext[0] * sx
        CY = ext[1] * sy
        if tag == 'grpSp':
            # 用 chOff/chExt 推导子坐标系 → 幻灯片空间的新 transform，再递归。
            ch_off = _xy(xfrm.find(f'{{{_A}}}chOff'), 'x', 'y') or (0, 0)
            ch_ext = _xy(xfrm.find(f'{{{_A}}}chExt'), 'cx', 'cy') or ext
            csx = (ext[0] / ch_ext[0]) * sx if ch_ext[0] else sx
            csy = (ext[1] / ch_ext[1]) * sy if ch_ext[1] else sy
            ctx = tx + (off[0] - ch_off[0] * (ext[0] / ch_ext[0] if ch_ext[0] else 1)) * sx
            cty = ty + (off[1] - ch_off[1] * (ext[1] / ch_ext[1] if ch_ext[1] else 1)) * sy
            yield from _walk_shapes(child, (ctx, cty, csx, csy), slide_no, counter, True)
            continue
        rec = _extract_props(child, tag)
        rec.update({'x': int(X), 'y': int(Y), 'cx': int(CX), 'cy': int(CY),
                    'ref': f'slide{slide_no}:shape{counter[0]}' if tag == 'sp' else None,
                    'grouped': grouped})
        yield rec


def _iter_shapes(sptree: ET.Element, slide_no: int):
    """产出所有形状（含 grpSp 内嵌套形状，坐标已换算到幻灯片 EMU 空间）。"""
    yield from _walk_shapes(sptree, (0.0, 0.0, 1.0, 1.0), slide_no, [0], False)


def _overlap_area(a: dict, b: dict) -> int:
    ix = max(0, min(a['x'] + a['cx'], b['x'] + b['cx']) - max(a['x'], b['x']))
    iy = max(0, min(a['y'] + a['cy'], b['y'] + b['cy']) - max(a['y'], b['y']))
    return ix * iy


_EMU_PER_PT = 12700.0


def _text_width_units(s: str) -> float:
    """文本所占宽度（以「字号」为单位）：中文/全角≈1.0，拉丁/数字≈0.55。"""
    w = 0.0
    for ch in s:
        if ch in (' ', '\t'):
            w += 0.3
        elif '\u4e00' <= ch <= '\u9fff' or '\u3000' <= ch <= '\u303f' \
                or '\uff00' <= ch <= '\uffef':
            w += 1.0
        else:
            w += 0.55
    return w


def _est_text_overflow(shape: dict) -> float:
    """估算文本"所需行数 / 框可容行数"的比值。<=0 表示不适用/无需判定。

    比纯字符数更准：考虑字号、框宽（每行可容字数）、框高（可容行数）与中英文混排。
    返回比值供调用方分级：>1.15 视为溢出预警；远超（如 ≥2）说明文本被塞进了
    明显放不下的框（典型：长文案塞进数字/短标签槽），应升级为阻断。
    """
    if shape['kind'] != 'sp':
        return 0.0
    paras = shape.get('paras') or ([shape['text']] if shape['text'] else [])
    paras = [p for p in paras if p and p.strip()]
    if not paras:
        return 0.0
    total_chars = sum(len(p) for p in paras)
    if total_chars < 12:
        return 0.0
    cx_pt = shape['cx'] / _EMU_PER_PT
    cy_pt = shape['cy'] / _EMU_PER_PT
    if cx_pt <= 0 or cy_pt <= 0:
        return 0.0
    font_pt = shape.get('font_pt') or 18.0
    # 每行可容宽度（字号单位）；预留约 6% 内边距
    line_capacity = (cx_pt * 0.94) / font_pt
    if line_capacity < 1:
        return 0.0
    lines_needed = 0
    for p in paras:
        units = _text_width_units(p)
        lines_needed += max(1, math.ceil(units / line_capacity))
    # 可用行数：行高约 1.2 倍字号
    lines_available = cy_pt / (font_pt * 1.2)
    if lines_available <= 0:
        return 0.0
    return lines_needed / lines_available


# 溢出预警/阻断阈值（所需行数 ÷ 可容行数）
_OVERFLOW_WARN = 1.15
_OVERFLOW_SEVERE = 2.0


def _has_text(shape: dict) -> bool:
    return bool(shape['text'] and shape['text'].strip())


def _issue_signature(issue: dict) -> tuple:
    # 不含页号：复制/重排页后页号会变，但形状名+类型+几何坐标在拷贝中保持一致，
    # 故用 (type, shape, geom) 作签名，让模板原生问题在重排/复制后仍能匹配基线降级。
    return (issue.get('type'), issue.get('shape'), issue.get('geom'))


def _classify_issues(issues: list[dict], baseline_issues: list[dict] | None = None) -> None:
    baseline_sigs = {_issue_signature(i) for i in baseline_issues or []}
    geometry_types = {'overflow', 'overlap', 'text_overflow'}
    for issue in issues:
        # 文本溢出按"超框倍数"分级：模板原生/组合内/轻度→warning；
        # 非基线且远超框高（≥SEVERE，典型为长文案塞进数字/短标签槽）→blocking，逼模型修。
        if issue.get('type') == 'text_overflow':
            is_baseline = _issue_signature(issue) in baseline_sigs
            severe = (issue.get('overflow_ratio') or 0) >= _OVERFLOW_SEVERE
            issue['baseline'] = is_baseline
            # normAutofit 的框 PPT 会自动缩字适配，不阻断；其余远超框高的非基线溢出才阻断
            if severe and not is_baseline and not issue.get('grouped') and not issue.get('norm_autofit'):
                issue['severity'] = 'blocking'
            else:
                issue['severity'] = 'warning'
        elif issue.get('grouped'):
            # 组合形状内的几何问题：坐标系换算有近似、且分组多为设计装饰，
            # 给足容忍——只预警、绝不阻断 PPT 生成。
            issue['severity'] = 'warning'
            issue['baseline'] = _issue_signature(issue) in baseline_sigs
        elif issue.get('type') in geometry_types and _issue_signature(issue) in baseline_sigs:
            issue['severity'] = 'warning'
            issue['baseline'] = True
        else:
            issue['severity'] = 'blocking'
            issue['baseline'] = False


def _zip_unpacked(unpacked: Path) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix='.pptx', delete=False)
    tmp_path = Path(tmp.name)
    tmp.close()
    with zipfile.ZipFile(tmp_path, 'w', zipfile.ZIP_DEFLATED) as z:
        for path in unpacked.rglob('*'):
            if path.is_file():
                z.write(path, path.relative_to(unpacked).as_posix())
    return tmp_path


def check_pptx(pptx_path: str, overlap_thresh: float = 0.5, baseline_template: str | None = None) -> dict:
    issues: list[dict] = []
    original_path = pptx_path
    temp_path: Path | None = None
    path_obj = Path(pptx_path)
    if path_obj.is_dir():
        temp_path = _zip_unpacked(path_obj)
        pptx_path = str(temp_path)
    with zipfile.ZipFile(pptx_path) as z:
        names = z.namelist()
        # slide 尺寸
        cx = cy = 0
        try:
            pres = z.read('ppt/presentation.xml').decode('utf-8', 'ignore')
            m = _SLD_SZ.search(pres)
            if m:
                cx, cy = int(m.group(1)), int(m.group(2))
        except KeyError:
            pass

        slide_names = sorted(
            (n for n in names if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)),
            key=lambda s: int(re.search(r'(\d+)', s).group(1)),
        )
        for n in slide_names:
            slide_no = int(re.search(r'slide(\d+)', n).group(1))
            try:
                root = ET.fromstring(z.read(n))
            except ET.ParseError as exc:
                issues.append({'slide': slide_no, 'type': 'xml_parse', 'detail': str(exc)})
                continue
            sptree = root.find(f'.//{{{_P}}}spTree')
            if sptree is None:
                continue
            shapes = list(_iter_shapes(sptree, slide_no))
            # 复核以「文字可读性」为中心：模板里文本框压在背景图/装饰形状上、
            # 装饰元素出血到画布外都是正常设计，不应误报。只盯住会真正影响阅读的问题。
            text_shapes = [s for s in shapes if _has_text(s)]

            # 1) 文字被画布裁掉：仅检查带文字的形状明显超出画布
            if cx and cy:
                margin = int(914400 * 0.15)  # 容忍 0.15 inch 出血/边距
                for s in text_shapes:
                    out_left = -s['x']
                    out_top = -s['y']
                    out_right = (s['x'] + s['cx']) - cx
                    out_bottom = (s['y'] + s['cy']) - cy
                    worst = max(out_left, out_top, out_right, out_bottom)
                    # 组合形状坐标系换算有近似，给 4 倍 buffer，避免误报。
                    eff_margin = margin * 4 if s.get('grouped') else margin
                    if worst > eff_margin:
                        issues.append({
                            'slide': slide_no, 'type': 'overflow', 'shape': s['name'] or s['kind'],
                            'ref': s.get('ref'), 'grouped': s.get('grouped', False),
                            'geom': (s['x'], s['y'], s['cx'], s['cy']),
                            'detail': f"文字框超出画布 {_emu_to_inch(worst):.2f}in: "
                                      f"{s['text'][:20]}",
                        })

            # 2) 文字互相压字：仅在两个都带文字的框显著重叠时报（背景图层叠不算）
            for i in range(len(text_shapes)):
                for j in range(i + 1, len(text_shapes)):
                    a, b = text_shapes[i], text_shapes[j]
                    area_a = a['cx'] * a['cy']
                    area_b = b['cx'] * b['cy']
                    if area_a <= 0 or area_b <= 0:
                        continue
                    ov = _overlap_area(a, b)
                    if ov <= 0:
                        continue
                    ratio = ov / min(area_a, area_b)
                    if ratio >= overlap_thresh:
                        issues.append({
                            'slide': slide_no, 'type': 'overlap',
                            'shape': f"{a['name'] or a['kind']} ∩ {b['name'] or b['kind']}",
                            'ref': ' ∩ '.join(x for x in (a.get('ref'), b.get('ref')) if x),
                            'grouped': bool(a.get('grouped') or b.get('grouped')),
                            'geom': (a['x'], a['y'], a['cx'], a['cy'], b['x'], b['y'], b['cx'], b['cy']),
                            'detail': f'两个文字框重叠 {ratio:.0%}（可能压字）',
                        })

            # 3) 文本疑似溢出
            for s in shapes:
                ratio = _est_text_overflow(s)
                if ratio > _OVERFLOW_WARN:
                    issues.append({
                        'slide': slide_no, 'type': 'text_overflow', 'shape': s['name'] or s['kind'],
                        'ref': s.get('ref'), 'grouped': s.get('grouped', False),
                        'norm_autofit': s.get('norm_autofit', False),
                        'overflow_ratio': round(ratio, 2),
                        'geom': (s['x'], s['y'], s['cx'], s['cy']),
                        'detail': f"文字偏多疑似溢出（{len(s['text'])} 字，约需 {ratio:.1f} 倍框高）: {s['text'][:24]}…",
                        'suggestion': '缩短该 ref，或用 adjust_shape 设 normAutofit 让字自适应/适当放大文本框。',
                    })
    if temp_path is not None:
        temp_path.unlink(missing_ok=True)

    baseline_issues: list[dict] | None = None
    if baseline_template:
        baseline_issues = check_pptx(baseline_template, overlap_thresh=overlap_thresh)['issues']
    _classify_issues(issues, baseline_issues)
    blocking = sum(1 for i in issues if i.get('severity') == 'blocking')
    warning = sum(1 for i in issues if i.get('severity') == 'warning')
    return {
        'pptx': original_path,
        'baseline_template': baseline_template,
        'blocking_count': blocking,
        'warning_count': warning,
        'issue_count': len(issues),
        'issues': issues,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='PPT 几何与内容复核')
    ap.add_argument('pptx')
    ap.add_argument('--json', action='store_true', help='以 JSON 输出')
    ap.add_argument('--overlap', type=float, default=0.5,
                    help='两个文字框重叠的报警阈值（占较小框比例，默认 0.5）')
    ap.add_argument('--baseline-template',
                    help='原始模板 pptx；模板原生几何问题降级为 warning')
    ap.add_argument('--report', help='兼容参数：将 JSON 报告写入指定文件')
    args = ap.parse_args()

    try:
        report = check_pptx(args.pptx, overlap_thresh=args.overlap, baseline_template=args.baseline_template)
    except (zipfile.BadZipFile, OSError) as exc:
        print(f'无法读取 {args.pptx}: {exc}', file=sys.stderr)
        return 1

    json_text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(json_text, encoding='utf-8')

    if args.json:
        print(json_text)
    else:
        if report['issue_count'] == 0:
            print('复核通过：未发现溢出/重叠/文本溢出问题。')
        else:
            print(f"发现 {report['blocking_count']} 个 blocking、{report['warning_count']} 个 warning：")
            for it in report['issues']:
                print(f"  [第{it['slide']}页][{it.get('severity')}][{it['type']}] {it.get('shape', '')} — {it['detail']}")
    return 2 if report['blocking_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
