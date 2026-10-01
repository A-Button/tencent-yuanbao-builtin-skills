"""将解包后的目录重新打包为 PPTX 文件。

压缩各 XML（移除多余空白），再打成 .pptx。若环境内存在可选的 PPTX schema 校验器
（validators 包）且提供了 --original，则顺带做一次自动修复+校验；否则跳过，不影响打包。

用法:
    python office/pack.py <input_directory> <output_file.pptx> [--original <模板.pptx>]

示例:
    python office/pack.py unpacked/ output.pptx --original /data/templates/商业/xxx.pptx
"""

import argparse
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

try:
    import defusedxml.minidom as _minidom
except ImportError:  # pragma: no cover
    import xml.dom.minidom as _minidom

_XML_PATTERNS = ("*.xml", "*.rels")


def pack(
    input_directory: str,
    output_file: str,
    original_file: str | None = None,
    validate: bool = True,
) -> tuple[None, str]:
    """将解压后的 PPTX 目录重新打包为单个 .pptx 文件。"""
    src_dir = Path(input_directory)
    dest_path = Path(output_file)

    if not src_dir.is_dir():
        return None, f"Error: {src_dir} is not a directory"
    if dest_path.suffix.lower() != ".pptx":
        return None, f"Error: {output_file} must be a .pptx file"

    if validate and original_file and Path(original_file).exists():
        msg = _try_validate(src_dir, Path(original_file))
        if msg:
            print(msg)

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


def _try_validate(unpacked_dir: Path, original_file: Path) -> str | None:
    """可选 schema 校验。validators 包不可用时静默跳过。"""
    try:
        from validators import PPTXSchemaValidator  # type: ignore
    except Exception:
        return None
    try:
        validator = PPTXSchemaValidator(unpacked_dir, original_file)
        repaired = validator.repair()
        passed = validator.validate()
        parts = []
        if repaired:
            parts.append(f"Auto-repaired {repaired} issue(s)")
        parts.append("Schema validation PASSED!" if passed else "Schema validation reported issues")
        return "\n".join(parts)
    except Exception as exc:
        return f"Validation skipped ({exc})"


def _compact_xml(xml_file: Path) -> None:
    try:
        with open(xml_file, encoding="utf-8") as fh:
            dom = _minidom.parse(fh)
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
    except Exception as err:  # pragma: no cover
        print(f"ERROR: Failed to parse {xml_file.name}: {err}", file=sys.stderr)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pack a directory into a PPTX file")
    parser.add_argument("input_directory", help="Unpacked PPTX directory")
    parser.add_argument("output_file", help="Output .pptx file")
    parser.add_argument("--original", help="Original template for optional schema validation")
    parser.add_argument(
        "--validate",
        type=lambda x: x.lower() == "true",
        default=True,
        metavar="true|false",
        help="Run optional schema validation if available (default: true)",
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
