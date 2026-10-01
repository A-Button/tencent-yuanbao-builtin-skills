"""将目录打包为 DOCX、PPTX 或 XLSX 文件。

自动执行校验与修复，压缩 XML 格式，并生成最终的 Office 文件。

用法:
    python pack.py <input_directory> <output_file> [--original <file>] [--validate true|false]

示例:
    python pack.py unpacked/ output.docx --original input.docx
    python pack.py unpacked/ output.pptx --validate false
"""

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import defusedxml.minidom

from validators import DOCXSchemaValidator, PPTXSchemaValidator, RedliningValidator

_SUPPORTED_EXTENSIONS = {".docx", ".pptx", ".xlsx"}
_XML_PATTERNS = ("*.xml", "*.rels")
_DEFAULT_AUTHOR = "yuanbao"


def pack(
    input_directory: str,
    output_file: str,
    original_file: str | None = None,
    validate: bool = True,
    infer_author_func=None,
) -> tuple[None, str]:
    """将解压后的 Office 目录重新打包为单个文件。

    参数:
        input_directory: 解压后的 Office 文档所在目录。
        output_file: 输出的 Office 文件路径（.docx/.pptx/.xlsx）。
        original_file: 用于校验对比的原始文件路径（可选）。
        validate: 是否在打包前执行校验与自动修复，默认为 True。
        infer_author_func: 用于推断作者名称的回调函数（可选）。

    返回:
        (None, 结果消息字符串) 的元组。
    """
    src_dir = Path(input_directory)
    dest_path = Path(output_file)
    ext = dest_path.suffix.lower()

    if not src_dir.is_dir():
        return None, f"Error: {src_dir} is not a directory"

    if ext not in _SUPPORTED_EXTENSIONS:
        return None, f"Error: {output_file} must be a .docx, .pptx, or .xlsx file"

    if validate and original_file:
        orig_path = Path(original_file)
        if orig_path.exists():
            ok, msg = _execute_validation(src_dir, orig_path, ext, infer_author_func)
            if msg:
                print(msg)
            if not ok:
                return None, f"Error: Validation failed for {src_dir}"

    with tempfile.TemporaryDirectory() as tmp:
        staging_dir = Path(tmp) / "content"
        shutil.copytree(src_dir, staging_dir)

        for pat in _XML_PATTERNS:
            for xml_path in staging_dir.rglob(pat):
                _compact_xml(xml_path)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry in staging_dir.rglob("*"):
                if entry.is_file():
                    archive.write(entry, entry.relative_to(staging_dir))

    return None, f"Successfully packed {src_dir} to {output_file}"


def _execute_validation(
    unpacked_dir: Path,
    original_file: Path,
    suffix: str,
    infer_author_func=None,
) -> tuple[bool, str | None]:
    """对解压目录执行 schema 校验和修复。

    参数:
        unpacked_dir: 解压后的文档目录。
        original_file: 原始 Office 文件路径。
        suffix: 文件扩展名（如 ".docx"）。
        infer_author_func: 作者推断回调函数（可选）。

    返回:
        (校验是否通过, 输出消息或 None) 的元组。
    """
    messages: list[str] = []
    validator_list = []

    if suffix == ".docx":
        author = _DEFAULT_AUTHOR
        if infer_author_func:
            try:
                author = infer_author_func(unpacked_dir, original_file)
            except ValueError as exc:
                print(
                    f"Warning: {exc} Using default author '{_DEFAULT_AUTHOR}'.",
                    file=sys.stderr,
                )

        validator_list = [
            DOCXSchemaValidator(unpacked_dir, original_file),
            RedliningValidator(unpacked_dir, original_file, author=author),
        ]
    elif suffix == ".pptx":
        validator_list = [PPTXSchemaValidator(unpacked_dir, original_file)]

    if not validator_list:
        return True, None

    repair_count = sum(v.repair() for v in validator_list)
    if repair_count:
        messages.append(f"Auto-repaired {repair_count} issue(s)")

    passed = all(v.validate() for v in validator_list)

    if passed:
        messages.append("All validations PASSED!")

    return passed, "\n".join(messages) if messages else None


def _compact_xml(xml_file: Path) -> None:
    """压缩 XML 文件：移除多余的空白文本节点和注释节点。

    参数:
        xml_file: 待处理的 XML 文件路径。

    异常:
        解析失败时会将错误信息输出到 stderr 并重新抛出异常。
    """
    try:
        with open(xml_file, encoding="utf-8") as fh:
            dom = defusedxml.minidom.parse(fh)

        for elem in dom.getElementsByTagName("*"):
            if elem.tagName.endswith(":t"):
                continue

            for child in list(elem.childNodes):
                is_blank_text = (
                    child.nodeType == child.TEXT_NODE
                    and child.nodeValue
                    and child.nodeValue.strip() == ""
                )
                if is_blank_text or child.nodeType == child.COMMENT_NODE:
                    elem.removeChild(child)

        xml_file.write_bytes(dom.toxml(encoding="UTF-8"))
    except Exception as err:
        print(f"ERROR: Failed to parse {xml_file.name}: {err}", file=sys.stderr)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Pack a directory into a DOCX, PPTX, or XLSX file"
    )
    parser.add_argument("input_directory", help="Unpacked Office document directory")
    parser.add_argument("output_file", help="Output Office file (.docx/.pptx/.xlsx)")
    parser.add_argument(
        "--original",
        help="Original file for validation comparison",
    )
    parser.add_argument(
        "--validate",
        type=lambda x: x.lower() == "true",
        default=True,
        metavar="true|false",
        help="Run validation with auto-repair (default: true)",
    )
    args = parser.parse_args()

    _, message = pack(
        args.input_directory,
        args.output_file,
        original_file=args.original,
        validate=args.validate,
    )
    print(message)

    if "Error" in message:
        sys.exit(1)
