#!/usr/bin/env python3
"""图表（DrawingML chart）读取/改写的共享逻辑（单一事实来源）。

inspect_deck.py / edit_chart.py / check_charts.py 都从这里导入：
- 把 slideN 上的图表定位到 `slideN:chartK`（按 graphicFrame 文档序）与其 chart part；
- 读取图表当前的类目/系列/数值（模板示例数据）；
- 按计划改写图表缓存数据（`c:cat`/`c:val`/`c:tx`），用**定向字符串替换**而非整树重序列化，
  以免破坏 chart XML 里复杂的命名空间（c14/c15/c16/mc 等）导致 PowerPoint 报修复。

设计原则：图表"显示用"的是缓存（strLit/numLit 或 strRef>strCache / numRef>numCache）。
PowerPoint 打开时按缓存渲染，只有用户手动"编辑数据"才会回读内嵌工作簿。因此本地化数据
只需改缓存即可正确显示，无需改内嵌 xlsx。
"""

from __future__ import annotations

import posixpath
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_C = 'http://schemas.openxmlformats.org/drawingml/2006/chart'
_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'

_CHART_TYPES = (
    'barChart', 'bar3DChart', 'lineChart', 'line3DChart', 'pieChart', 'pie3DChart',
    'doughnutChart', 'areaChart', 'area3DChart', 'radarChart', 'scatterChart',
    'bubbleChart', 'ofPieChart', 'stockChart', 'surfaceChart',
)


def _esc(s: str) -> str:
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


# ---------------------------------------------------------------------------
# 定位：slideN -> [(ref, chart_part)]
# ---------------------------------------------------------------------------

def _rels_targets(rels_bytes: bytes, base_dir: str) -> dict[str, str]:
    """rId -> 规范化后的 part 路径（仅图表关系）。"""
    out: dict[str, str] = {}
    try:
        root = ET.fromstring(rels_bytes)
    except ET.ParseError:
        return out
    for rel in root.iter(f'{{{_REL}}}Relationship'):
        rid = rel.get('Id', '')
        tgt = rel.get('Target', '')
        typ = rel.get('Type', '')
        mode = rel.get('TargetMode', '')
        if not rid or not tgt or mode == 'External':
            continue
        if not typ.endswith('/chart'):
            continue
        out[rid] = posixpath.normpath(posixpath.join(base_dir, tgt))
    return out


def _chart_rids_in_order(slide_bytes: bytes) -> list[str]:
    """按文档序返回 slide 上图表引用的 r:id（graphicFrame 内 <c:chart r:id=...>）。"""
    rids: list[str] = []
    try:
        root = ET.fromstring(slide_bytes)
    except ET.ParseError:
        return rids
    for el in root.iter(f'{{{_C}}}chart'):
        rid = el.get(f'{{{_R}}}id')
        if rid:
            rids.append(rid)
    return rids


def _resolve_chart_parts(slide_bytes: bytes, rels_bytes: bytes, slide_dir: str,
                         slide_no: int) -> list[tuple[str, str]]:
    targets = _rels_targets(rels_bytes, slide_dir)
    out: list[tuple[str, str]] = []
    k = 0
    for rid in _chart_rids_in_order(slide_bytes):
        part = targets.get(rid)
        if not part:
            continue
        k += 1
        out.append((f'slide{slide_no}:chart{k}', part))
    return out


def slide_charts_unpacked(unpacked: Path, slide_no: int) -> list[tuple[str, Path]]:
    slide = unpacked / 'ppt' / 'slides' / f'slide{slide_no}.xml'
    rels = unpacked / 'ppt' / 'slides' / '_rels' / f'slide{slide_no}.xml.rels'
    if not slide.exists():
        return []
    rels_bytes = rels.read_bytes() if rels.exists() else b''
    parts = _resolve_chart_parts(slide.read_bytes(), rels_bytes, 'ppt/slides', slide_no)
    return [(ref, unpacked / part) for ref, part in parts]


def slide_charts_zip(z: zipfile.ZipFile, slide_no: int) -> list[tuple[str, str]]:
    slide_name = f'ppt/slides/slide{slide_no}.xml'
    rels_name = f'ppt/slides/_rels/slide{slide_no}.xml.rels'
    try:
        slide_bytes = z.read(slide_name)
    except KeyError:
        return []
    try:
        rels_bytes = z.read(rels_name)
    except KeyError:
        rels_bytes = b''
    return _resolve_chart_parts(slide_bytes, rels_bytes, 'ppt/slides', slide_no)


