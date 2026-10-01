"""L3 自由生成兜底：用 python-docx + docxlib 从零新建一份中文默认排版的 Word 文档。

用法：
    python new_doc.py <output.docx> [--example minimal|report|memo]

供 SKILL.md 中提及、也用于 verify/docx 的 s08 冒烟场景。骨架内演示：
- `ensure_yuanbao_defaults`（中文默认字体 + US Letter + 1 英寸边距）
- 标题 / 正文 / 分栏（分页）
- 双宽度表格（同时写 tblW 与 tcW）
- 页眉 / 页脚页码
- 目录（TOC 域）
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from docxlib import (
    add_footer_page_number,
    add_heading,
    add_page_break,
    add_paragraph,
    add_table_double_width,
    add_toc,
    ensure_yuanbao_defaults,
    open_docx,
    save_docx,
)


def build_minimal(doc) -> None:
    add_heading(doc, "示例文档", level=1)
    add_paragraph(doc, "这是一份用 python-docx + docxlib 生成的示例文档，用来演示元宝默认排版。")


def build_report(doc) -> None:
    add_heading(doc, "项目周报 · 第 42 周", level=1)
    add_paragraph(doc, "以下是本周的进展与下周计划，供团队周会同步。")

    add_heading(doc, "本周完成", level=2)
    add_paragraph(doc, "- 完成 docx 技能的 python-docx 化重构；单测与场景全部通过。")
    add_paragraph(doc, "- 输出双宽度表格 helper 与追踪修订 helper，覆盖删除、拒绝、恢复三条主链路。")

    add_heading(doc, "关键指标", level=2)
    add_table_double_width(
        doc,
        headers=["模块", "本周状态", "备注"],
        rows=[
            ["docxlib", "已合入", "含 6 类单测"],
            ["场景 s01…s08", "冒烟通过", "手动跑 4 条最脆弱路径"],
            ["SKILL.md", "已重写", "front-matter description 未动"],
        ],
        column_widths_dxa=[3000, 3000, 3360],
    )

    add_heading(doc, "下周计划", level=2)
    add_paragraph(doc, "- 打通 CI 冒烟，并把 baseline 更新到重构后的 turn 数。")
    add_paragraph(doc, "- 收敛依赖：把 python-docx 版本 pin 到 ~=1.2 写入镜像。")


def build_memo(doc) -> None:
    add_heading(doc, "备忘录", level=1)
    add_paragraph(doc, "自：技术团队")
    add_paragraph(doc, "至：产品与运营团队")
    add_paragraph(doc, "主题：docx 技能重构对接说明")

    add_page_break(doc)

    add_heading(doc, "背景", level=2)
    add_paragraph(doc, "旧版 docx 技能依赖手动 pack/unpack 处理 XML；重构后统一走 python-docx，日常写作与追踪修订、批注均改由脚本完成。")

    add_heading(doc, "对接要点", level=2)
    add_paragraph(doc, "- 生成新文档：先 `ensure_yuanbao_defaults`，再按需追加内容。")
    add_paragraph(doc, "- 编辑已有文档：`open_docx` → python-docx / docxlib 编辑 → `save_docx`。")
    add_paragraph(doc, "- 追踪修订与批注：走 `docxlib.tracked_changes` 与 `docxlib.comments`。")


EXAMPLES = {
    "minimal": build_minimal,
    "report": build_report,
    "memo": build_memo,
}


def main() -> int:
    parser = argparse.ArgumentParser(description="用 python-docx + docxlib 从零新建 Word 文档示例")
    parser.add_argument("output", help="输出 .docx")
    parser.add_argument(
        "--example",
        choices=sorted(EXAMPLES),
        default="report",
        help="演示模板类型（默认：report）",
    )
    parser.add_argument("--no-toc", action="store_true", help="不生成目录")
    parser.add_argument("--no-footer", action="store_true", help="不生成页脚页码")
    args = parser.parse_args()

    out = Path(args.output)
    if out.suffix.lower() != ".docx":
        print(f"Error: 输出必须是 .docx，收到 {out.suffix}", file=sys.stderr)
        return 1

    doc = open_docx()
    ensure_yuanbao_defaults(doc)

    if not args.no_toc:
        add_toc(doc)
        add_page_break(doc)

    EXAMPLES[args.example](doc)

    if not args.no_footer:
        add_footer_page_number(doc.sections[0])

    save_docx(doc, out)
    print(f"已生成 {out}（模板：{args.example}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
