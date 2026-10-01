"""向解压后的 PPTX 目录中添加新幻灯片。

用法: python add_slide.py <unpacked_dir> <source>

source 参数支持以下两种形式:
  - 幻灯片文件（如 slide2.xml）——复制该幻灯片
  - 版式文件（如 slideLayout2.xml）——基于版式创建空白幻灯片

示例:
    python add_slide.py unpacked/ slide2.xml
    # 复制 slide2，生成 slide5.xml

    python add_slide.py unpacked/ slideLayout2.xml
    # 基于 slideLayout2.xml 创建 slide5.xml

查看可用版式: ls unpacked/ppt/slideLayouts/

脚本会输出需要插入到 presentation.xml 中的 <p:sldId> 元素。
"""

import re
import shutil
import sys
from pathlib import Path

_SLIDE_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
)
_SLIDE_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
)
_LAYOUT_REL_TYPE = (
    "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout"
)

_BLANK_SLIDE_TEMPLATE = '''\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:sld xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
  <p:cSld>
    <p:spTree>
      <p:nvGrpSpPr>
        <p:cNvPr id="1" name=""/>
        <p:cNvGrpSpPr/>
        <p:nvPr/>
      </p:nvGrpSpPr>
      <p:grpSpPr>
        <a:xfrm>
          <a:off x="0" y="0"/>
          <a:ext cx="0" cy="0"/>
          <a:chOff x="0" y="0"/>
          <a:chExt cx="0" cy="0"/>
        </a:xfrm>
      </p:grpSpPr>
    </p:spTree>
  </p:cSld>
  <p:clrMapOvr>
    <a:masterClrMapping/>
  </p:clrMapOvr>
</p:sld>'''

_RELS_WRAPPER = '''\
<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="{rel_type}" Target="{target}"/>
</Relationships>'''


def get_next_slide_number(slides_dir: Path) -> int:
    """获取下一个可用的幻灯片编号。"""
    nums = [
        int(m.group(1))
        for f in slides_dir.glob("slide*.xml")
        if (m := re.match(r"slide(\d+)\.xml", f.name))
    ]
    return max(nums) + 1 if nums else 1


def parse_source(source: str) -> tuple[str, str | None]:
    """解析来源字符串，判断是版式还是已有幻灯片。

    返回 ("layout", 版式文件名) 或 ("slide", None)。
    """
    if source.startswith("slideLayout") and source.endswith(".xml"):
        return ("layout", source)
    return ("slide", None)


def create_slide_from_layout(unpacked_dir: Path, layout_file: str) -> None:
    """基于指定的版式模板创建一张新的空白幻灯片。"""
    slides_dir = unpacked_dir / "ppt" / "slides"
    rels_dir = slides_dir / "_rels"
    layouts_dir = unpacked_dir / "ppt" / "slideLayouts"

    layout_path = layouts_dir / layout_file
    if not layout_path.exists():
        print(f"Error: {layout_path} not found", file=sys.stderr)
        sys.exit(1)

    next_num = get_next_slide_number(slides_dir)
    dest = f"slide{next_num}.xml"
    dest_slide = slides_dir / dest
    dest_rels = rels_dir / f"{dest}.rels"

    dest_slide.write_text(_BLANK_SLIDE_TEMPLATE, encoding="utf-8")

    rels_dir.mkdir(exist_ok=True)
    rels_xml = _RELS_WRAPPER.format(
        rel_type=_LAYOUT_REL_TYPE,
        target=f"../slideLayouts/{layout_file}",
    )
    dest_rels.write_text(rels_xml, encoding="utf-8")

    _register_content_type(unpacked_dir, dest)
    rid = _register_presentation_rel(unpacked_dir, dest)
    next_slide_id = _next_available_slide_id(unpacked_dir)

    print(f"Created {dest} from {layout_file}")
    print(
        f'Add to presentation.xml <p:sldIdLst>:'
        f' <p:sldId id="{next_slide_id}" r:id="{rid}"/>'
    )


