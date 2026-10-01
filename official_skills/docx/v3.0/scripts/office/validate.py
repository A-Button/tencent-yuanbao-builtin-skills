"""命令行工具：对 Office 文档执行 XSD schema 校验与追踪修订一致性校验。

用法：
    python validate.py <路径> [--original <原始文件>] [--auto-repair] [--author NAME]

第一个参数既可以是：
- 已解包的 Office 文档目录；
- 也可以是 .docx / .pptx / .xlsx 文件（将自动解压到临时目录）。

自动修复会处理：
- paraId / durableId 超出 OOXML 上限
- 含空白的 w:t 元素缺失 xml:space="preserve"
"""

import argparse
import sys
import tempfile
import zipfile
from pathlib import Path

from validators import DOCXSchemaValidator, PPTXSchemaValidator, RedliningValidator


def main():
    parser = argparse.ArgumentParser(description="校验 Office 文档的 XML 文件")
    parser.add_argument(
        "path",
        help="已解包目录 或 Office 文件（.docx/.pptx/.xlsx）的路径",
    )
    parser.add_argument(
        "--original",
        required=False,
        default=None,
        help="原始文件（.docx/.pptx/.xlsx）路径；省略时会输出全部 XSD 错误，并跳过追踪修订校验",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="输出详细信息",
    )
    parser.add_argument(
        "--auto-repair",
        action="store_true",
        help="自动修复常见问题（十六进制 ID、空白保留）",
    )
    parser.add_argument(
        "--author",
        default="元宝",
        help="追踪修订校验所用的作者名（默认：元宝）",
    )
    args = parser.parse_args()

    path = Path(args.path)
    assert path.exists(), f"Error: {path} 不存在"

    original_file = None
    if args.original:
        original_file = Path(args.original)
        assert original_file.is_file(), f"Error: {original_file} 不是文件"
        assert original_file.suffix.lower() in [".docx", ".pptx", ".xlsx"], (
            f"Error: {original_file} 必须是 .docx / .pptx / .xlsx 文件"
        )

    file_extension = (original_file or path).suffix.lower()
    assert file_extension in [".docx", ".pptx", ".xlsx"], (
        f"Error: 无法从 {path} 推断文件类型。请使用 --original 或传入 .docx/.pptx/.xlsx 文件。"
    )

    if path.is_file() and path.suffix.lower() in [".docx", ".pptx", ".xlsx"]:
        temp_dir = tempfile.mkdtemp()
        with zipfile.ZipFile(path, "r") as zf:
            zf.extractall(temp_dir)
        unpacked_dir = Path(temp_dir)
    else:
        assert path.is_dir(), f"Error: {path} 既不是目录也不是 Office 文件"
        unpacked_dir = path

    match file_extension:
        case ".docx":
            validators = [
                DOCXSchemaValidator(unpacked_dir, original_file, verbose=args.verbose),
            ]
            if original_file:
                validators.append(
                    RedliningValidator(unpacked_dir, original_file, verbose=args.verbose, author=args.author)
                )
        case ".pptx":
            validators = [
                PPTXSchemaValidator(unpacked_dir, original_file, verbose=args.verbose),
            ]
        case _:
            print(f"Error: 不支持的文件类型 {file_extension}")
            sys.exit(1)

    if args.auto_repair:
        total_repairs = sum(v.repair() for v in validators)
        if total_repairs:
            print(f"已自动修复 {total_repairs} 处问题")

    success = all(v.validate() for v in validators)

    if success:
        print("所有校验已通过！")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
