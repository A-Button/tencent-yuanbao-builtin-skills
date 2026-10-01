#!/usr/bin/env python3
"""交付门（可读性）：正文/标题文字与其背景的对比度不能过低。

复盘里"浅底白字/蓝底蓝字/黑底黑字"是头号可读性杀手，而 replace_text 沿用模板字色、
check_layout 只看几何，没有任何对比度校验。本门按 WCAG 相对亮度算文字↔背景对比度，
低于阈值（正文 4.5、大字 3.0）判 `low_contrast`(blocking)。

保守取舍（避免误报）：仅当**字色与背景都能确定地解析出来**时才比对——
- 字色：run rPr / 段落 defRPr / 形状 lstStyle / 占位符(版式·母版) / 主题，逐级解析；解析不到则跳过。
- 背景：文本框下方**最近的**实色填充形状或满版/重叠图片或页面背景色；
  图片背景用 PIL 把文字区域切成小网格分别采样，取对该字色**最不利的子区域**参与判定
  （生成图常见亮窗/暗角等强局部反差，整框平均色会把局部低对比"平均"掉，导致明显糊字的情况漏判）；
  渐变/图案/解析不到则跳过该形状（不阻断）。

模型修法：用 image_generation 重生成更合适明度的背景图，或用 adjust_shape 的 fontColor 改字色。
退出码：有 blocking 返回 2，否则 0。
"""

from __future__ import annotations

import argparse
import io
import json
import math
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'

_SCHEME_FALLBACK = {  # clrMap 名 → theme clrScheme 名
    'tx1': 'dk1', 'tx2': 'dk2', 'bg1': 'lt1', 'bg2': 'lt2',
}

# 对比度阈值：大字(≥24pt 或加粗≥19pt)=3.0，正文=4.5
_LARGE_PT = 24.0
_LARGE_BOLD_PT = 19.0
_THRESH_LARGE = 3.0
_THRESH_NORMAL = 4.5
# 留出余量减少误报：仅当明显低于阈值才阻断
_MARGIN = 0.92
# 图片背景采样网格：切块太粗会漏掉局部亮/暗斑，太细则接近逐像素、易被噪点带偏；
# 4x3 对典型文字框（长条形）能较好覆盖左右与上下的明暗跳变。
_IMG_GRID = (4, 3)


def _q(tag: str, ns: str = _A) -> str:
    return f'{{{ns}}}{tag}'


def _hex_to_rgb(h: str):
    h = (h or '').strip().lstrip('#')
    if len(h) != 6:
        return None
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    except ValueError:
        return None


def _apply_mods(rgb, el: ET.Element):
    """应用 lumMod/lumOff/shade/tint（近似），返回新 rgb。"""
    if rgb is None:
        return None
    r, g, b = rgb
    def child_val(tag):
        c = el.find(_q(tag))
        if c is not None:
            try:
                return int(c.get('val', '0')) / 100000.0
            except ValueError:
                return None
        return None
    lummod = child_val('lumMod')
    lumoff = child_val('lumOff')
    shade = child_val('shade')
    tint = child_val('tint')
    # 用 HSL 的 L 近似处理 lumMod/lumOff
    if lummod is not None or lumoff is not None:
        import colorsys
        hh, ll, ss = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
        if lummod is not None:
            ll *= lummod
        if lumoff is not None:
            ll = min(1.0, ll + lumoff)
        r, g, b = (int(c * 255) for c in colorsys.hls_to_rgb(hh, ll, ss))
    if shade is not None:
        r, g, b = (int(c * shade) for c in (r, g, b))
    if tint is not None:
        r, g, b = (int(c + (255 - c) * (1 - tint)) for c in (r, g, b))
    return (max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b)))


class ThemeMap:
    def __init__(self, scheme: dict[str, tuple], clrmap: dict[str, str]):
        self.scheme = scheme  # dk1.. → rgb
        self.clrmap = clrmap  # tx1 → dk1 等

    def resolve_scheme(self, name: str):
        nm = self.clrmap.get(name, name)
        nm = _SCHEME_FALLBACK.get(nm, nm)
        return self.scheme.get(nm)