# ---------------------------------------------------------------------------
# 读取图表数据
# ---------------------------------------------------------------------------

def _first_block(xml: str, tag: str) -> str | None:
    m = re.search(rf'<{tag}\b[^>]*>(.*?)</{tag}>', xml, re.S)
    if m:
        return m.group(1)
    return None


def _cache_values(block: str | None) -> list[str]:
    if not block:
        return []
    # 取 <c:pt idx=..><c:v>..</c:v></c:pt> 里的 c:v，按 idx 排序（容忍缺序）
    pairs: list[tuple[int, str]] = []
    for m in re.finditer(r'<c:pt\b[^>]*\bidx="(\d+)"[^>]*>\s*<c:v>(.*?)</c:v>', block, re.S):
        pairs.append((int(m.group(1)), m.group(2)))
    pairs.sort(key=lambda p: p[0])
    return [v for _, v in pairs]


def _series_name(ser: str) -> str:
    tx = _first_block(ser, 'c:tx')
    if not tx:
        return ''
    vals = re.findall(r'<c:v>(.*?)</c:v>', tx, re.S)
    return vals[-1].strip() if vals else ''


def read_chart_data(xml: str) -> dict:
    """解析 chart XML 文本，返回 {type, categories, series:[{name, values}]}。"""
    ctype = ''
    for t in _CHART_TYPES:
        if re.search(rf'<c:{t}\b', xml):
            ctype = t
            break
    categories: list[str] = []
    series: list[dict] = []
    for sm in re.finditer(r'<c:ser\b.*?</c:ser>', xml, re.S):
        ser = sm.group(0)
        cat_vals = _cache_values(_first_block(ser, 'c:cat'))
        val_vals = _cache_values(_first_block(ser, 'c:val'))
        if not categories and cat_vals:
            categories = cat_vals
        series.append({'name': _series_name(ser), 'values': val_vals})
    return {'type': ctype, 'categories': categories, 'series': series}


def chart_signature(data: dict) -> str:
    """图表数据的归一化签名：类目+系列名+数值（去空白）。用于与模板基线比对。"""
    def n(x) -> str:
        return re.sub(r'\s+', '', str(x))
    cats = '|'.join(n(c) for c in data.get('categories', []))
    sers = ';'.join(
        n(s.get('name', '')) + '=' + ','.join(n(v) for v in s.get('values', []))
        for s in data.get('series', [])
    )
    return f'{cats}#{sers}'


# ---------------------------------------------------------------------------
# 改写图表数据
# ---------------------------------------------------------------------------

def _set_points(block: str, values: list) -> str:
    """把某个 c:cat / c:val 内层 block 的 ptCount 与 c:pt 列表替换为 values。"""
    new_pts = ''.join(
        f'<c:pt idx="{i}"><c:v>{_esc(str(v))}</c:v></c:pt>' for i, v in enumerate(values)
    )
    # 更新 ptCount（仅首个）
    block = re.sub(r'<c:ptCount val="\d+"/>', f'<c:ptCount val="{len(values)}"/>', block, count=1)
    # 删掉旧 pt
    block = re.sub(r'<c:pt\b.*?</c:pt>', '', block, flags=re.S)
    # 在 ptCount 后插入新 pt
    if re.search(r'<c:ptCount val="\d+"/>', block):
        block = re.sub(r'(<c:ptCount val="\d+"/>)', lambda m: m.group(1) + new_pts, block, count=1)
    return block


def _set_named_block(ser: str, tag: str, values: list) -> str:
    def repl(m: re.Match) -> str:
        return m.group(1) + _set_points(m.group(2), values) + m.group(3)
    return re.sub(rf'(<{tag}\b[^>]*>)(.*?)(</{tag}>)', repl, ser, count=1, flags=re.S)