def duplicate_slide(unpacked_dir: Path, source: str) -> None:
    """复制一张已有的幻灯片（去除备注页关联）。"""
    slides_dir = unpacked_dir / "ppt" / "slides"
    rels_dir = slides_dir / "_rels"
    source_slide = slides_dir / source

    if not source_slide.exists():
        print(f"Error: {source_slide} not found", file=sys.stderr)
        sys.exit(1)

    next_num = get_next_slide_number(slides_dir)
    dest = f"slide{next_num}.xml"
    dest_slide = slides_dir / dest
    source_rels = rels_dir / f"{source}.rels"
    dest_rels = rels_dir / f"{dest}.rels"

    shutil.copy2(source_slide, dest_slide)

    if source_rels.exists():
        shutil.copy2(source_rels, dest_rels)
        rels_text = dest_rels.read_text(encoding="utf-8")
        rels_text = re.sub(
            r'\s*<Relationship[^>]*Type="[^"]*notesSlide"[^>]*/>\s*',
            "\n",
            rels_text,
        )
        dest_rels.write_text(rels_text, encoding="utf-8")

    _register_content_type(unpacked_dir, dest)
    rid = _register_presentation_rel(unpacked_dir, dest)
    next_slide_id = _next_available_slide_id(unpacked_dir)

    print(f"Created {dest} from {source}")
    print(
        f'Add to presentation.xml <p:sldIdLst>:'
        f' <p:sldId id="{next_slide_id}" r:id="{rid}"/>'
    )


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _register_content_type(unpacked_dir: Path, dest: str) -> None:
    """在 [Content_Types].xml 中为新幻灯片注册内容类型。"""
    ct_path = unpacked_dir / "[Content_Types].xml"
    ct_xml = ct_path.read_text(encoding="utf-8")

    override = (
        f'<Override PartName="/ppt/slides/{dest}"'
        f' ContentType="{_SLIDE_CONTENT_TYPE}"/>'
    )

    if f"/ppt/slides/{dest}" not in ct_xml:
        ct_xml = ct_xml.replace("</Types>", f"  {override}\n</Types>")
        ct_path.write_text(ct_xml, encoding="utf-8")


def _register_presentation_rel(unpacked_dir: Path, dest: str) -> str:
    """在 presentation.xml.rels 中添加新幻灯片的关系条目，返回分配的 rId。"""
    pres_rels_path = unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels"
    pres_rels = pres_rels_path.read_text(encoding="utf-8")

    existing_ids = [int(n) for n in re.findall(r'Id="rId(\d+)"', pres_rels)]
    next_rid_num = max(existing_ids) + 1 if existing_ids else 1
    rid = f"rId{next_rid_num}"

    rel_entry = (
        f'<Relationship Id="{rid}"'
        f' Type="{_SLIDE_REL_TYPE}"'
        f' Target="slides/{dest}"/>'
    )

    if f"slides/{dest}" not in pres_rels:
        pres_rels = pres_rels.replace(
            "</Relationships>", f"  {rel_entry}\n</Relationships>"
        )
        pres_rels_path.write_text(pres_rels, encoding="utf-8")

    return rid


def _next_available_slide_id(unpacked_dir: Path) -> int:
    """从 presentation.xml 中读取已有的 sldId，返回下一个可用 ID。"""
    pres_path = unpacked_dir / "ppt" / "presentation.xml"
    pres_xml = pres_path.read_text(encoding="utf-8")
    ids = [int(n) for n in re.findall(r'<p:sldId[^>]*id="(\d+)"', pres_xml)]
    return max(ids) + 1 if ids else 256


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python add_slide.py <unpacked_dir> <source>", file=sys.stderr)
        print("", file=sys.stderr)
        print("Source can be:", file=sys.stderr)
        print("  slide2.xml        - duplicate an existing slide", file=sys.stderr)
        print("  slideLayout2.xml  - create from a layout template", file=sys.stderr)
        print("", file=sys.stderr)
        print("To see available layouts: ls <unpacked_dir>/ppt/slideLayouts/", file=sys.stderr)
        sys.exit(1)

    unpacked_dir = Path(sys.argv[1])
    source = sys.argv[2]

    if not unpacked_dir.exists():
        print(f"Error: {unpacked_dir} not found", file=sys.stderr)
        sys.exit(1)

    source_type, layout_file = parse_source(source)

    if source_type == "layout" and layout_file is not None:
        create_slide_from_layout(unpacked_dir, layout_file)
    else:
        duplicate_slide(unpacked_dir, source)
