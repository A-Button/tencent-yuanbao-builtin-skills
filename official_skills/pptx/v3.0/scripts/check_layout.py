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
    # 字号（百分点，sz=1800 表示 18pt）：取该形状内最大字号估算可用容量。
    # 旧实现取最小字号，会让大号主文字按脚注/单位的小字号计算，系统性漏掉数字位、
    # 指标卡和并列标题的真实溢出。
    sizes: list[float] = []
    for rpr in elem.iter():
        if rpr.tag in (f'{{{_A}}}rPr', f'{{{_A}}}defRPr', f'{{{_A}}}endParaRPr'):
            sz = rpr.get('sz')
            if sz:
                try:
                    sizes.append(int(sz) / 100.0)
                except ValueError:
                    pass
    font_pt = max(sizes) if sizes else None
    body_pr = elem.find(f'.//{{{_A}}}bodyPr')
    # DrawingML 默认左右内边距 0.1in、上下 0.05in；显式为 0 时必须尊重模板设置。
    def _inset(name: str, default: int) -> int:
        if body_pr is None or body_pr.get(name) is None:
            return default
        try:
            return int(body_pr.get(name, str(default)))
        except ValueError:
            return default
    insets = {
        'l': _inset('lIns', 91440), 'r': _inset('rIns', 91440),
        't': _inset('tIns', 45720), 'b': _inset('bIns', 45720),
    }
    # normAutofit：PPT 会自动缩字以适配框，故不应把它判成"塞不下"的硬阻断。
    norm_autofit = elem.find(f'.//{{{_A}}}normAutofit') is not None
    return {'name': name, 'kind': tag, 'text': text, 'paras': paras,
            'font_pt': font_pt, 'norm_autofit': norm_autofit, 'insets': insets}


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


def estimate_overflow(paras: list[str], cx_emu: float, cy_emu: float,
                      insets: dict | None, font_pt: float,
                      width_safety: float = 1.0) -> dict:
    """估算文本在给定框/字号下的排布细节。返回 {ratio, lines_needed, lines_available}。

    考虑字号、框宽（每行可容字数）、框高（可容行数）与中英文混排。是「几何复核」与
    「生成阶段写入自适配」共用的单一事实来源，避免两处逻辑漂移。

    width_safety<1：给每行可容宽度打折，预留安全余量。字宽单位模型（CJK=1.0、拉丁=0.55）
    是理想字距，真实渲染里粗体字重、字体实际字距、符号（如 '/'）宽度都会略宽于模型；对
    「绝不该换行」的短标签，反解字号时必须留余量，否则会卡在"模型刚好判定单行"的临界点，
    真实渲染再宽一丁点就折行（复盘：数字卡『北京/重庆/深圳』把"圳"挤到第二行）。
    """
    empty = {'ratio': 0.0, 'lines_needed': 0, 'lines_available': 0.0}
    paras = [p for p in (paras or []) if p and p.strip()]
    if not paras:
        return empty
    insets = insets or {}
    cx_pt = (cx_emu - insets.get('l', 0) - insets.get('r', 0)) / _EMU_PER_PT
    cy_pt = (cy_emu - insets.get('t', 0) - insets.get('b', 0)) / _EMU_PER_PT
    if cx_pt <= 0 or cy_pt <= 0 or font_pt <= 0:
        return empty
    # 每行可容宽度（字号单位）；内边距已从实际 bodyPr 精确扣除。
    line_capacity = cx_pt / font_pt
    # 字号大到一行连一个字都放不下时（line_capacity<1）旧实现直接返回 0，会系统性
    # 漏掉"窄框塞大字"（如 96pt 的『万人次』塞进 1.1in 宽的框，逐字竖排后严重压字）。
    # 改为：每行至少容 1 个字来估行数，并额外用 1/line_capacity 反映横向撑爆的程度。
    safe_capacity = line_capacity * max(0.5, min(1.0, width_safety))
    chars_per_line = max(1.0, safe_capacity)
    width_overflow = max(1.0, 1.0 / safe_capacity) if safe_capacity < 1 else 1.0
    lines_needed = 0
    for p in paras:
        units = _text_width_units(p)
        lines_needed += max(1, math.ceil(units / chars_per_line))
    lines_available = cy_pt / (font_pt * 1.2)  # 行高约 1.2 倍字号
    if lines_available <= 0:
        return {'ratio': 0.0, 'lines_needed': lines_needed, 'lines_available': 0.0}
    ratio = max(lines_needed / lines_available, width_overflow)
    return {'ratio': ratio, 'lines_needed': lines_needed, 'lines_available': lines_available}


