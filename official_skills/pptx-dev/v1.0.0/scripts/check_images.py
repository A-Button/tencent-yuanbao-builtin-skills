#!/usr/bin/env python3
"""交付门：选中页里的"显著图位"必须换成主题图，不能留模板库存照片。

做法：把成品里每个 <p:pic> 的媒体字节做哈希，与**原模板**的媒体哈希集合比对。
若某图位的媒体仍命中模板原图、且该图位足够大（面积占比 ≥ 阈值），判定为
`untouched_template_image`（blocking）——提示模型用 image_generation 生成主题图后替换。

- 替换后的图经 replace_image 重压缩/旋转，哈希必然变化，不会被误判。
- 小图标/角标/装饰（面积占比 < 阈值）必须保留模板原资源；若被生成图替换，判
  `replaced_protected_small_visual`（blocking）。
- 仅看 pic 自身 spPr/xfrm/ext 的面积；组合内无绝对尺寸的 pic 跳过（多为装饰）。
- **给文字当背景/衬底的图默认禁止替换**：任一文本框≥半数自身面积被该图覆盖
  （逻辑与 `check_contrast.py` 判定"这张图是这个文本框的背景"完全一致），或
  该图占画布至少 50%（`_FULLBLEED_BG_FRAC`），都算"背景衬字位"。这类图通常经过
  设计师专门挑选/裁切以配合固定的文字压顶位置（文字区明暗均匀、对比度安全）；
  换成按主题重新生成的写实照片，画面内容不可控，容易在文字压顶处出现亮斑/暗角
  糊字（复盘实例：换图前后同一文字框对比度从 4.7 掉到 1.4），且为了保对比度不停
  重生成/改字色，是消耗模型轮次预算的头号来源。**若这类图位最终仍被换成了非模板
  图，判 `replaced_protected_backdrop`（blocking）**——不是"不强制"而是硬性不允许，
  必须换回模板原图。没有文字压在上面的独立视觉位（图文分栏的大图、卡片配图等）
  不受此豁免，仍必须换成主题图。

退出码：有 blocking 返回 2，否则 0。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    from chart_utils import slide_charts_zip
except ImportError:  # pragma: no cover
    slide_charts_zip = None

_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
# 微软 SVG 扩展命名空间：SVG 图标的 <a:blip> 本身常无 r:embed，真正的媒体引用挂在
# extLst 里的 <asvg:svgBlip r:embed="..."> 上。只看 <a:blip> 会把未改动的 SVG 图标误判
# 成“媒体解析不到 → 非模板图 → 被替换”，导致模板自带图标全被 replaced_protected_small_visual
# 阻断（复盘：整套模板对自己跑都爆一堆 blocking，把模型逼到删页/换模板空转）。
_ASVG = 'http://schemas.microsoft.com/office/drawing/2016/SVG/main'

# Logo 墙：同一页这么多张图都仍命中模板原图 → 判模板残留 Logo 墙
_LOGO_WALL_MIN = 3
# 配图覆盖度：选中页≥此数却零显著图位+零图表 → no_visual 提醒
_NO_VISUAL_MIN_PAGES = 6
# 大面积图片：达到半页即按背景/主视觉保护，不允许生成图替换。
_FULLBLEED_BG_FRAC = 0.50
# 文字衬底：文本框自身面积有此比例被图覆盖，就算该图是这个文本框的背景（与
# check_contrast.py 的 provider 判定阈值一致，保持两处"背景"定义统一）
_TEXT_OVERLAP_BG_FRAC = 0.50


def _template_media_hashes(template: str) -> set[str]:
    hashes: set[str] = set()
    try:
        with zipfile.ZipFile(template) as z:
            for n in z.namelist():
                if n.startswith('ppt/media/') and not n.endswith('/'):
                    hashes.add(hashlib.md5(z.read(n)).hexdigest())
    except (zipfile.BadZipFile, OSError, KeyError):
        pass
    return hashes


def _slide_size(z: zipfile.ZipFile) -> tuple[int, int]:
    try:
        raw = z.read('ppt/presentation.xml').decode('utf-8', 'ignore')
        m = re.search(r'<p:sldSz[^>]*cx="(\d+)"[^>]*cy="(\d+)"', raw)
        if m:
            return int(m.group(1)), int(m.group(2))
    except KeyError:
        pass
    return 0, 0


def _rels_map(z: zipfile.ZipFile, slide_name: str) -> dict[str, str]:
    base = posixpath.dirname(slide_name)
    rels = f'{base}/_rels/{posixpath.basename(slide_name)}.rels'
    out: dict[str, str] = {}
    try:
        raw = z.read(rels).decode('utf-8', 'ignore')
    except KeyError:
        return out
    for rid, tgt in re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', raw):
        out[rid] = posixpath.normpath(posixpath.join(base, tgt))
    return out


def _bounds(elem: ET.Element) -> tuple[int, int] | None:
    ext = elem.find(f'.//{{{_A}}}xfrm/{{{_A}}}ext')
    if ext is None:
        return None
    try:
        return int(ext.get('cx', '0')), int(ext.get('cy', '0'))
    except (TypeError, ValueError):
        return None


def _blip_embeds(elem: ET.Element) -> list[str]:
    """该视觉元素引用的所有媒体 embed：同时收集 <a:blip r:embed>（含 PNG 兜底）与
    扩展里的 <asvg:svgBlip r:embed>（SVG 本体）。SVG 图标的主 blip 常无 r:embed，
    只有 svgBlip 有——只看前者会把未改动的模板图标误判成非模板图。"""
    embeds: list[str] = []
    for blip in elem.iter(f'{{{_A}}}blip'):
        e = blip.get(f'{{{_R}}}embed')
        if e:
            embeds.append(e)
    for svg in elem.iter(f'{{{_ASVG}}}svgBlip'):
        e = svg.get(f'{{{_R}}}embed')
        if e:
            embeds.append(e)
    return embeds


def _blip_embed(elem: ET.Element) -> str | None:
    embeds = _blip_embeds(elem)
    return embeds[0] if embeds else None


def _overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    ax, ay, acx, acy = a
    bx, by, bcx, bcy = b
    ix = max(0, min(ax + acx, bx + bcx) - max(ax, bx))
    iy = max(0, min(ay + acy, by + bcy) - max(ay, by))
    return ix * iy


def _xy_bounds(elem: ET.Element) -> tuple[int, int, int, int] | None:
    """含位置的完整 bounds（x,y,cx,cy），供与文本框做重叠判定；_bounds() 只取 (cx,cy)。"""
    xfrm = elem.find(f'.//{{{_A}}}xfrm')
    if xfrm is None:
        return None
    off = xfrm.find(f'{{{_A}}}off')
    ext = xfrm.find(f'{{{_A}}}ext')
    if off is None or ext is None:
        return None
    try:
        return (int(off.get('x', '0')), int(off.get('y', '0')),
                int(ext.get('cx', '0')), int(ext.get('cy', '0')))
    except (TypeError, ValueError):
        return None


def _text_bounds_on_slide(root: ET.Element) -> list[tuple[int, int, int, int]]:
    """该页所有非空文本框的 (x,y,cx,cy)，用于判定图片是否在给文字当背景。"""
    out = []
    for sp in root.iter(f'{{{_P}}}sp'):
        tb = sp.find(f'{{{_P}}}txBody')
        if tb is None:
            continue
        text = ''.join(t.text or '' for t in tb.iter(f'{{{_A}}}t')).strip()
        if len(text) < 2:
            continue
        b = _xy_bounds(sp)
        if b:
            out.append(b)
    return out


def _is_text_backdrop(bounds_xy: tuple[int, int, int, int] | None,
                       text_boxes: list[tuple[int, int, int, int]]) -> bool:
    """任一文本框≥半数自身面积被这张图覆盖，就算这张图是文字的背景/衬底。"""
    if not bounds_xy:
        return False
    for tb in text_boxes:
        tarea = tb[2] * tb[3]
        if tarea <= 0:
            continue
        if _overlap(bounds_xy, tb) / tarea >= _TEXT_OVERLAP_BG_FRAC:
            return True
    return False


def _iter_visuals(root: ET.Element):
    visual_idx = 0
    for idx, pic in enumerate(root.iter(f'{{{_P}}}pic'), start=1):
        visual_idx += 1
        yield f'image{idx}', 'pic', _blip_embeds(pic), _bounds(pic), _xy_bounds(pic)
    for shape_idx, shape in enumerate(root.iter(f'{{{_P}}}sp'), start=1):
        sp_pr = shape.find(f'{{{_P}}}spPr')
        if sp_pr is None or sp_pr.find(f'{{{_A}}}blipFill') is None:
            continue
        visual_idx += 1
        yield f'visual{visual_idx}', 'shape_fill', _blip_embeds(sp_pr), _bounds(shape), _xy_bounds(shape)


def check(final_pptx: str, template: str, min_area_frac: float) -> dict:
    issues: list[dict] = []
    tpl_hashes = _template_media_hashes(template)
    try:
        z = zipfile.ZipFile(final_pptx)
    except (zipfile.BadZipFile, OSError) as e:
        return {'blocking_count': 0, 'issues': [], 'note': f'无法读取 {final_pptx}: {e}'}

    sx, sy = _slide_size(z)
    slide_area = sx * sy
    name_set = set(z.namelist())
    significant = 0
    chart_total = 0
    slide_names = sorted(
        (n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)),
        key=lambda n: int(re.findall(r'\d+', n)[0]),
    )
    for name in slide_names:
        raw = z.read(name).decode('utf-8', 'ignore')
        try:
            root = ET.fromstring(raw)
        except ET.ParseError:
            continue
        rmap = _rels_map(z, name)
        sn = int(re.findall(r'\d+', name)[0])
        text_boxes = _text_bounds_on_slide(root)
        tpl_pics_on_slide = 0  # 该页仍命中模板原图的显著视觉槽数 → Logo 墙判定
        for ref_suffix, slot_type, embeds, bounds, bounds_xy in _iter_visuals(root):
            # 该视觉槽只要有任一引用的媒体（PNG 兜底或 SVG 本体）命中模板原图，就算未被替换。
            # 用 any 而非单一 blip，避免 SVG 图标（主 blip 无 embed）被误判为“非模板图”。
            # has_media：是否真解析到了媒体字节。空 blip（如装饰分隔线 <a:blip/> 无 embed）
            # 或 embed 解析不到媒体时，无从证明“被换成非模板图”，一律不判 replaced，避免
            # 把模板自带的无图装饰位误判为违规替换（复盘：这类空 blip 会整页误报 blocking）。
            is_tpl = False
            has_media = False
            media = None
            for e in embeds:
                m = rmap.get(e)
                if not m or m not in name_set:
                    continue
                has_media = True
                media = media or m
                try:
                    if hashlib.md5(z.read(m)).hexdigest() in tpl_hashes:
                        is_tpl = True
                        break
                except KeyError:
                    continue

            if not bounds:
                continue
            area = bounds[0] * bounds[1]
            if not slide_area:
                continue
            area_frac = area / slide_area
            # 小于显著图位阈值的资源按 icon/装饰占位保护。过去这里直接 continue，
            # 导致模型可以把 0.1%~5% 的小图标换成写实生成图而质检完全看不到。
            if area_frac < min_area_frac:
                if has_media and not is_tpl:
                    issues.append({
                        'severity': 'blocking', 'type': 'replaced_protected_small_visual',
                        'ref': f'slide{sn}:{ref_suffix}',
                        'detail': f'第 {sn} 页 {slot_type} 视觉槽仅占版面 {area_frac:.1%}（<'
                                  f'{min_area_frac:.0%}），属于图标/装饰保护位，却被换成了非模板图片。'
                                  '小视觉槽禁止用生成图片替换；请用 replace_image.py restore 撤回。',
                    })
                continue
            significant += 1
            is_fullbleed = area_frac >= _FULLBLEED_BG_FRAC
            is_backdrop = is_fullbleed or _is_text_backdrop(bounds_xy, text_boxes)
            if is_backdrop:
                if has_media and not is_tpl:
                    # 背景/衬字位被换成了非模板图：这类位置模板已配合固定文字位精选过明暗，
                    # 换成按主题重新生成的写实照片内容不可控，是文字压顶处糊字的头号来源
                    # （复盘：换图后同一文字框对比度从 4.7 掉到 1.4）。默认硬性禁止替换，
                    # 不接受"这次生成的图应该还行"式的例外——保留模板原图。
                    issues.append({
                        'severity': 'blocking', 'type': 'replaced_protected_backdrop',
                        'ref': f'slide{sn}:{ref_suffix}',
                        'detail': f'第 {sn} 页 {slot_type} 视觉槽是给文字当背景/满版背景'
                                  f'（占版面 {area_frac:.0%}），被换成了非模板图片。这类背景位'
                                  '默认不允许替换（模板已配合固定文字位精选好明暗对比，换生成图易导致'
                                  '文字压顶处糊字/不可读）；一键撤回，不要去猜/手动找模板原图文件：'
                                  f'先 `python replace_image.py list <unpacked> --slide {sn}` 找到 '
                                  f'{ref_suffix} 对应的 visual# 编号，再 `python replace_image.py restore '
                                  f'<unpacked> --slide {sn} --visual-index <该编号>`（也不要为这个报错去读'
                                  'check_images.py/replace_image.py 源码）。',
                    })
                continue  # 无论是否被换：背景/衬字位不计入"必须换主题图"统计，可读性交给 check_contrast
            if is_tpl:
                tpl_pics_on_slide += 1
                issues.append({
                    'severity': 'blocking', 'type': 'untouched_template_image',
                    'ref': f'slide{sn}:{ref_suffix}',
                        'detail': f'第 {sn} 页 {slot_type} 视觉槽仍是模板原图（占版面 {area_frac:.0%}）；'
                              '用 image_generation 生成贴合主题的图后替换该视觉槽。',
                })

        # Logo 墙：同页多张图都仍是模板原图（多见于"客户/合作伙伴"通用 Logo 页）
        if tpl_pics_on_slide >= _LOGO_WALL_MIN:
            issues.append({
                'severity': 'blocking', 'type': 'template_logo_wall',
                'ref': f'slide{sn}',
                'detail': f'第 {sn} 页有 {tpl_pics_on_slide} 张图仍是模板原图（疑似模板自带 Logo 墙/通用图标）；'
                          '与主题无关，应删除该页或把这些图换成贴合主题的图/数据可视化。',
            })

        if slide_charts_zip is not None:
            chart_total += len(slide_charts_zip(z, sn))

    z.close()
    # 配图覆盖度：稍大的副本却零显著图位、零图表 → 给 no_visual 提醒（不阻断）
    page_count = len(slide_names)
    if page_count >= _NO_VISUAL_MIN_PAGES and significant == 0 and chart_total == 0:
        issues.append({
            'severity': 'warning', 'type': 'no_visual',
            'detail': f'全副 {page_count} 页无任何显著配图或图表；建议挑一个图文/图表版式，'
                      '为关键页补 1~2 张主题配图或一张数据图表，避免纯文字。',
        })
    blocking = sum(1 for i in issues if i['severity'] == 'blocking')
    warning = sum(1 for i in issues if i['severity'] == 'warning')
    return {'blocking_count': blocking, 'warning_count': warning,
            'significant_pics': significant, 'significant_visuals': significant, 'chart_count': chart_total,
            'issue_count': len(issues), 'issues': issues}


def main() -> int:
    ap = argparse.ArgumentParser(description='Check selected-deck significant image slots were replaced.')
    ap.add_argument('final_pptx')
    ap.add_argument('--template', required=True, help='原模板 .pptx（用于媒体哈希基线）')
    ap.add_argument('--min-area-frac', type=float, default=0.02,
                    help='判定"显著图位"的最小面积占比（默认 0.02=2%%）')
    ap.add_argument('--report', help='把 JSON 报告写到该路径')
    args = ap.parse_args()

    report = check(args.final_pptx, args.template, args.min_area_frac)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding='utf-8')
    print(text)
    return 2 if report['blocking_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
