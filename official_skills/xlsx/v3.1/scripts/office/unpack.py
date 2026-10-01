"""解包 Office 文件 (DOCX, PPTX, XLSX) 以便编辑。

解压 ZIP 归档，美化打印 XML 文件，并可选地：
- 合并具有相同格式的相邻 run 元素（仅 DOCX）
- 简化来自同一作者的相邻修订标记（仅 DOCX）

Usage:
    python unpack.py <office_file> <output_dir> [options]

Examples:
    python unpack.py document.docx unpacked/
    python unpack.py presentation.pptx unpacked/
    python unpack.py document.docx unpacked/ --merge-runs false
"""

import argparse
import sys
import zipfile
from pathlib import Path

import defusedxml.minidom

from helpers.merge_runs import merge_runs as do_merge_runs
from helpers.simplify_redlines import simplify_redlines as do_simplify_redlines

_SMART_QUOTE_MAP = {
    "\u201c": "&#x201C;",
    "\u201d": "&#x201D;",
    "\u2018": "&#x2018;",
    "\u2019": "&#x2019;",
}

_VALID_SUFFIXES = {".docx", ".pptx", ".xlsx"}


def unpack(
    input_file: str,
    output_directory: str,
    merge_runs: bool = True,
    simplify_redlines: bool = True,
) -> tuple[None, str]:
    src = Path(input_file)
    dst = Path(output_directory)
    suffix = src.suffix.lower()

    if not src.exists():
        return None, f"Error: {input_file} does not exist"

    if suffix not in _VALID_SUFFIXES:
        return None, f"Error: {input_file} must be a .docx, .pptx, or .xlsx file"

    try:
        dst.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(dst)

        xml_files = list(dst.rglob("*.xml")) + list(dst.rglob("*.rels"))
        for xf in xml_files:
            _pretty_print_xml(xf)

        msg = f"Unpacked {input_file} ({len(xml_files)} XML files)"

        if suffix == ".docx":
            if simplify_redlines:
                count, _ = do_simplify_redlines(str(dst))
                msg += f", simplified {count} tracked changes"
            if merge_runs:
                count, _ = do_merge_runs(str(dst))
                msg += f", merged {count} runs"

        for xf in xml_files:
            _escape_smart_quotes(xf)

        return None, msg

    except zipfile.BadZipFile:
        return None, f"Error: {input_file} is not a valid Office file"
    except Exception as e:
        return None, f"Error unpacking: {e}"


def _pretty_print_xml(xml_file: Path) -> None:
    try:
        content = xml_file.read_text(encoding="utf-8")
        dom = defusedxml.minidom.parseString(content)
        xml_file.write_bytes(dom.toprettyxml(indent="  ", encoding="utf-8"))
    except Exception:
        pass


def _escape_smart_quotes(xml_file: Path) -> None:
    try:
        content = xml_file.read_text(encoding="utf-8")
        for char, entity in _SMART_QUOTE_MAP.items():
            content = content.replace(char, entity)
        xml_file.write_text(content, encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Unpack an Office file (DOCX, PPTX, XLSX) for editing"
    )
    parser.add_argument("input_file", help="Office file to unpack")
    parser.add_argument("output_directory", help="Output directory")
    parser.add_argument(
        "--merge-runs",
        type=lambda v: v.lower() == "true",
        default=True,
        metavar="true|false",
        help="Merge adjacent runs with identical formatting (DOCX only, default: true)",
    )
    parser.add_argument(
        "--simplify-redlines",
        type=lambda v: v.lower() == "true",
        default=True,
        metavar="true|false",
        help="Merge adjacent tracked changes from same author (DOCX only, default: true)",
    )
    args = parser.parse_args()

    _, message = unpack(
        args.input_file,
        args.output_directory,
        merge_runs=args.merge_runs,
        simplify_redlines=args.simplify_redlines,
    )
    print(message)

    if "Error" in message:
        sys.exit(1)
