"""Office 文档 XML 文件的命令行验证工具。

基于 XSD schema 和修订标记验证文档结构。

Usage:
    python validate.py <path> [--original <original_file>] [--auto-repair] [--author NAME]

第一个参数可以是：
- 包含 Office 文档 XML 文件的解包目录
- 打包的 Office 文件 (.docx/.pptx/.xlsx)，将被解包到临时目录

自动修复项：
- paraId/durableId 值超出 OOXML 限制
- w:t 元素中包含空白字符但缺少 xml:space="preserve"
"""

import argparse
import sys
import tempfile
import zipfile
from pathlib import Path

from validators import DOCXSchemaValidator, PPTXSchemaValidator, RedliningValidator

_VALID_SUFFIXES = {".docx", ".pptx", ".xlsx"}


def main():
    parser = argparse.ArgumentParser(description="Validate Office document XML files")
    parser.add_argument(
        "path",
        help="Path to unpacked directory or packed Office file (.docx/.pptx/.xlsx)",
    )
    parser.add_argument(
        "--original",
        required=False,
        default=None,
        help="Path to original file (.docx/.pptx/.xlsx). If omitted, all XSD errors are reported and redlining validation is skipped.",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--auto-repair",
        action="store_true",
        help="Automatically repair common issues (hex IDs, whitespace preservation)",
    )
    parser.add_argument(
        "--author",
        default="Assistant",
        help="Author name for redlining validation (default: Assistant)",
    )
    args = parser.parse_args()

    path = Path(args.path)
    assert path.exists(), f"Error: {path} does not exist"

    original_file = None
    if args.original:
        original_file = Path(args.original)
        assert original_file.is_file(), f"Error: {original_file} is not a file"
        assert original_file.suffix.lower() in _VALID_SUFFIXES, (
            f"Error: {original_file} must be a .docx, .pptx, or .xlsx file"
        )

    file_ext = (original_file or path).suffix.lower()
    assert file_ext in _VALID_SUFFIXES, (
        f"Error: Cannot determine file type from {path}. Use --original or provide a .docx/.pptx/.xlsx file."
    )

    if path.is_file() and path.suffix.lower() in _VALID_SUFFIXES:
        temp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(temp_dir)
        unpacked_dir = Path(temp_dir)
    else:
        assert path.is_dir(), f"Error: {path} is not a directory or Office file"
        unpacked_dir = path

    match file_ext:
        case ".docx":
            validators = [
                DOCXSchemaValidator(unpacked_dir, original_file, verbose=args.verbose),
            ]
            if original_file:
                validators.append(
                    RedliningValidator(
                        unpacked_dir, original_file,
                        verbose=args.verbose, author=args.author,
                    )
                )
        case ".pptx":
            validators = [
                PPTXSchemaValidator(unpacked_dir, original_file, verbose=args.verbose),
            ]
        case _:
            print(f"Error: Validation not supported for file type {file_ext}")
            sys.exit(1)

    if args.auto_repair:
        total_repairs = sum(v.repair() for v in validators)
        if total_repairs:
            print(f"Auto-repaired {total_repairs} issue(s)")

    ok = all(v.validate() for v in validators)

    if ok:
        print("All validations PASSED!")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