def _parse_theme(theme_xml: bytes) -> dict[str, tuple]:
    out: dict[str, tuple] = {}
    try:
        root = ET.fromstring(theme_xml)
    except ET.ParseError:
        return out
    scheme = root.find(f'.//{_q("clrScheme")}')
    if scheme is None:
        return out
    for child in scheme:
        name = child.tag.split('}')[-1]
        srgb = child.find(_q('srgbClr'))
        sysc = child.find(_q('sysClr'))
        if srgb is not None:
            out[name] = _hex_to_rgb(srgb.get('val', '')) or (0, 0, 0)
        elif sysc is not None:
            out[name] = _hex_to_rgb(sysc.get('lastClr', '')) or (0, 0, 0)
    return out


def _color_from_fill(fill_parent: ET.Element | None, theme: ThemeMap):
    """从 solidFill 元素解析 rgb；非实色返回 None。"""
    if fill_parent is None:
        return None
    solid = fill_parent.find(_q('solidFill'))
    if solid is None:
        return None
    srgb = solid.find(_q('srgbClr'))
    if srgb is not None:
        return _apply_mods(_hex_to_rgb(srgb.get('val', '')), srgb)
    sch = solid.find(_q('schemeClr'))
    if sch is not None:
        base = theme.resolve_scheme(sch.get('val', ''))
        return _apply_mods(base, sch)
    sysc = solid.find(_q('sysClr'))
    if sysc is not None:
        return _hex_to_rgb(sysc.get('lastClr', ''))
    return None


