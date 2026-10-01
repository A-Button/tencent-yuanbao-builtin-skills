"""中文默认字体、标题样式、eastAsia 字体写入的 helper。

python-docx 的 `Font` 对象**不暴露 `eastAsia`**：即使 `run.font.name = "思源黑体"`
也只写 `w:ascii`，中文 run 就悄悄走了 Word 兜底字体。所有需要中文字体的场景
都要用这里的 `apply_eastasia_font_to_style` / `apply_font_to_run`。
"""

from __future__ import annotations

from copy import deepcopy

from docx.oxml import OxmlElement
from lxml import etree

from .ooxml import qn

EASTASIA = "思源黑体"
ASCII_HANSI = "Times New Roman"

DEFAULT_SIZE_PT = 12
HEADING_SIZES_PT = {
    1: 16,
    2: 14,
    3: 13,
}


def _get_or_create_rpr(style_or_element):
    """style 内部：走 element.get_or_add_rPr()；元素内部：手工找 w:rPr。"""
    if hasattr(style_or_element, "element"):
        return style_or_element.element.get_or_add_rPr()
    rpr = style_or_element.find(qn("w:rPr"))
    if rpr is None:
        rpr = OxmlElement("w:rPr")
        style_or_element.insert(0, rpr)
    return rpr


def _set_rfonts(rpr, *, eastasia=None, ascii=None, h_ansi=None, cs=None) -> None:
    """幂等更新 `<w:rFonts>`。参数为 None 时不动对应属性。"""
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.insert(0, rfonts)
    if eastasia is not None:
        rfonts.set(qn("w:eastAsia"), eastasia)
    if ascii is not None:
        rfonts.set(qn("w:ascii"), ascii)
    if h_ansi is not None:
        rfonts.set(qn("w:hAnsi"), h_ansi)
    if cs is not None:
        rfonts.set(qn("w:cs"), cs)


def _set_size(rpr, size_pt: int) -> None:
    """OOXML `<w:sz w:val="..">` 单位是 half-point：12pt → 24。cs 用 `<w:szCs>`。"""
    for tag, ns_tag in [("w:sz", "w:sz"), ("w:szCs", "w:szCs")]:
        elem = rpr.find(qn(ns_tag))
        if elem is None:
            elem = OxmlElement(tag)
            rpr.append(elem)
        elem.set(qn("w:val"), str(size_pt * 2))


def _set_bold(rpr, bold: bool) -> None:
    for tag in ("w:b", "w:bCs"):
        elem = rpr.find(qn(tag))
        if bold:
            if elem is None:
                elem = OxmlElement(tag)
                rpr.append(elem)
        else:
            if elem is not None:
                rpr.remove(elem)


def apply_eastasia_font_to_style(
    style,
    *,
    eastasia: str | None = None,
    ascii: str | None = None,
    h_ansi: str | None = None,
    cs: str | None = None,
    size_pt: int | None = None,
    bold: bool | None = None,
) -> None:
    """在指定 `docx.styles.Style` 的 rPr 上打字体/字号/粗体。

    python-docx 的 Font 对象设不了 eastAsia、也无法可靠 idempotent 覆盖 rPr，
    统一走 lxml。
    """
    rpr = _get_or_create_rpr(style)
    if any(v is not None for v in (eastasia, ascii, h_ansi, cs)):
        _set_rfonts(rpr, eastasia=eastasia, ascii=ascii, h_ansi=h_ansi, cs=cs)
    if size_pt is not None:
        _set_size(rpr, size_pt)
    if bold is not None:
        _set_bold(rpr, bold)


def apply_font_to_run(run, *, eastasia=EASTASIA, ascii=ASCII_HANSI, size_pt=None, bold=None):
    """给单个 run 打字体。与 `apply_eastasia_font_to_style` 语义一致，作用域是 run。"""
    rpr = run._r.get_or_add_rPr()
    _set_rfonts(rpr, eastasia=eastasia, ascii=ascii, h_ansi=ascii, cs=ascii)
    if size_pt is not None:
        _set_size(rpr, size_pt)
    if bold is not None:
        _set_bold(rpr, bold)
    return run


def ensure_heading_style(doc, level: int, size_pt: int, *, bold: bool = True) -> None:
    """把内置 `Heading N` 样式改成元宝需要的字体/字号/粗体 + `outlineLevel = level-1`。

    `outlineLevel` 是 TOC 识别标题层级的关键；缺了 TOC 会生成不出目录。
    """
    style_name = f"Heading {level}"
    style = doc.styles[style_name]
    apply_eastasia_font_to_style(
        style,
        eastasia=EASTASIA,
        ascii=ASCII_HANSI,
        h_ansi=ASCII_HANSI,
        cs=ASCII_HANSI,
        size_pt=size_pt,
        bold=bold,
    )

    # 段落级 outlineLevel
    ppr = style.element.get_or_add_pPr()
    outline = ppr.find(qn("w:outlineLvl"))
    if outline is None:
        outline = OxmlElement("w:outlineLvl")
        ppr.append(outline)
    outline.set(qn("w:val"), str(max(0, level - 1)))


def copy_rpr(source_run_or_element):
    """深拷贝某个 run 的 `<w:rPr>`，用于在 tracked change 里保留格式。

    传入可以是 python-docx 的 Run，也可以是 lxml 的 `<w:r>` 元素。
    没找到 rPr 返回 None。
    """
    if hasattr(source_run_or_element, "_r"):
        r = source_run_or_element._r
    else:
        r = source_run_or_element
    rpr = r.find(qn("w:rPr"))
    if rpr is None:
        return None
    return deepcopy(rpr)
