"""段落 / 列表 / 表格 / 图片 / 页眉页脚 / 目录 等常用结构化 helper。

`add_paragraph`、`doc.add_table` 之类的常规能力直接用 python-docx 的原生 API，
本模块只在 python-docx 覆盖不到 / 有硬性 OOXML 规则的位置提供 helper：

- **表格双宽度**：`add_table_double_width`。同时写 `<w:tblW>` 与每个 cell 的
  `<w:tcW>`，避免部分平台（Google Docs / WPS）渲染异常。
- **图片三段 altText**：`add_picture_with_alttext`。python-docx 只写 `descr`；
  完整 alt 需要 `name`、`title`、`descr` 都填。
- **页面尺寸 / 页边距**：`set_page_size` / `set_page_margins`。DXA 单位对齐 skill 传统。
- **页脚页码**：`add_footer_page_number`。用 `<w:fldSimple w:instr=" PAGE ">`。
- **目录**：`add_toc`。用 `<w:fldChar>` + `<w:instrText> TOC \\o "1-3" \\h \\z </w:instrText>`。
- **超链接**：`add_external_hyperlink`。python-docx 1.2 不暴露 external hyperlink。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import OxmlElement
from docx.shared import Emu, Inches, Pt

from .ooxml import ensure_child_order, needs_xml_space_preserve, qn, set_text_with_preserve

# 部分 OOXML CT_TblPrBase 子元素的合法顺序（XSD sequence）
_TBLPR_ORDER = [
    qn("w:tblStyle"),
    qn("w:tblpPr"),
    qn("w:tblOverlap"),
    qn("w:bidiVisual"),
    qn("w:tblStyleRowBandSize"),
    qn("w:tblStyleColBandSize"),
    qn("w:tblW"),
    qn("w:jc"),
    qn("w:tblCellSpacing"),
    qn("w:tblInd"),
    qn("w:tblBorders"),
    qn("w:shd"),
    qn("w:tblLayout"),
    qn("w:tblCellMar"),
    qn("w:tblLook"),
    qn("w:tblCaption"),
    qn("w:tblDescription"),
    qn("w:tblPrChange"),
]
from .styles import EASTASIA, ASCII_HANSI, apply_font_to_run


def add_paragraph(doc_or_container, text: str = "", *, style: str | None = None):
    """新建段落，返回 python-docx Paragraph。

    与 `doc.add_paragraph` 的区别：文字默认走 `apply_font_to_run` 加中文字体，
    避免正文英文默认使用 Arial。传空字符串代表先建段再自己加 run。
    """
    p = doc_or_container.add_paragraph(style=style) if style else doc_or_container.add_paragraph()
    if text:
        run = p.add_run(text)
        apply_font_to_run(run, eastasia=EASTASIA, ascii=ASCII_HANSI)
    return p


def add_heading(doc, text: str, level: int = 1):
    """新建一段标题，等价于 `doc.add_heading` 但同步应用中文字体。"""
    h = doc.add_heading(text, level=level)
    for run in h.runs:
        apply_font_to_run(run, eastasia=EASTASIA, ascii=ASCII_HANSI)
    return h


def add_page_break(doc_or_paragraph) -> None:
    """在 doc 或 paragraph 末尾插入一个硬分页。"""
    if hasattr(doc_or_paragraph, "add_paragraph"):
        p = doc_or_paragraph.add_paragraph()
    else:
        p = doc_or_paragraph
    run = p.add_run()
    br = OxmlElement("w:br")
    br.set(qn("w:type"), "page")
    run._r.append(br)


def _dxa(value_or_inches):
    """允许传 int（DXA）或 float（英寸），统一转成 int DXA。"""
    if isinstance(value_or_inches, float):
        return int(value_or_inches * 1440)
    return int(value_or_inches)


def set_page_size(section, width_dxa: int, height_dxa: int, *, landscape: bool = False) -> None:
    """设 section 页面尺寸；DXA 单位（1440 DXA = 1 英寸）。

    横向：如果 landscape=True，会自动交换 width/height 并把 orient 设为 landscape。
    """
    if landscape:
        width_dxa, height_dxa = height_dxa, width_dxa
    section.page_width = Emu(width_dxa * 635)  # 1 DXA = 635 EMU
    section.page_height = Emu(height_dxa * 635)
    pg_sz = section._sectPr.find(qn("w:pgSz"))
    if pg_sz is None:
        pg_sz = OxmlElement("w:pgSz")
        section._sectPr.append(pg_sz)
    pg_sz.set(qn("w:orient"), "landscape" if landscape else "portrait")


def set_page_margins(section, *, top: int = 1440, right: int = 1440,
                     bottom: int = 1440, left: int = 1440) -> None:
    """按 DXA 设置四边页边距。默认 1 英寸。"""
    section.top_margin = Emu(top * 635)
    section.bottom_margin = Emu(bottom * 635)
    section.left_margin = Emu(left * 635)
    section.right_margin = Emu(right * 635)


def add_table_double_width(doc, headers: list[str], rows: list[list[str]],
                            *, column_widths_dxa: list[int] | None = None,
                            total_width_dxa: int | None = None,
                            header_shading: str | None = "D5E8F0"):
    """按「双宽度」规则新建一张表。

    - `column_widths_dxa` 未提供时按内容区宽度（total_width_dxa 或 9360 DXA / 6.5 英寸）等分。
    - 同时写 `<w:tblW>` 与每个 `<w:tc>/<w:tcW>`，两者数值必须一致。
    - `header_shading` 是十六进制颜色（不带 #），传 None 关闭。
    """
    n_cols = len(headers)
    if column_widths_dxa is None:
        total = total_width_dxa or 9360
        base = total // n_cols
        column_widths_dxa = [base] * n_cols
        column_widths_dxa[-1] += total - sum(column_widths_dxa)

    total_dxa = sum(column_widths_dxa)

    table = doc.add_table(rows=1 + len(rows), cols=n_cols)
    table.autofit = False
    table.alignment = WD_TABLE_ALIGNMENT.LEFT

    # 表宽
    tbl_pr = table._tbl.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        table._tbl.insert(0, tbl_pr)
    tbl_w = tbl_pr.find(qn("w:tblW"))
    if tbl_w is None:
        tbl_w = OxmlElement("w:tblW")
        tbl_pr.append(tbl_w)
    tbl_w.set(qn("w:w"), str(total_dxa))
    tbl_w.set(qn("w:type"), "dxa")

    # 边框
    tbl_borders = tbl_pr.find(qn("w:tblBorders"))
    if tbl_borders is None:
        tbl_borders = OxmlElement("w:tblBorders")
        tbl_pr.append(tbl_borders)
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = tbl_borders.find(qn(f"w:{side}"))
        if b is None:
            b = OxmlElement(f"w:{side}")
            tbl_borders.append(b)
        b.set(qn("w:val"), "single")
        b.set(qn("w:sz"), "4")
        b.set(qn("w:color"), "CCCCCC")

    # tblPr 子元素顺序：tblBorders 必须在 tblLayout / tblLook 之前
    ensure_child_order(tbl_pr, _TBLPR_ORDER)

    # grid + 每 cell tcW
    tbl_grid = table._tbl.find(qn("w:tblGrid"))
    if tbl_grid is None:
        tbl_grid = OxmlElement("w:tblGrid")
        table._tbl.append(tbl_grid)
    for grid_col in list(tbl_grid.findall(qn("w:gridCol"))):
        tbl_grid.remove(grid_col)
    for w in column_widths_dxa:
        gc = OxmlElement("w:gridCol")
        gc.set(qn("w:w"), str(w))
        tbl_grid.append(gc)

    def _set_cell_width(cell, dxa):
        tc_pr = cell._tc.get_or_add_tcPr()
        tc_w = tc_pr.find(qn("w:tcW"))
        if tc_w is None:
            tc_w = OxmlElement("w:tcW")
            tc_pr.append(tc_w)
        tc_w.set(qn("w:w"), str(dxa))
        tc_w.set(qn("w:type"), "dxa")

    def _set_cell_shading(cell, fill_hex):
        tc_pr = cell._tc.get_or_add_tcPr()
        shd = tc_pr.find(qn("w:shd"))
        if shd is None:
            shd = OxmlElement("w:shd")
            tc_pr.append(shd)
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), fill_hex)

    header_row = table.rows[0]
    for i, (cell, text, dxa) in enumerate(zip(header_row.cells, headers, column_widths_dxa)):
        _set_cell_width(cell, dxa)
        if header_shading:
            _set_cell_shading(cell, header_shading)
        p = cell.paragraphs[0]
        run = p.add_run(text)
        apply_font_to_run(run, eastasia=EASTASIA, ascii=ASCII_HANSI, bold=True)

    for r_i, row_data in enumerate(rows, start=1):
        for c_i, (cell, text, dxa) in enumerate(zip(table.rows[r_i].cells, row_data, column_widths_dxa)):
            _set_cell_width(cell, dxa)
            p = cell.paragraphs[0]
            run = p.add_run(str(text))
            apply_font_to_run(run, eastasia=EASTASIA, ascii=ASCII_HANSI)

    return table


def add_picture_with_alttext(paragraph, image_path: str | Path, *,
                              width_in: float | None = None, height_in: float | None = None,
                              alt_title: str = "", alt_desc: str = "", alt_name: str = "image"):
    """插入图片，同时写全 `docPr/@name`、`docPr/@title`、`docPr/@descr` 三段 altText。

    python-docx 只填 `descr`；`title` / `name` 需要手工补。返回 lxml `<w:drawing>` 元素。
    """
    run = paragraph.add_run()
    if width_in is not None:
        pic = run.add_picture(str(image_path), width=Inches(width_in))
    elif height_in is not None:
        pic = run.add_picture(str(image_path), height=Inches(height_in))
    else:
        pic = run.add_picture(str(image_path))

    # 定位 docPr
    drawing = run._r.find(qn("w:drawing"))
    if drawing is not None:
        for doc_pr in drawing.iter(qn("wp:docPr")):
            doc_pr.set("name", alt_name or doc_pr.get("name", ""))
            doc_pr.set("title", alt_title or "")
            doc_pr.set("descr", alt_desc or "")
    return drawing


def add_external_hyperlink(paragraph, url: str, text: str, *, style: str = "Hyperlink"):
    """在 paragraph 末尾追加一个外链超链接。返回 lxml `<w:hyperlink>` 元素。

    python-docx 1.2 不覆盖外链超链接；这里手写 `<w:hyperlink r:id="..">`。
    需要先在 document.part 上登记关系。
    """
    part = paragraph.part
    rid = part.relate_to(url, RT.HYPERLINK, is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), rid)

    new_r = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    rstyle = OxmlElement("w:rStyle")
    rstyle.set(qn("w:val"), style)
    rpr.append(rstyle)
    new_r.append(rpr)
    t = OxmlElement("w:t")
    set_text_with_preserve(t, text)
    new_r.append(t)
    hyperlink.append(new_r)

    paragraph._p.append(hyperlink)
    return hyperlink


def add_footer_page_number(section, *, prefix: str = "第 ", suffix: str = " 页") -> None:
    """在 section 的 default footer 加一个「第 X 页」字段。"""
    footer_p = section.footer.paragraphs[0]
    if prefix:
        run = footer_p.add_run(prefix)
        apply_font_to_run(run, eastasia=EASTASIA, ascii=ASCII_HANSI)
    fld = OxmlElement("w:fldSimple")
    fld.set(qn("w:instr"), "PAGE")
    footer_p._p.append(fld)
    if suffix:
        run = footer_p.add_run(suffix)
        apply_font_to_run(run, eastasia=EASTASIA, ascii=ASCII_HANSI)


def add_toc(doc, *, heading_range: str = "1-3", hyperlink: bool = True):
    """在文档末尾插入一个 TOC 字段。Word 打开时会自动刷新。

    - heading_range: `"1-3"` 表示收纳 H1..H3
    - hyperlink: 是否可点击跳转
    """
    p = doc.add_paragraph()
    r = p.add_run()

    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    r._r.append(fld_begin)

    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    # 反斜杠留在 f-string 表达式之外：Python < 3.12 不允许表达式部分含 `\`。
    hyperlink_switch = "\\h " if hyperlink else ""
    instr.text = f' TOC \\o "{heading_range}" {hyperlink_switch}\\z '
    r._r.append(instr)

    fld_sep = OxmlElement("w:fldChar")
    fld_sep.set(qn("w:fldCharType"), "separate")
    r._r.append(fld_sep)

    placeholder = OxmlElement("w:t")
    set_text_with_preserve(placeholder, "打开文档时按 F9 或右键“更新域”以刷新目录")
    r._r.append(placeholder)

    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    r._r.append(fld_end)
    return p