def _rel_luminance(rgb) -> float:
    def chan(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = rgb
    return 0.2126 * chan(r) + 0.7152 * chan(g) + 0.0722 * chan(b)


def _contrast(a, b) -> float:
    la, lb = _rel_luminance(a), _rel_luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _bounds(shape: ET.Element):
    xfrm = shape.find(f'.//{_q("xfrm")}')
    if xfrm is None:
        return None
    off = xfrm.find(_q('off'))
    ext = xfrm.find(_q('ext'))
    if off is None or ext is None:
        return None
    try:
        return (int(off.get('x', '0')), int(off.get('y', '0')),
                int(ext.get('cx', '0')), int(ext.get('cy', '0')))
    except ValueError:
        return None


def _overlap(a, b) -> int:
    ax, ay, acx, acy = a
    bx, by, bcx, bcy = b
    ix = max(0, min(ax + acx, bx + bcx) - max(ax, bx))
    iy = max(0, min(ay + acy, by + bcy) - max(ay, by))
    return ix * iy


def _rels_map(z: zipfile.ZipFile, slide_name: str) -> dict[str, str]:
    base = posixpath.dirname(slide_name)
    rels = f'{base}/_rels/{posixpath.basename(slide_name)}.rels'
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(z.read(rels))
    except (KeyError, ET.ParseError):
        return out
    for rel in root.iter(f'{{{_REL}}}Relationship'):
        out[rel.get('Id', '')] = posixpath.normpath(posixpath.join(base, rel.get('Target', '')))
    return out


def _image_region_samples(z, media_part, rel_rect, grid: tuple[int, int] = _IMG_GRID):
    """采样图片在 rel_rect=(fx,fy,fw,fh)(0~1) 区域内的网格子块平均 rgb 列表。

    不用整框单一平均色：生成图常有强局部反差（一块亮窗+大片暗景同框），
    整框平均会把局部低对比"抹平"，导致文字明显糊在亮/暗斑上却测不出来。
    返回多个子块颜色，调用方对每个 run 取"最不利子块"的对比度。失败返回 []。
    """
    if Image is None:
        return []
    try:
        data = z.read(media_part)
    except KeyError:
        return []
    try:
        im = Image.open(io.BytesIO(data)).convert('RGB')
    except Exception:
        return []
    w, h = im.size
    fx, fy, fw, fh = rel_rect
    l = max(0, int(fx * w)); t = max(0, int(fy * h))
    r = min(w, int((fx + fw) * w)); b = min(h, int((fy + fh) * h))
    if r <= l or b <= t:
        l, t, r, b = 0, 0, w, h
    crop = im.crop((l, t, r, b))
    if crop.width <= 0 or crop.height <= 0:
        return []
    gw, gh = grid
    cw, ch = crop.size
    samples: list[tuple[int, int, int]] = []
    for gy in range(gh):
        y0, y1 = gy * ch // gh, (gy + 1) * ch // gh
        if y1 <= y0:
            continue
        for gx in range(gw):
            x0, x1 = gx * cw // gw, (gx + 1) * cw // gw
            if x1 <= x0:
                continue
            # 缩到 1x1 即得该子块平均色，避免逐像素遍历与已弃用的 getdata。
            avg = crop.crop((x0, y0, x1, y1)).resize((1, 1)).getpixel((0, 0))
            if isinstance(avg, (int, float)):
                avg = (int(avg), int(avg), int(avg))
            samples.append((int(avg[0]), int(avg[1]), int(avg[2])))
    return samples


def _slide_size(z):
    try:
        raw = z.read('ppt/presentation.xml').decode('utf-8', 'ignore')
        m = re.search(r'<p:sldSz[^>]*cx="(\d+)"[^>]*cy="(\d+)"', raw)
        if m:
            return int(m.group(1)), int(m.group(2))
    except KeyError:
        pass
    return 0, 0


def _layout_master_for_slide(z, slide_name):
    """返回 (layout_part, master_part)。"""
    rmap = _rels_map(z, slide_name)
    layout = next((t for t in rmap.values() if '/slideLayouts/' in t), None)
    master = None
    if layout:
        lmap = _rels_map(z, layout)
        master = next((t for t in lmap.values() if '/slideMasters/' in t), None)
    return layout, master


def _theme_for_master(z, master_part):
    if not master_part:
        return {}
    mmap = _rels_map(z, master_part)
    theme = next((t for t in mmap.values() if '/theme/' in t), None)
    if theme:
        try:
            return _parse_theme(z.read(theme))
        except KeyError:
            return {}
    return {}


def _clrmap_from_master(z, master_part) -> dict[str, str]:
    if not master_part:
        return {}
    try:
        root = ET.fromstring(z.read(master_part))
    except (KeyError, ET.ParseError):
        return {}
    cm = root.find(_q('clrMap', _P))
    if cm is None:
        return {}
    return {k: v for k, v in cm.attrib.items()}


def _page_bg_color(z, slide_name, layout_part, master_part, theme: ThemeMap):
    """页面背景实色：slide bg → layout bg → master bg；非实色返回 None。"""
    for part in (slide_name, layout_part, master_part):
        if not part:
            continue
        try:
            root = ET.fromstring(z.read(part))
        except (KeyError, ET.ParseError):
            continue
        bg = root.find(f'.//{_q("bg", _P)}')
        if bg is None:
            continue
        bgpr = bg.find(_q('bgPr', _P))
        if bgpr is not None:
            c = _color_from_fill(bgpr, theme)
            if c:
                return c
        bgref = bg.find(_q('bgRef', _P))
        if bgref is not None:
            sch = bgref.find(_q('schemeClr'))
            if sch is not None:
                c = _apply_mods(theme.resolve_scheme(sch.get('val', '')), sch)
                if c:
                    return c
    return None


def _run_color(run: ET.Element, para: ET.Element, shape: ET.Element, theme: ThemeMap):
    """逐级解析 run 字色：run rPr → 段落 defRPr → 形状 lstStyle lvl1 defRPr。解析不到返回 None。"""
    rpr = run.find(_q('rPr'))
    c = _color_from_fill(rpr, theme)
    if c:
        return c
    ppr = para.find(_q('pPr'))
    if ppr is not None:
        c = _color_from_fill(ppr.find(_q('defRPr')), theme)
        if c:
            return c
    tx = shape.find(_q('txBody', _P))
    if tx is not None:
        lst = tx.find(_q('lstStyle'))
        if lst is not None:
            for lvl in ('lvl1pPr', 'lvl2pPr'):
                p = lst.find(_q(lvl))
                if p is not None:
                    c = _color_from_fill(p.find(_q('defRPr')), theme)
                    if c:
                        return c
    return None


def _font_pt(run: ET.Element, para: ET.Element) -> tuple[float, bool]:
    rpr = run.find(_q('rPr'))
    sz = None
    bold = False
    if rpr is not None:
        if rpr.get('sz'):
            try:
                sz = int(rpr.get('sz')) / 100.0
            except ValueError:
                pass
        bold = rpr.get('b') == '1'
    if sz is None:
        ppr = para.find(_q('pPr'))
        dpr = ppr.find(_q('defRPr')) if ppr is not None else None
        if dpr is not None and dpr.get('sz'):
            try:
                sz = int(dpr.get('sz')) / 100.0
            except ValueError:
                pass
    return (sz or 18.0, bold)


def check(final_pptx: str) -> dict:
    issues: list[dict] = []
    try:
        z = zipfile.ZipFile(final_pptx)
    except (zipfile.BadZipFile, OSError) as e:
        return {'blocking_count': 0, 'issues': [], 'note': f'无法读取: {e}'}

    sx, sy = _slide_size(z)
    slide_area = sx * sy
    checked = 0
    slide_names = sorted(
        (n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)),
        key=lambda n: int(re.findall(r'\d+', n)[0]),
    )
    for name in slide_names:
        sn = int(re.findall(r'\d+', name)[0])
        try:
            root = ET.fromstring(z.read(name))
        except ET.ParseError:
            continue
        layout, master = _layout_master_for_slide(z, name)
        theme = ThemeMap(_theme_for_master(z, master), _clrmap_from_master(z, master))
        page_bg = _page_bg_color(z, name, layout, master, theme)
        rmap = _rels_map(z, name)

        sptree = root.find(f'.//{_q("spTree", _P)}')
        if sptree is None:
            continue
        children = list(sptree)

        # ref 编号必须与 inspect_deck.py / verify_content.py / check_layout.py /
        # adjust_shape.py 完全一致：只数 <p:sp>，按 root.iter 的文档序（含组内嵌套）
        # 从 1 编号——绝不能按 spTree 直接子节点的位置编号（那会把 nvGrpSpPr/grpSpPr
        # 两个必有的头部元素、以及穿插的 pic/graphicFrame/cxnSp/grpSp 也计入偏移，
        # 导致这里报出的 ref 与模型用 adjust_shape 改的 shape 对不上号，永远修不好）。
        sp_ref_index = {id(sp): idx for idx, sp in enumerate(root.iter(_q('sp', _P)), start=1)}

        # 收集填充提供者（按文档序，later=在上层）：实色形状 / 图片
        providers: list[dict] = []
        for i, el in enumerate(children):
            tag = el.tag.split('}')[-1]
            b = _bounds(el)
            if b is None:
                continue
            if tag == 'sp':
                sppr = el.find(_q('spPr', _P))
                col = _color_from_fill(sppr, theme)
                if col:
                    providers.append({'order': i, 'bounds': b, 'kind': 'solid', 'color': col})
            elif tag == 'pic':
                blip = el.find(f'.//{_q("blip")}')
                embed = blip.get(f'{{{_R}}}embed') if blip is not None else None
                media = rmap.get(embed) if embed else None
                if media:
                    providers.append({'order': i, 'bounds': b, 'kind': 'image', 'media': media})

        # 逐文本框逐 run 评估
        for i, el in enumerate(children):
            if el.tag.split('}')[-1] != 'sp':
                continue
            tb = el.find(_q('txBody', _P))
            if tb is None:
                continue
            tbounds = _bounds(el)
            if tbounds is None:
                continue
            # 该文本框文字（合并）
            full = ''.join(t.text or '' for t in el.iter(_q('t'))).strip()
            if len(full) < 2:
                continue

            # 背景：找文档序在该文本框之前、与之重叠且面积最大覆盖的最上层 provider
            bg_candidates: list[tuple[int, int, int]] = []
            best = None
            tarea = tbounds[2] * tbounds[3]
            for p in providers:
                if p['order'] >= i:
                    continue
                ov = _overlap(p['bounds'], tbounds)
                if ov <= 0 or not tarea:
                    continue
                if ov / tarea < 0.5:  # 覆盖文本框过半才算其背景
                    continue
                if best is None or p['order'] > best['order']:
                    best = p
            if best is not None:
                if best['kind'] == 'solid':
                    bg_candidates = [best['color']]
                elif best['kind'] == 'image' and slide_area:
                    bx, by, bcx, bcy = best['bounds']
                    if bcx > 0 and bcy > 0:
                        rel = ((tbounds[0] - bx) / bcx, (tbounds[1] - by) / bcy,
                               tbounds[2] / bcx, tbounds[3] / bcy)
                        rel = (max(0.0, min(1.0, rel[0])), max(0.0, min(1.0, rel[1])),
                               max(0.05, min(1.0, rel[2])), max(0.05, min(1.0, rel[3])))
                        bg_candidates = _image_region_samples(z, best['media'], rel)
            if not bg_candidates:
                if page_bg is None:
                    continue  # 背景不确定 → 跳过，不阻断
                bg_candidates = [page_bg]

            # 文字色：取首个能解析出颜色的 run
            worst = None
            for para in el.iter(_q('p')):
                for run in para.findall(_q('r')):
                    txt = ''.join(t.text or '' for t in run.findall(_q('t')))
                    if not txt.strip():
                        continue
                    col = _run_color(run, para, el, theme)
                    if col is None:
                        continue
                    pt, bold = _font_pt(run, para)
                    # 多个背景候选（图片按网格切块）时取对该字色最不利（对比度最低）的子块，
                    # 而不是所有子块的平均——避免局部亮/暗斑被"平均"掉。
                    ratio, worst_bg = min(
                        ((_contrast(col, c), c) for c in bg_candidates),
                        key=lambda t: t[0],
                    )
                    thresh = _THRESH_LARGE if (pt >= _LARGE_PT or (bold and pt >= _LARGE_BOLD_PT)) else _THRESH_NORMAL
                    if ratio < thresh * _MARGIN:
                        if worst is None or ratio < worst['ratio']:
                            worst = {'ratio': ratio, 'fg': col, 'thresh': thresh, 'pt': pt, 'bg': worst_bg}
                    checked += 1
            if worst is not None:
                fg_hex = '%02X%02X%02X' % worst['fg']
                bg_hex = '%02X%02X%02X' % worst['bg']
                shape_num = sp_ref_index.get(id(el))
                if shape_num is None:
                    continue  # 理论上不会发生（el 本身就来自这颗树的 sp 遍历）
                issues.append({
                    'slide': sn, 'type': 'low_contrast',
                    'ref': f'slide{sn}:shape{shape_num}',
                    'geom': tbounds, 'fg': fg_hex, 'bg': bg_hex,
                    'detail': (f'第 {sn} 页文字与背景对比度仅 {worst["ratio"]:.1f}（需≥{worst["thresh"]:.0f}）：'
                               f'字色#{fg_hex} vs 背景#{bg_hex}，'
                               f'文字“{full[:16]}”。改字色(adjust_shape fontColor)或换更合适明度的背景图。'),
                })
    z.close()
    return {'runs_checked': checked, 'issues': issues}


