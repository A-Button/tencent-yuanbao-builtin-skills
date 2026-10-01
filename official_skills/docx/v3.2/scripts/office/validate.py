"""对 Office 文档（.docx / .pptx / .xlsx）执行 XSD schema 校验与追踪修订一致性校验。

用法：
    python validate.py <path> [--original <original>] [--author NAME] [--auto-repair]

`path` 必须是 `.docx` / `.pptx` / `.xlsx` 文件。内部会临时解包到 tempdir 后交给
`office/validators/*` 里的校验器。校验器实现本身保持不变。

自动修复会处理：
- durableId / paraId 超出 OOXML 上限
- 含空白的 `w:t` 元素缺 `xml:space="preserve"`
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import zipfile
from pathlib import Path

from validators import DOCXSchemaValidator, PPTXSchemaValidator, RedliningValidator


def main() -> int:
    parser = argparse.ArgumentParser(description="校验 Office 文档的 XML 文件")
    parser.add_argument("path", help="Office 文件路径（.docx / .pptx / .xlsx）")
    parser.add_argument(
        "--original",
        default=None,
        help="原始文件路径；提供后 XSD 校验器会忽略原文件已存在的错误，追踪修订校验器会以此做基线",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="输出详细信息",
    )
    parser.add_argument(
        "--auto-repair",
        action="store_true",
        help="自动修复常见问题（durableId、xml:space=preserve）",
    )
    parser.add_argument(
        "--author",
        default="元宝",
        help="追踪修订校验所用的作者名（默认：元宝）",
    )
    parser.add_argument(
        "--no-redline-check",
        action="store_true",
        help="跳过追踪修订一致性校验；只跑 XSD",
    )
    args = parser.parse_args()

    path = Path(args.path)
    if not path.is_file():
        print(f"Error: {path} 不存在或不是文件", file=sys.stderr)
        return 1
    if path.suffix.lower() not in {".docx", ".pptx", ".xlsx"}:
        print(f"Error: 只支持 .docx / .pptx / .xlsx，收到 {path.suffix}", file=sys.stderr)
        return 1

    original_file = Path(args.original) if args.original else None
    if original_file is not None:
        if not original_file.is_file():
            print(f"Error: --original {original_file} 不存在", file=sys.stderr)
            return 1
        if original_file.suffix.lower() != path.suffix.lower():
            print(
                f"Error: --original 后缀 ({original_file.suffix}) 与 {path.suffix} 不匹配",
                file=sys.stderr,
            )
            return 1

    with tempfile.TemporaryDirectory() as tmp:
        unpacked = Path(tmp)
        try:
            with zipfile.ZipFile(path) as zf:
                zf.extractall(unpacked)
        except zipfile.BadZipFile as exc:
            print(f"Error: {path} 不是合法的 Office 文件：{exc}", file=sys.stderr)
            return 1

        validators = _build_validators(
            unpacked=unpacked,
            original_file=original_file,
            suffix=path.suffix.lower(),
            author=args.author,
            verbose=args.verbose,
            skip_redline=args.no_redline_check,
        )

        if args.auto_repair:
            total = sum(v.repair() for v in validators)
            if total:
                print(f"已自动修复 {total} 处问题")

        ok = all(v.validate() for v in validators)
        if ok:
            print("所有校验已通过！")
        return 0 if ok else 1


def _build_validators(
    *,
    unpacked: Path,
    original_file: Path | None,
    suffix: str,
    author: str,
    verbose: bool,
    skip_redline: bool,
) -> list:
    if suffix == ".docx":
        validators: list = [DOCXSchemaValidator(unpacked, original_file, verbose=verbose)]
        if original_file is not None and not skip_redline:
            validators.append(
                RedliningValidator(unpacked, original_file, verbose=verbose, author=author)
            )
        return validators
    if suffix == ".pptx":
        return [PPTXSchemaValidator(unpacked, original_file, verbose=verbose)]
    # xlsx：无独立校验器，跳过
    return []


if __name__ == "__main__":
    sys.exit(main())