def _set_series_name(ser: str, name: str) -> str:
    """改写系列名（图例/系列标签）。

    常见结构：<c:tx><c:strRef>…<c:strCache><c:ptCount/><c:pt><c:v>名</c:v></c:pt>
    柱状图模板常只有 ptCount、无 pt（图例显示 Series1）；此时须在 ptCount 后插入 pt。
    """

    def _inject_tx(inner: str) -> str:
        if re.search(r'<c:ptCount val="\d+"\s*/>', inner):
            return re.sub(
                r'(<c:ptCount val="\d+"\s*/>)',
                lambda m: m.group(1) + f'<c:pt idx="0"><c:v>{_esc(name)}</c:v></c:pt>',
                inner, count=1)
        return (f'<c:strLit><c:ptCount val="1"/>'
                f'<c:pt idx="0"><c:v>{_esc(name)}</c:v></c:pt></c:strLit>')

    def repl(m: re.Match) -> str:
        inner = m.group(2)
        ats = list(re.finditer(r'(<c:v>)(.*?)(</c:v>)', inner, re.S))
        if ats:
            first = ats[0]
            inner2 = inner[:first.start()] + first.group(1) + _esc(name) + first.group(3)
            cursor = first.end()
            for a in ats[1:]:
                inner2 += inner[cursor:a.start()] + a.group(1) + a.group(3)
                cursor = a.end()
            inner2 += inner[cursor:]
            return m.group(1) + inner2 + m.group(3)
        return m.group(1) + _inject_tx(inner) + m.group(3)

    new_ser, n = re.subn(r'(<c:tx\b[^>]*>)(.*?)(</c:tx>)', repl, ser, count=1, flags=re.S)
    if n:
        return new_ser
    # 极少数图表系列无 c:tx：在 <c:ser> 开头补一个
    lit = (f'<c:tx><c:strLit><c:ptCount val="1"/>'
           f'<c:pt idx="0"><c:v>{_esc(name)}</c:v></c:pt></c:strLit></c:tx>')
    return re.sub(r'(<c:ser\b[^>]*>)', lambda m: m.group(1) + lit, ser, count=1)


def apply_chart_edit(xml: str, edit: dict) -> tuple[str, dict]:
    """按 edit 改写图表数据。返回 (新 xml, 摘要)。

    edit 形如：
      {"categories": ["A","B","C"],
       "series": [{"name":"2024","values":[1,2,3]}, {"name":"2025","values":[4,5,6]}],
       "title": "可选：图表标题"}
    单系列可简写 {"categories":[...], "values":[...], "name":"可选系列名"}。
    """
    cats = edit.get('categories')
    series = edit.get('series')
    if series is None and ('values' in edit or 'name' in edit):
        single = {}
        if 'name' in edit:
            single['name'] = edit['name']
        if 'values' in edit:
            single['values'] = edit['values']
        series = [single]

    ser_spans = list(re.finditer(r'<c:ser\b.*?</c:ser>', xml, re.S))
    summary = {'series_found': len(ser_spans), 'series_edited': 0, 'categories_set': bool(cats)}
    if not ser_spans:
        return xml, summary

    out: list[str] = []
    last = 0
    for i, m in enumerate(ser_spans):
        out.append(xml[last:m.start()])
        ser = m.group(0)
        if cats is not None:
            ser = _set_named_block(ser, 'c:cat', list(cats))
        if series is not None and i < len(series):
            s = series[i] or {}
            if s.get('name') is not None:
                ser = _set_series_name(ser, str(s['name']))
            if s.get('values') is not None:
                ser = _set_named_block(ser, 'c:val', list(s['values']))
            summary['series_edited'] += 1
        out.append(ser)
        last = m.end()
    out.append(xml[last:])
    new_xml = ''.join(out)

    title = edit.get('title')
    if title is not None:
        new_xml = _set_chart_title(new_xml, str(title))
        summary['title_set'] = True
    return new_xml, summary


def _set_chart_title(xml: str, title: str) -> str:
    """改写 <c:title> 内 rich 文本的首个 a:t（其余清空），保留格式。"""
    def repl(m: re.Match) -> str:
        inner = m.group(2)
        ats = list(re.finditer(r'(<a:t>)(.*?)(</a:t>)', inner, re.S))
        if not ats:
            return m.group(0)
        first = ats[0]
        inner2 = inner[:first.start()] + first.group(1) + _esc(title) + first.group(3)
        cursor = first.end()
        for a in ats[1:]:
            inner2 += inner[cursor:a.start()] + a.group(1) + a.group(3)
            cursor = a.end()
        inner2 += inner[cursor:]
        return m.group(1) + inner2 + m.group(3)
    return re.sub(r'(<c:title\b[^>]*>)(.*?)(</c:title>)', repl, xml, count=1, flags=re.S)
