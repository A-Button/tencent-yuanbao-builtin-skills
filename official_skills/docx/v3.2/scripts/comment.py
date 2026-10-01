"""向 DOCX 文档添加批注 / 回复批注。

用法：
    python comment.py <input.docx> <output.docx> <id> <text> [选项]
    python comment.py <input.docx> <output.docx> <id> <text> --parent 0        # 回复
    python comment.py <input.docx> <output.docx> <id> <text> --author 元宝     # 显式作者
    python comment.py <input.docx> <output.docx> <id> <text> --anchor-para 2   # 指定挂哪一段

不再需要"先 unpack 再手写 range 标记"这个环节——
CLI 内部直接调用 `docxlib.add_comment` / `docxlib.reply_comment`，一次完成：

1. 首次调用时按需 provision comments.xml 及其扩展 part
2. 追加 `<w:comment>` / `<w15:commentEx>` / `<w16cid:commentId>` / `<w16cex:commentExtensible>`
3. 在目标段落里插入 `<w:commentRangeStart>` / `<w:commentRangeEnd>` / `<w:commentReference>`
   （作为 `<w:p>` 的直接子元素，不嵌到 `<w:r>` 里）

正文里遇到 `&`、`<`、`>` 会由 lxml 正常转义；智能引号无需预先转成 XML 实体。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 允许 `python skills/docx/scripts/comment.py ...` 直接跑
_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from docxlib import add_comment, open_docx, reply_comment, save_docx


def main() -> int:
    p = argparse.ArgumentParser(description="向 DOCX 文档添加批注")
    p.add_argument("input_docx", help="输入 .docx")
    p.add_argument("output_docx", help="输出 .docx")
    p.add_argument("comment_id", type=int, help="批注 ID（必须唯一）")
    p.add_argument("text", help="批注正文")
    p.add_argument("--author", default="元宝", help="作者名（默认：元宝）")
    p.add_argument("--initials", default="Y", help="作者姓名首字母（默认：Y）")
    p.add_argument("--parent", type=int, help="父批注 ID（提供时本条作为回复）")
    p.add_argument(
        "--anchor-para",
        type=int,
        default=0,
        help="批注挂在哪一段（0-indexed，只在非回复模式下生效；默认：0）",
    )
    args = p.parse_args()

    input_path = Path(args.input_docx)
    output_path = Path(args.output_docx)
    if not input_path.is_file():
        print(f"Error: 找不到输入文件 {input_path}", file=sys.stderr)
        return 1
    if output_path.suffix.lower() != ".docx":
        print(f"Error: 输出文件必须是 .docx，收到 {output_path.suffix}", file=sys.stderr)
        return 1

    doc = open_docx(input_path)

    if args.parent is not None:
        cid = reply_comment(
            doc, args.parent, args.text,
            author=args.author, initials=args.initials, comment_id=args.comment_id,
        )
        kind = "回复"
    else:
        paragraphs = doc.paragraphs
        if not paragraphs:
            print("Error: 输入文档无段落可挂批注", file=sys.stderr)
            return 1
        if args.anchor_para < 0 or args.anchor_para >= len(paragraphs):
            print(
                f"Error: --anchor-para {args.anchor_para} 超出范围 0..{len(paragraphs) - 1}",
                file=sys.stderr,
            )
            return 1
        cid = add_comment(
            doc, paragraphs[args.anchor_para], args.text,
            author=args.author, initials=args.initials, comment_id=args.comment_id,
        )
        kind = "批注"

    save_docx(doc, output_path)
    print(f"已添加{kind} {cid} → {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
