"""
用于验证 Office 文档 XML 文件是否符合 XSD 模式以及检查修订标记的命令行工具。

用法:
    python validate.py <path> [--original <原始文件>] [--auto-repair] [--author 作者名]

第一个参数可以是:
- 包含 Office 文档 XML 文件的解压目录
- 打包的 Office 文件（.docx/.pptx/.xlsx），会被解压到临时目录

自动修复功能:
- 修复超出 OOXML 限制的 paraId/durableId 值
- 补全含空白字符的 w:t 元素上缺失的 xml:space="preserve" 属性
"""

import argparse
import sys
import tempfile
import zipfile
from pathlib import Path

from validators import DOCXSchemaValidator, PPTXSchemaValidator, RedliningValidator

OFFICE_EXTENSIONS = [".docx", ".pptx", ".xlsx"]


def _build_arg_parser() -> argparse.ArgumentParser:
    """构建并返回命令行参数解析器。"""
    parser = argparse.ArgumentParser(description="验证 Office 文档 XML 文件")
    parser.add_argument(
        "path",
        help="解压目录或打包的 Office 文件（.docx/.pptx/.xlsx）的路径",
    )
    parser.add_argument(
        "--original",
        required=False,
        default=None,
        help="原始文件路径（.docx/.pptx/.xlsx）。若省略，将报告所有 XSD 错误并跳过修订标记验证。",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="启用详细输出",
    )
    parser.add_argument(
        "--auto-repair",
        action="store_true",
        help="自动修复常见问题（十六进制 ID、空白字符保留）",
    )
    parser.add_argument(
        "--author",
        default="yuanbao",
        help="用于修订标记验证的作者名称（默认: yuanbao）",
    )
    return parser


def _resolve_original(original_arg: str | None) -> Path | None:
    """解析并校验 --original 参数，返回 Path 或 None。"""
    if not original_arg:
        return None
    original_file = Path(original_arg)
    assert original_file.is_file(), f"Error: {original_file} is not a file"
    assert original_file.suffix.lower() in OFFICE_EXTENSIONS, (
        f"Error: {original_file} must be a .docx, .pptx, or .xlsx file"
    )
    return original_file


def _determine_extension(path: Path, original_file: Path | None) -> str:
    """根据路径或原始文件推断文档类型后缀。"""
    ext = (original_file or path).suffix.lower()
    assert ext in OFFICE_EXTENSIONS, (
        f"Error: Cannot determine file type from {path}. Use --original or provide a .docx/.pptx/.xlsx file."
    )
    return ext


def _unpack_if_needed(path: Path) -> Path:
    """若路径指向 Office 打包文件则解压到临时目录，否则直接返回目录路径。"""
    if path.is_file() and path.suffix.lower() in OFFICE_EXTENSIONS:
        tmp = tempfile.mkdtemp()
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(tmp)
        return Path(tmp)
    assert path.is_dir(), f"Error: {path} is not a directory or Office file"
    return path


def _create_validators(file_extension, unpacked_dir, original_file, *, verbose, author):
    """根据文件类型创建对应的验证器列表。"""
    match file_extension:
        case ".docx":
            result = [
                DOCXSchemaValidator(unpacked_dir, original_file, verbose=verbose),
            ]
            if original_file:
                result.append(
                    RedliningValidator(unpacked_dir, original_file, verbose=verbose, author=author)
                )
            return result
        case ".pptx":
            return [
                PPTXSchemaValidator(unpacked_dir, original_file, verbose=verbose),
            ]
        case _:
            print(f"Error: Validation not supported for file type {file_extension}")
            sys.exit(1)


def main():
    """Office 文档验证工具的主入口。解析参数、执行可选的自动修复，然后运行所有验证器。"""
    parser = _build_arg_parser()
    args = parser.parse_args()

    path = Path(args.path)
    assert path.exists(), f"Error: {path} does not exist"

    original_file = _resolve_original(args.original)
    file_extension = _determine_extension(path, original_file)
    unpacked_dir = _unpack_if_needed(path)

    validators = _create_validators(
        file_extension, unpacked_dir, original_file,
        verbose=args.verbose, author=args.author,
    )

    if args.auto_repair:
        total_repairs = sum(v.repair() for v in validators)
        if total_repairs:
            print(f"Auto-repaired {total_repairs} issue(s)")

    success = all(v.validate() for v in validators)

    if success:
        print("All validations PASSED!")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