def estimate_overflow_ratio(paras: list[str], cx_emu: float, cy_emu: float,
                            insets: dict | None, font_pt: float) -> float:
    """溢出比：>1.15 预警；远超（≥1.2）多为长文塞短槽，应阻断或缩字适配。"""
    return estimate_overflow(paras, cx_emu, cy_emu, insets, font_pt)['ratio']


def fit_font_scale(paras: list[str], cx_emu: float, cy_emu: float,
                   insets: dict | None, font_pt: float,
                   floor: float = 0.30, target: float = 1.0,
                   max_lines: int | None = None) -> float:
    """反解「让文本恰好放进框」所需的字号缩放比 s∈(floor,1]。

    当前字号已能放下（比值≤1.15）时返回 1.0（不缩）。否则从 1.0 逐步下探，找到第一个
    满足条件的缩放；到 floor 仍放不下则返回 floor（有底线，避免缩成不可读）。

    max_lines：允许的最大渲染行数。对单位/短标签这类**绝不该换行**的文本，传入其显式
    段数（通常 1），据此要求缩到"每段单行放下"，而不是"面积能塞下（可换行）"——否则会
    出现『万人次』被折成『万人/次』这种明显错误的单位格式。默认 None = 仅按面积适配。

    注意：早返回（判定"当前字号已放下、无需缩"）必须同时满足行数约束——否则一个在够高的框里
    横向折成两行、但面积比仍 ≤1.15 的短标签会被当成"放得下"直接放行，max_lines 单行约束根本
    没机会生效（复盘：数字卡『15万+公里』折成三行断字就是这么漏过去的）。
    """
    # 单行短标签用更大的宽度安全余量（真实渲染比理想字宽模型宽，粗体/字距/符号叠加）；
    # 正文换行留一点点余量即可，避免行尾最后一个字被挤出。
    safety = _LABEL_WIDTH_SAFETY if max_lines is not None else _BODY_WIDTH_SAFETY
    est0 = estimate_overflow(paras, cx_emu, cy_emu, insets, font_pt, safety)
    if est0['ratio'] <= _OVERFLOW_WARN and (max_lines is None or est0['lines_needed'] <= max_lines):
        return 1.0
    s = 1.0
    while s > floor:
        s -= 0.02
        est = estimate_overflow(paras, cx_emu, cy_emu, insets, font_pt * s, safety)
        if est['ratio'] <= target and (max_lines is None or est['lines_needed'] <= max_lines):
            return round(s, 2)
    return round(floor, 2)


def _est_text_overflow(shape: dict) -> float:
    if shape['kind'] != 'sp':
        return 0.0
    paras = shape.get('paras') or ([shape['text']] if shape['text'] else [])
    return estimate_overflow_ratio(paras, shape['cx'], shape['cy'],
                                   shape.get('insets'), shape.get('font_pt') or 18.0)


# 反解字号时的宽度安全余量：单行短标签留 ~15%，正文留 ~5%。
_LABEL_WIDTH_SAFETY = 0.85
_BODY_WIDTH_SAFETY = 0.95

# 溢出预警/阻断阈值（所需行数 ÷ 可容行数）
_OVERFLOW_WARN = 1.15
_OVERFLOW_SEVERE = 1.20
# 短标题/短标签只要明确超框就很刺眼；与正文使用相同的质量门槛。
_OVERFLOW_HEADING = 1.20


def _has_text(shape: dict) -> bool:
    return bool(shape['text'] and shape['text'].strip())


def _issue_signature(issue: dict) -> tuple:
    # 不含页号：复制/重排页后页号会变，但形状名+类型+几何坐标在拷贝中保持一致，
    # 故用 (type, shape, geom) 作签名，让模板原生问题在重排/复制后仍能匹配基线降级。
    return (issue.get('type'), issue.get('shape'), issue.get('geom'))


