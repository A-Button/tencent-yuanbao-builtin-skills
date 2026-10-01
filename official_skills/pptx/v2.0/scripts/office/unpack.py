"""解包 Office 文件（DOCX、PPTX、XLSX）以便编辑。

将 ZIP 压缩包解压，对 XML 文件进行格式化美化，并可选择：
- 合并具有相同格式的相邻文本段落（仅适用于 DOCX）
- 简化同一作者的相邻修订记录（仅适用于 DOCX）

用法:
    python unpack.py <office_file> <output_dir> [options]

示例:
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

SMART_QUOTE_REPLACEMENTS = {
    "\u201c": "&#x201C;",
    "\u201d": "&#x201D;",
    "\u2018": "&#x2018;",
    "\u2019": "&#x2019;",
}


def unpack(
    input_file: str,
    output_directory: str,
    merge_runs: bool = True,
    simplify_redlines: bool = True,
) -> tuple[None, str]:
    """解包 Office 文件到指定目录。

    将给定的 Office 文件（DOCX/PPTX/XLSX）解压到目标目录，
    格式化所有 XML 文件，并根据参数执行可选的后处理操作。

    参数:
        input_file: 待解包的 Office 文件路径。
        output_directory: 解包内容的输出目录。
        merge_runs: 是否合并格式相同的相邻 run 节点（仅 DOCX）。
        simplify_redlines: 是否简化同一作者的相邻修订标记（仅 DOCX）。

    返回:
        元组 (None, 消息字符串)，消息中包含操作结果或错误信息。
    """
    src = Path(input_file)
    dest = Path(output_directory)
    ext = src.suffix.lower()

    if not src.exists():
        return None, f"Error: {input_file} does not exist"

    if ext not in {".docx", ".pptx", ".xlsx"}:
        return None, f"Error: {input_file} must be a .docx, .pptx, or .xlsx file"

    try:
        dest.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(src, "r") as archive:
            archive.extractall(dest)

        all_xml = list(dest.rglob("*.xml")) + list(dest.rglob("*.rels"))
        for fpath in all_xml:
            _format_xml(fpath)

        result_msg = f"Unpacked {input_file} ({len(all_xml)} XML files)"

        if ext == ".docx":
            if simplify_redlines:
                num_simplified, _ = do_simplify_redlines(str(dest))
                result_msg += f", simplified {num_simplified} tracked changes"

            if merge_runs:
                num_merged, _ = do_merge_runs(str(dest))
                result_msg += f", merged {num_merged} runs"

        for fpath in all_xml:
            _encode_smart_quotes(fpath)

        return None, result_msg

    except zipfile.BadZipFile:
        return None, f"Error: {input_file} is not a valid Office file"
    except Exception as exc:
        return None, f"Error unpacking: {exc}"


def _format_xml(target: Path) -> None:
    """将 XML 文件格式化为带缩进的可读形式。

    参数:
        target: 需要格式化的 XML 文件路径。
    """
    try:
        raw = target.read_text(encoding="utf-8")
        parsed = defusedxml.minidom.parseString(raw)
        target.write_bytes(parsed.toprettyxml(indent="  ", encoding="utf-8"))
    except Exception:
        pass


def _encode_smart_quotes(target: Path) -> None:
    """将 XML 文件中的智能引号字符替换为对应的 XML 实体编码。

    参数:
        target: 需要处理的 XML 文件路径。
    """
    try:
        text = target.read_text(encoding="utf-8")
        for quote_char, xml_entity in SMART_QUOTE_REPLACEMENTS.items():
            text = text.replace(quote_char, xml_entity)
        target.write_text(text, encoding="utf-8")
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
