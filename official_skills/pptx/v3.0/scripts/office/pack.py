"""将解包后的目录重新打包为 PPTX 文件。

压缩各 XML（移除多余空白），再打成 .pptx。PNG/JPEG 等已压缩媒体用 ZIP_STORED，
避免 zlib 二次白压。若环境内存在可选的 PPTX schema 校验器（validators 包）且提供了
--original，则顺带做一次自动修复+校验；否则跳过，不影响打包。

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

_CT_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
# 常见部件扩展名 → 内容类型。用于打包前自愈 [Content_Types].xml：只要包里有某扩展名的
# 部件而它既无逐部件 Override、其扩展名又不在 Default 里，就补一条 Default，避免成品
# 出现 content_type_missing（PowerPoint 打开报“需要修复”）。复盘：加了带内嵌 Excel 的
# 图表后 ppt/embeddings/*.xlsx 没登记、字体嵌入/页面复制过程又把模板原有的 jpeg Default
# 弄丢，导致 docProps/thumbnail.jpeg 与 xlsx 全部报缺失。这里只增不删、幂等。
_EXT_CONTENT_TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "gif": "image/gif",
    "bmp": "image/bmp",
    "tif": "image/tiff",
    "tiff": "image/tiff",
    "emf": "image/x-emf",
    "wmf": "image/x-wmf",
    "svg": "image/svg+xml",
    "webp": "image/webp",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls": "application/vnd.ms-excel",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "xml": "application/xml",
    "rels": "application/vnd.openxmlformats-package.relationships+xml",
    "fntdata": "application/x-fontdata",
    "ttf": "application/x-font-ttf",
    "otf": "application/vnd.ms-opentype",
    "bin": "application/vnd.openxmlformats-officedocument.oleObject",
    "mp4": "video/mp4",
    "m4v": "video/mp4",
    "mov": "video/quicktime",
    "avi": "video/avi",
    "wmv": "video/x-ms-wmv",
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "wav": "audio/wav",
    "wdp": "image/vnd.ms-photo",
}

# 已压缩或再 DEFLATE 几乎无收益的部件：按 STORED 写入，只压 XML/rels。
_STORED_SUFFIXES = frozenset({
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff",
    ".emf", ".wmf", ".wdp", ".webp", ".svg",
    ".mp4", ".m4v", ".mov", ".avi", ".wmv",
    ".mp3", ".m4a", ".wav",
    ".xlsx", ".xls", ".docx",
    ".bin", ".fntdata", ".ttf", ".otf",
})


def zip_compress_type(name: str) -> int:
    """OOXML 部件的 zip 压缩方式：媒体/字体/嵌套 Office 包 STORED，其余 DEFLATE。"""
    base = name.rsplit("/", 1)[-1]
    ext = ("" if "." not in base else "." + base.rsplit(".", 1)[-1]).lower()
    if ext in _STORED_SUFFIXES:
        return zipfile.ZIP_STORED
    return zipfile.ZIP_DEFLATED


def write_pptx_blobs(dest, blobs: dict, *, content_types: str = "[Content_Types].xml") -> None:
    """把 {archive_name: bytes} 写成 .pptx；[Content_Types].xml 置顶。"""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(blobs.keys(), key=lambda n: (n != content_types, n))
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zout:
        for name in ordered:
            zout.writestr(name, blobs[name], compress_type=zip_compress_type(name))


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

        _ensure_content_types(staging_dir)

        for pat in _XML_PATTERNS:
            for xml_path in staging_dir.rglob(pat):
                _compact_xml(xml_path)

        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(dest_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for entry in staging_dir.rglob("*"):
                if entry.is_file():
                    rel = entry.relative_to(staging_dir)
                    if len(rel.parts) == 1 and rel.name.startswith("."):
                        continue  # helper state, not an OOXML package part
                    arcname = rel.as_posix()
                    archive.write(entry, rel, compress_type=zip_compress_type(arcname))

    return None, f"Successfully packed {src_dir} to {output_file}"


def _ensure_content_types(staging_dir: Path) -> None:
    """打包前自愈 [Content_Types].xml：为包内所有部件补齐缺失的 Default（幂等、只增不删）。

    对每个部件，若其 PartName 无逐部件 Override、其扩展名又不在 Default 里，就按扩展名补一条
    Default（未知扩展名兜底 application/octet-stream）。避免 content_type_missing 型损坏。
    """
    from xml.etree import ElementTree as ET

    ct_path = staging_dir / "[Content_Types].xml"
    if not ct_path.exists():
        return
    try:
        tree = ET.parse(ct_path)
    except ET.ParseError:
        return
    root = tree.getroot()

    have_defaults = set()  # 已声明的扩展名（小写）
    override_parts = set()  # 已声明的逐部件 PartName
    for el in root:
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "Default":
            ext = el.get("Extension")
            if ext:
                have_defaults.add(ext.lower())
        elif tag == "Override":
            pn = el.get("PartName")
            if pn:
                override_parts.add(pn)

    needed_exts = {}  # ext(lower) -> content_type，需要补的
    for entry in staging_dir.rglob("*"):
        if not entry.is_file():
            continue
        rel = entry.relative_to(staging_dir).as_posix()
        if rel == "[Content_Types].xml":
            continue
        part_name = "/" + rel
        if part_name in override_parts:
            continue
        ext = rel.rsplit(".", 1)[-1].lower() if "." in rel else ""
        if not ext or ext in have_defaults or ext in needed_exts:
            continue
        needed_exts[ext] = _EXT_CONTENT_TYPES.get(ext, "application/octet-stream")

    if not needed_exts:
        return

    for ext, ctype in sorted(needed_exts.items()):
        el = ET.SubElement(root, f"{{{_CT_NS}}}Default")
        el.set("Extension", ext)
        el.set("ContentType", ctype)

    ET.register_namespace("", _CT_NS)
    tree.write(ct_path, encoding="UTF-8", xml_declaration=True)


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
