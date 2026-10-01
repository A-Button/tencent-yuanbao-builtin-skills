"""docxlib —— python-docx 之上的 Word 编辑 helper。

公开的公共 API：

- 文档级：`open_docx` / `save_docx` / `ensure_yuanbao_defaults`
- 样式：`apply_font_to_run` / `ensure_heading_style` / `EASTASIA` / `ASCII_HANSI`
- 结构化 block：`add_paragraph` / `add_heading` / `add_page_break`
  / `add_table_double_width` / `add_picture_with_alttext`
  / `add_external_hyperlink` / `add_footer_page_number` / `add_toc`
  / `set_page_size` / `set_page_margins`
- 追踪修订：`insert_tracked` / `delete_tracked` / `replace_run_text_with_tracked`
  / `delete_paragraph_tracked` / `reject_insertion` / `restore_deletion`
  / `find_ins_by_author` / `find_del_by_author` / `accept_all_tracked`
- 批注：`add_comment` / `reply_comment`
- 底层：`qn` / `NS` / `now_utc_z`（供高阶自定义场景用）

设计原则：常规能力交回 python-docx 原生 API；只在必要处封装。
"""

from .blocks import (
    add_external_hyperlink,
    add_footer_page_number,
    add_heading,
    add_page_break,
    add_paragraph,
    add_picture_with_alttext,
    add_table_double_width,
    add_toc,
    set_page_margins,
    set_page_size,
)
from .comments import add_comment, reply_comment
from .document import ensure_yuanbao_defaults, open_docx, save_docx
from .ooxml import NS, hex_id_8, now_utc_z, qn
from .styles import (
    ASCII_HANSI,
    DEFAULT_SIZE_PT,
    EASTASIA,
    HEADING_SIZES_PT,
    apply_eastasia_font_to_style,
    apply_font_to_run,
    ensure_heading_style,
)
from .tracked_changes import (
    accept_all_tracked,
    delete_paragraph_tracked,
    delete_tracked,
    find_del_by_author,
    find_ins_by_author,
    insert_tracked,
    reject_insertion,
    replace_run_text_with_tracked,
    restore_deletion,
)

__all__ = [
    "NS",
    "ASCII_HANSI",
    "DEFAULT_SIZE_PT",
    "EASTASIA",
    "HEADING_SIZES_PT",
    "accept_all_tracked",
    "add_comment",
    "add_external_hyperlink",
    "add_footer_page_number",
    "add_heading",
    "add_page_break",
    "add_paragraph",
    "add_picture_with_alttext",
    "add_table_double_width",
    "add_toc",
    "apply_eastasia_font_to_style",
    "apply_font_to_run",
    "delete_paragraph_tracked",
    "delete_tracked",
    "ensure_heading_style",
    "ensure_yuanbao_defaults",
    "find_del_by_author",
    "find_ins_by_author",
    "hex_id_8",
    "insert_tracked",
    "now_utc_z",
    "open_docx",
    "qn",
    "reject_insertion",
    "replace_run_text_with_tracked",
    "reply_comment",
    "restore_deletion",
    "save_docx",
    "set_page_margins",
    "set_page_size",
]