def _sig(issue: dict) -> tuple:
    # 不含页号（复制/重排后页号会变），用几何+字色+背景色作签名匹配模板基线。
    # 背景色必须入签：满版图/背景色一旦被换成新图（哪怕字色沿用了模板默认值未改），
    # 就是一次全新的"字色×背景"组合，模板设计者从没验证过它可读——不能因为字色
    # 恰好没变、且这个字色在模板原图上也曾经对比度不够，就把"新背景撞上旧字色"的
    # 新问题误判成"模板自带的设计选择"而放过。
    return (issue.get('geom'), issue.get('fg'), issue.get('bg'))


def check_with_baseline(final_pptx: str, baseline_template: str | None = None) -> dict:
    raw = check(final_pptx)
    issues = raw['issues']
    baseline_sigs: set = set()
    if baseline_template:
        try:
            baseline_sigs = {_sig(i) for i in check(baseline_template)['issues']}
        except Exception:  # noqa: BLE001
            baseline_sigs = set()
    for issue in issues:
        is_baseline = _sig(issue) in baseline_sigs
        # 模板原生的低对比（装饰/水印文字）是设计选择 → 降级 warning；
        # 仅成品里**新出现**的低对比（多为背景图换明度后压住模板字色）才阻断。
        issue['severity'] = 'warning' if is_baseline else 'blocking'
        issue['baseline'] = is_baseline
    blocking = sum(1 for i in issues if i.get('severity') == 'blocking')
    warning = sum(1 for i in issues if i.get('severity') == 'warning')
    return {'blocking_count': blocking, 'warning_count': warning,
            'runs_checked': raw['runs_checked'], 'issue_count': len(issues), 'issues': issues}


def main() -> int:
    ap = argparse.ArgumentParser(description='Check text/background contrast (WCAG).')
    ap.add_argument('pptx')
    ap.add_argument('--baseline-template', help='原模板 pptx；模板原生低对比降级为 warning')
    ap.add_argument('--report', help='把 JSON 报告写到该路径')
    args = ap.parse_args()
    report = check_with_baseline(args.pptx, args.baseline_template)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding='utf-8')
    print(text)
    return 2 if report['blocking_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
