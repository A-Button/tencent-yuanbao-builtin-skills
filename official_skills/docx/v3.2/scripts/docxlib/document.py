"""文档级操作：打开 / 保存 / 应用元宝默认排版。"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.shared import Pt

from .styles import (
    ASCII_HANSI,
    DEFAULT_SIZE_PT,
    EASTASIA,
    HEADING_SIZES_PT,
    apply_eastasia_font_to_style,
    ensure_heading_style,
)


def open_docx(path: str | Path | None = None):
    """打开一份 `.docx`；path 为 None 或路径不存在时返回一份新建空文档。

    - 已有文档：等价于 `docx.Document(path)`，不改动内容
    - 空白起手：`docx.Document()`，用来给「L3 自由生成」做起点
    """
    if path is None:
        return Document()
    p = Path(path)
    if not p.exists():
        return Document()
    return Document(str(p))


def save_docx(doc, path: str | Path) -> Path:
    """把 doc 存到 path，返回 Path 对象。"""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))
    return out


def ensure_yuanbao_defaults(doc) -> None:
    """幂等地把元宝默认排版应用到 `doc`。

    - Normal 样式：思源黑体（eastAsia）+ Times New Roman（ascii/hAnsi/cs），12pt
    - Heading 1 / Heading 2 / Heading 3：同族字体，粗体，尺寸表见 styles.py
    - 主 section：US Letter（12240 × 15840 DXA），四边 1 英寸页边距

    多次调用只保证「最终状态是元宝默认」，不会累计副作用。
    """
    normal = doc.styles["Normal"]
    apply_eastasia_font_to_style(
        normal,
        eastasia=EASTASIA,
        ascii=ASCII_HANSI,
        h_ansi=ASCII_HANSI,
        cs=ASCII_HANSI,
        size_pt=DEFAULT_SIZE_PT,
    )

    for level, size_pt in HEADING_SIZES_PT.items():
        ensure_heading_style(doc, level=level, size_pt=size_pt)

    # US Letter：宽 8.5in、高 11in，四边 1in。python-docx 用 Pt/Emu 换算即可。
    section = doc.sections[0]
    from docx.shared import Inches
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    _fix_settings_zoom(doc)


def _fix_settings_zoom(doc) -> None:
    """python-docx 默认写 `<w:zoom w:val="bestFit"/>`，但 XSD 期望 `<w:zoom>` 带
    `w:percent`。这里默认补 100。Windows / macOS Word 都能识别。
    """
    from .ooxml import qn
    try:
        settings_root = doc.settings.element
    except AttributeError:
        return
    zoom = settings_root.find(qn("w:zoom"))
    if zoom is None:
        return
    if zoom.get(qn("w:percent")):
        return
    zoom.set(qn("w:percent"), "100")
