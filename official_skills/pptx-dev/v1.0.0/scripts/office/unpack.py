"""解包 PPTX 文件以便编辑。

将 .pptx（本质是 ZIP）解压到目录，并把其中的 XML 文件格式化美化，便于用编辑器逐行修改。

用法:
    python office/unpack.py <pptx_file> <output_dir>

示例:
    python office/unpack.py /data/templates/商业/xxx.pptx unpacked/
"""

import argparse
import sys
import zipfile
from pathlib import Path

try:  # 优先使用更安全的解析器，缺失时回退到标准库
    import defusedxml.minidom as _minidom
except ImportError:  # pragma: no cover
    import xml.dom.minidom as _minidom

SMART_QUOTE_REPLACEMENTS = {
    "\u201c": "&#x201C;",
    "\u201d": "&#x201D;",
    "\u2018": "&#x2018;",
    "\u2019": "&#x2019;",
}


def unpack(input_file: str, output_directory: str) -> tuple[None, str]:
    """解包 PPTX 文件到指定目录，并格式化所有 XML。"""
    src = Path(input_file)
    dest = Path(output_directory)

    if not src.exists():
        return None, f"Error: {input_file} does not exist"
    if src.suffix.lower() != ".pptx":
        return None, f"Error: {input_file} must be a .pptx file"

    try:
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src, "r") as archive:
            archive.extractall(dest)

        all_xml = list(dest.rglob("*.xml")) + list(dest.rglob("*.rels"))
        for fpath in all_xml:
            _format_xml(fpath)
        for fpath in all_xml:
            _encode_smart_quotes(fpath)

        return None, f"Unpacked {input_file} ({len(all_xml)} XML files)"
    except zipfile.BadZipFile:
        return None, f"Error: {input_file} is not a valid PPTX file"
    except Exception as exc:  # pragma: no cover
        return None, f"Error unpacking: {exc}"


def _format_xml(target: Path) -> None:
    try:
        raw = target.read_text(encoding="utf-8")
        parsed = _minidom.parseString(raw)
        target.write_bytes(parsed.toprettyxml(indent="  ", encoding="utf-8"))
    except Exception:
        pass


def _encode_smart_quotes(target: Path) -> None:
    try:
        text = target.read_text(encoding="utf-8")
        for quote_char, xml_entity in SMART_QUOTE_REPLACEMENTS.items():
            text = text.replace(quote_char, xml_entity)
        target.write_text(text, encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unpack a PPTX file for editing")
    parser.add_argument("input_file", help="PPTX file to unpack")
    parser.add_argument("output_directory", help="Output directory")
    args = parser.parse_args()

    _, message = unpack(args.input_file, args.output_directory)
    print(message)
    if "Error" in message:
        sys.exit(1)