def _classify_issues(issues: list[dict], baseline_issues: list[dict] | None = None) -> None:
    baseline_sigs = {_issue_signature(i) for i in baseline_issues or []}
    # 记录基线里每个签名的 text_overflow 溢出比：用于「溢出是否被替换文案加重」的判断。
    # 关键修复：模板某槽原文本能放下（或只轻微溢出），换成更长/更大字号的文案后严重溢出，
    # 二者 geom 相同会误命中基线降级（历史上让 200pt 的『****』靠模板『3亿』蒙混过关）。
    # 因此仅当成品溢出比未明显超过基线时才认定为模板原生问题，否则视为内容导致、照常阻断。
    baseline_ratio: dict[tuple, float] = {}
    for b in baseline_issues or []:
        if b.get('type') == 'text_overflow':
            sig = _issue_signature(b)
            baseline_ratio[sig] = max(baseline_ratio.get(sig, 0.0), b.get('overflow_ratio') or 0.0)
    geometry_types = {'overflow', 'overlap', 'text_overflow', 'text_collision'}
    for issue in issues:
        # 模板原生/组合内问题降级；任何非基线、非自动缩字且明确超框的文本都阻断。
        # 视觉上 1.2 倍已经会拆字、截断或挤到相邻卡片，不能再作为 warning 交付。
        if issue.get('type') == 'text_overflow':
            sig = _issue_signature(issue)
            ratio = issue.get('overflow_ratio') or 0
            # 仅当成品溢出比 ≤ 基线×1.1 才算模板原生；替换文案把溢出加重的不再豁免。
            is_baseline = sig in baseline_sigs and ratio <= baseline_ratio.get(sig, 0.0) * 1.1
            # 短标题/标签溢出比长正文更刺眼：阈值下调到 _OVERFLOW_HEADING；长正文沿用 _OVERFLOW_SEVERE。
            limit = _OVERFLOW_HEADING if issue.get('short_heading') else _OVERFLOW_SEVERE
            severe = ratio >= limit
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

            # 2.5) 文字溢出压住相邻文本框：文案过长使渲染下沿越出本框、侵入下方/相邻的另一个
            # 文本框（典型：封面标题换行后压住副标题）。原框本不重叠、靠"渲染溢出"造成压字，
            # 故 overlap 抓不到，这里用估算的渲染高度补captured。
            for a in text_shapes:
                if a.get('grouped') or a.get('norm_autofit'):
                    continue  # 组合/自动缩字不计
                r_a = _est_text_overflow(a)
                if r_a <= _OVERFLOW_WARN:
                    continue
                rendered_cy = int(a['cy'] * min(r_a, 4.0))
                expanded = {'x': a['x'], 'y': a['y'], 'cx': a['cx'], 'cy': rendered_cy}
                for b in text_shapes:
                    if b is a:
                        continue
                    area_b = b['cx'] * b['cy']
                    if area_b <= 0:
                        continue
                    # 原框已显著重叠 → 归 overlap，不在这里重复报
                    if _overlap_area(a, b) / min(a['cx'] * a['cy'] or 1, area_b) >= overlap_thresh:
                        continue
                    intrude = _overlap_area(expanded, b)
                    if intrude <= 0:
                        continue
                    if intrude / area_b >= 0.2:
                        issues.append({
                            'slide': slide_no, 'type': 'text_collision',
                            'shape': f"{a['name'] or a['kind']} → {b['name'] or b['kind']}",
                            'ref': a.get('ref'),
                            'grouped': False,
                            'geom': (a['x'], a['y'], a['cx'], a['cy']),
                            'detail': (f"文字过长溢出后压住相邻文本框（约需 {r_a:.1f} 倍框高，"
                                       f"侵入下方框 {intrude / area_b:.0%}）: {a['text'][:20]}…"),
                            'suggestion': '缩短该 ref 文案，或用 adjust_shape 放大文本框/设 normAutofit 让字自适应。',
                        })
                        break

            # 3) 文本疑似溢出
            for s in shapes:
                ratio = _est_text_overflow(s)
                if ratio > _OVERFLOW_WARN:
                    issues.append({
                        'slide': slide_no, 'type': 'text_overflow', 'shape': s['name'] or s['kind'],
                        'ref': s.get('ref'), 'grouped': s.get('grouped', False),
                        'norm_autofit': s.get('norm_autofit', False),
                        'overflow_ratio': round(ratio, 2),
                        # 短标题/标签塞不下（短文本却需远超 1 倍框高）比长正文更刺眼，单独标记便于升级。
                        'short_heading': len((s.get('text') or '').strip()) <= 20,
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
