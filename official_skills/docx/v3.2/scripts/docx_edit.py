"""追踪修订相关操作的一站式 CLI（在 workspace 沙箱里跑）。

用法（子命令模式）：

    python docx_edit.py insert-tracked   <input.docx> <output.docx> <para-index> "<text>" [--author 元宝]
    python docx_edit.py delete-paragraph <input.docx> <output.docx> <para-index> [--author 元宝]
    python docx_edit.py reject-ins       <input.docx> <output.docx> <other-author> [--our-author 元宝]
    python docx_edit.py restore-del      <input.docx> <output.docx> <other-author> [--our-author 元宝]
    python docx_edit.py accept-all       <input.docx> <output.docx>

背景：`verify/docx/tool_config.py::get_script_allowlist` 只允许模型运行白名单里的
CLI；直接写 `python -c "from docxlib..."` 是走不通的（run_script 只放行 allowlist）。
为了让 s02–s06 场景能在沙箱内跑，这里把 `docxlib.tracked_changes` 的常用操作全部
暴露成子命令。语义与 helper 完全一致，作者默认「元宝」。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from docxlib import (
    accept_all_tracked,
    delete_paragraph_tracked,
    find_del_by_author,
    find_ins_by_author,
    insert_tracked,
    open_docx,
    reject_insertion,
    restore_deletion,
    save_docx,
)


def _insert_tracked(args) -> int:
    doc = open_docx(args.input_docx)
    paragraphs = doc.paragraphs
    if not paragraphs:
        print("Error: 输入文档无段落", file=sys.stderr)
        return 1
    if args.para_index < 0 or args.para_index >= len(paragraphs):
        print(
            f"Error: para-index {args.para_index} 超出范围 0..{len(paragraphs) - 1}",
            file=sys.stderr,
        )
        return 1
    insert_tracked(paragraphs[args.para_index], args.text, author=args.author)
    save_docx(doc, args.output_docx)
    print(f"已在第 {args.para_index} 段末尾插入 tracked-change → {args.output_docx}")
    return 0


def _delete_paragraph(args) -> int:
    doc = open_docx(args.input_docx)
    paragraphs = doc.paragraphs
    if not paragraphs:
        print("Error: 输入文档无段落", file=sys.stderr)
        return 1
    if args.para_index < 0 or args.para_index >= len(paragraphs):
        print(
            f"Error: para-index {args.para_index} 超出范围 0..{len(paragraphs) - 1}",
            file=sys.stderr,
        )
        return 1
    delete_paragraph_tracked(paragraphs[args.para_index], author=args.author)
    save_docx(doc, args.output_docx)
    print(f"已以追踪修订删除第 {args.para_index} 段 → {args.output_docx}")
    return 0


def _reject_ins(args) -> int:
    doc = open_docx(args.input_docx)
    inses = find_ins_by_author(doc, args.other_author)
    if not inses:
        print(f"Error: 未找到 author={args.other_author} 的 <w:ins>", file=sys.stderr)
        return 1
    for ins in inses:
        reject_insertion(ins, author=args.our_author)
    save_docx(doc, args.output_docx)
    print(f"已拒绝 {len(inses)} 处 {args.other_author} 的插入 → {args.output_docx}")
    return 0


def _restore_del(args) -> int:
    doc = open_docx(args.input_docx)
    dels = find_del_by_author(doc, args.other_author)
    if not dels:
        print(f"Error: 未找到 author={args.other_author} 的 <w:del>", file=sys.stderr)
        return 1
    for de in dels:
        restore_deletion(de, author=args.our_author)
    save_docx(doc, args.output_docx)
    print(f"已恢复 {len(dels)} 处 {args.other_author} 的删除 → {args.output_docx}")
    return 0


def _accept_all(args) -> int:
    doc = open_docx(args.input_docx)
    ins_n, del_n = accept_all_tracked(doc)
    save_docx(doc, args.output_docx)
    print(f"已接受 {ins_n} 处 ins / {del_n} 处 del → {args.output_docx}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="追踪修订 CLI（open_docx → 修改 → save_docx）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    def _add_io(sp):
        sp.add_argument("input_docx", help="输入 .docx")
        sp.add_argument("output_docx", help="输出 .docx")

    p1 = sub.add_parser("insert-tracked", help="在指定段落末尾追加一段 <w:ins>")
    _add_io(p1)
    p1.add_argument("para_index", type=int, help="目标段落 0-indexed")
    p1.add_argument("text", help="要插入的文本")
    p1.add_argument("--author", default="元宝")
    p1.set_defaults(func=_insert_tracked)

    p2 = sub.add_parser("delete-paragraph", help="以追踪修订整段删除")
    _add_io(p2)
    p2.add_argument("para_index", type=int, help="目标段落 0-indexed")
    p2.add_argument("--author", default="元宝")
    p2.set_defaults(func=_delete_paragraph)

    p3 = sub.add_parser("reject-ins", help="拒绝某作者的所有 <w:ins>（嵌套 w:del）")
    _add_io(p3)
    p3.add_argument("other_author", help="被拒绝的插入作者名，例如 Jane")
    p3.add_argument("--our-author", default="元宝", dest="our_author")
    p3.set_defaults(func=_reject_ins)

    p4 = sub.add_parser("restore-del", help="恢复某作者的所有 <w:del>（新增 w:ins 兄弟）")
    _add_io(p4)
    p4.add_argument("other_author", help="被恢复的删除作者名，例如 Jane")
    p4.add_argument("--our-author", default="元宝", dest="our_author")
    p4.set_defaults(func=_restore_del)

    p5 = sub.add_parser("accept-all", help="接受文档内所有追踪修订")
    _add_io(p5)
    p5.set_defaults(func=_accept_all)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
