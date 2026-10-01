#!/usr/bin/env python3
"""表格（DrawingML a:tbl）读取/改写的共享逻辑（单一事实来源）。

inspect_deck.py / edit_table.py / check_tables.py 都从这里导入：
- 把 slideN 上的表格定位到 `slideN:tableK`（按 <a:tbl> 在该页 XML 的文档序）；
- 读取表格当前的单元格文本网格（模板示例内容）；
- 按计划改写单元格文本——用**定向字符串替换**保留每个 run 的格式（rPr/字体/颜色），
  不整树重序列化，避免破坏单元格里的复杂样式。

与图表不同，表格不是独立 part，而是直接内嵌在 slide XML 里（graphicFrame>a:graphic>
a:graphicData>a:tbl）。因此读写都作用在 ppt/slides/slideN.xml 本身。

读写顺序约定：行按 <a:tr> 文档序、单元格按行内 <a:tc> 文档序索引（含被合并的占位
单元格也计入，以保证 inspect 看到的网格下标与 edit 写回的下标完全一致）。
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path

_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'

_TBL_RE = re.compile(r'<a:tbl\b.*?</a:tbl>', re.S)
_TR_RE = re.compile(r'<a:tr\b.*?</a:tr>', re.S)
_TC_RE = re.compile(r'<a:tc\b.*?</a:tc>', re.S)
_AT_RE = re.compile(r'<a:t>(.*?)</a:t>', re.S)
_P_RE = re.compile(r'<a:p\b[^>]*>.*?</a:p>', re.S)


def _esc(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _unesc(s: str) -> str:
    return (s.replace('&lt;', '<').replace('&gt;', '>')
            .replace('&quot;', '"').replace('&apos;', "'").replace('&amp;', '&'))


# ---------------------------------------------------------------------------
# 读取表格网格
# ---------------------------------------------------------------------------

def _cell_text(tc_xml: str) -> str:
    """单元格全部文本：各段落 <a:t> 拼接，段落间用换行。"""
    paras: list[str] = []
    for pm in _P_RE.finditer(tc_xml):
        txt = ''.join(_unesc(m.group(1)) for m in _AT_RE.finditer(pm.group(0)))
        if txt:
            paras.append(txt)
    return '\n'.join(paras)


def read_table_grid(tbl_xml: str) -> list[list[str]]:
    grid: list[list[str]] = []
    for tr in _TR_RE.finditer(tbl_xml):
        row = [_cell_text(tc.group(0)) for tc in _TC_RE.finditer(tr.group(0))]
        grid.append(row)
    return grid


def table_signature(grid: list[list[str]]) -> str:
    """表格内容签名：所有单元格按行主序拼接、去空白。用于与模板基线比对。"""
    def n(x: str) -> str:
        return re.sub(r'\s+', '', str(x))
    return '|'.join('/'.join(n(c) for c in row) for row in grid)


# ---------------------------------------------------------------------------
# 定位：slideN -> [(ref, tbl_xml)]，附 span 以便就地替换
# ---------------------------------------------------------------------------

def iter_tables(slide_xml: str, slide_no: int):
    """产出 (ref, match)：match.group(0) 是该 <a:tbl> 整段，match.start()/end() 为其在 slide_xml 的位置。"""
    for k, m in enumerate(_TBL_RE.finditer(slide_xml), start=1):
        yield f'slide{slide_no}:table{k}', m


def slide_tables_text(slide_xml: str, slide_no: int) -> list[dict]:
    out: list[dict] = []
    for ref, m in iter_tables(slide_xml, slide_no):
        grid = read_table_grid(m.group(0))
        out.append({
            'ref': ref,
            'rows': len(grid),
            'cols': max((len(r) for r in grid), default=0),
            'cells': grid,
        })
    return out


def slide_tables_unpacked(unpacked: Path, slide_no: int) -> list[dict]:
    slide = unpacked / 'ppt' / 'slides' / f'slide{slide_no}.xml'
    if not slide.exists():
        return []
    try:
        return slide_tables_text(slide.read_text(encoding='utf-8'), slide_no)
    except (OSError, UnicodeDecodeError):
        return []


def slide_tables_zip(z: zipfile.ZipFile, slide_no: int) -> list[dict]:
    name = f'ppt/slides/slide{slide_no}.xml'
    try:
        return slide_tables_text(z.read(name).decode('utf-8', 'ignore'), slide_no)
    except KeyError:
        return []


# ---------------------------------------------------------------------------
# 改写单元格文本
# ---------------------------------------------------------------------------

def _set_cell_text(tc_xml: str, text: str) -> str:
    """把单元格文本设为 text，保留首个 run 的格式（rPr）。

    策略：把首个 <a:t> 设为新文本，清空该单元格其余 <a:t>（保留 run 结构与格式）。
    若单元格无任何 run（空格），则在首个段落里插入一个最简 run。
    多行文本（含 \\n）原样写入首个 <a:t>（同段落内换行不渲染为换行，建议表格单元格单行）。
    """
    ats = list(_AT_RE.finditer(tc_xml))
    if ats:
        first = ats[0]
        head = tc_xml[:first.start()] + '<a:t>' + _esc(text) + '</a:t>'
        rest = tc_xml[first.end():]
        rest = _AT_RE.sub('<a:t></a:t>', rest)
        return head + rest
    run = f'<a:r><a:t>{_esc(text)}</a:t></a:r>'
    # 优先插在 endParaRPr 之前（schema：run 在 endParaRPr 前）
    new, n = re.subn(r'(<a:endParaRPr\b)', run + r'\1', tc_xml, count=1)
    if n:
        return new
    new, n = re.subn(r'(</a:p>)', run + r'\1', tc_xml, count=1)
    return new if n else tc_xml


def apply_table_edit(tbl_xml: str, edit: dict) -> tuple[str, dict]:
    """按 edit['cells']（二维数组）改写表格单元格文本。返回 (新 xml, 摘要)。

    cells[r][c] 对应第 r 个 <a:tr> 的第 c 个 <a:tc>；值为 None/缺省则保留原内容。
    允许参差：只改提供到的行/格。
    """
    cells = edit.get('cells')
    summary = {'rows_found': 0, 'cells_edited': 0}
    if not cells:
        return tbl_xml, summary

    rows = list(_TR_RE.finditer(tbl_xml))
    summary['rows_found'] = len(rows)
    out: list[str] = []
    last = 0
    for ri, rm in enumerate(rows):
        out.append(tbl_xml[last:rm.start()])
        row_xml = rm.group(0)
        if ri < len(cells) and cells[ri] is not None:
            row_vals = cells[ri]
            tcs = list(_TC_RE.finditer(row_xml))
            o2: list[str] = []
            l2 = 0
            for ci, cm in enumerate(tcs):
                o2.append(row_xml[l2:cm.start()])
                tc = cm.group(0)
                if ci < len(row_vals) and row_vals[ci] is not None:
                    tc = _set_cell_text(tc, str(row_vals[ci]))
                    summary['cells_edited'] += 1
                o2.append(tc)
                l2 = cm.end()
            o2.append(row_xml[l2:])
            row_xml = ''.join(o2)
        out.append(row_xml)
        last = rm.end()
    out.append(tbl_xml[last:])
    return ''.join(out), summary
