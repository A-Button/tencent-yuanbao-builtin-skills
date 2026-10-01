"""清理解压后的 PPTX 目录中未被引用的文件。

用法: python clean.py <unpacked_dir>

示例:
    python clean.py unpacked/

本脚本会移除以下内容:
- 不在 sldIdLst 中的孤立幻灯片及其关系文件
- [trash] 目录（未被引用的文件）
- 已删除资源对应的孤立 .rels 文件
- 未被引用的媒体、嵌入对象、图表、图示、绘图、墨迹文件
- 未被引用的主题文件
- 未被引用的备注幻灯片
- 已删除文件对应的 Content-Type 覆盖项
"""

import re
import sys
from pathlib import Path

import defusedxml.minidom


def get_slides_in_sldidlst(unpacked_dir: Path) -> set[str]:
    """从 presentation.xml 的 sldIdLst 中获取所有被引用的幻灯片文件名。

    解析 presentation.xml.rels 建立 rId 到幻灯片文件名的映射，
    再从 presentation.xml 中提取 sldIdLst 里引用的 rId，
    返回实际被引用的幻灯片文件名集合。
    """
    pres_path = unpacked_dir / "ppt" / "presentation.xml"
    pres_rels_path = unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels"

    if not pres_path.exists() or not pres_rels_path.exists():
        return set()

    rels_dom = defusedxml.minidom.parse(str(pres_rels_path))
    rid_to_slide: dict[str, str] = {}
    for rel_elem in rels_dom.getElementsByTagName("Relationship"):
        rid = rel_elem.getAttribute("Id")
        target = rel_elem.getAttribute("Target")
        rel_type = rel_elem.getAttribute("Type")
        if "slide" in rel_type and target.startswith("slides/"):
            rid_to_slide[rid] = target[len("slides/"):]

    pres_content = pres_path.read_text(encoding="utf-8")
    referenced_rids = set(re.findall(r'<p:sldId[^>]*r:id="([^"]+)"', pres_content))

    return {rid_to_slide[rid] for rid in referenced_rids if rid in rid_to_slide}


def remove_orphaned_slides(unpacked_dir: Path) -> list[str]:
    """移除不在 sldIdLst 中的孤立幻灯片文件。

    同时删除对应的 .rels 文件，并从 presentation.xml.rels 中
    清除指向已删除幻灯片的 Relationship 节点。
    """
    slides_dir = unpacked_dir / "ppt" / "slides"
    slides_rels_dir = slides_dir / "_rels"
    pres_rels_path = unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels"

    if not slides_dir.exists():
        return []

    referenced_slides = get_slides_in_sldidlst(unpacked_dir)
    removed: list[str] = []

    for slide_file in slides_dir.glob("slide*.xml"):
        if slide_file.name in referenced_slides:
            continue
        rel_path = slide_file.relative_to(unpacked_dir)
        slide_file.unlink()
        removed.append(str(rel_path))

        rels_file = slides_rels_dir / f"{slide_file.name}.rels"
        if rels_file.exists():
            rels_file.unlink()
            removed.append(str(rels_file.relative_to(unpacked_dir)))

    if removed and pres_rels_path.exists():
        rels_dom = defusedxml.minidom.parse(str(pres_rels_path))
        modified = False

        for rel_elem in list(rels_dom.getElementsByTagName("Relationship")):
            target = rel_elem.getAttribute("Target")
            if target.startswith("slides/"):
                slide_name = target[len("slides/"):]
                if slide_name not in referenced_slides:
                    if rel_elem.parentNode:
                        rel_elem.parentNode.removeChild(rel_elem)
                        modified = True

        if modified:
            with open(pres_rels_path, "wb") as fh:
                fh.write(rels_dom.toxml(encoding="utf-8"))

    return removed


def purge_trash_folder(unpacked_dir: Path) -> list[str]:
    """删除 [trash] 目录及其中的所有文件。

    遍历 [trash] 目录中的文件逐个删除，最后移除空目录本身。
    """
    trash_dir = unpacked_dir / "[trash]"
    removed: list[str] = []

    if not (trash_dir.exists() and trash_dir.is_dir()):
        return removed

    for file_path in trash_dir.iterdir():
        if file_path.is_file():
            removed.append(str(file_path.relative_to(unpacked_dir)))
            file_path.unlink()
    trash_dir.rmdir()

    return removed


def get_slide_referenced_files(unpacked_dir: Path) -> set:
    """收集所有幻灯片 .rels 文件中引用的目标路径。

    扫描 ppt/slides/_rels/ 下的全部 .rels 文件，
    解析其中的 Relationship 节点，将目标路径解析为相对于解压目录的路径。
    """
    referenced: set = set()
    slides_rels_dir = unpacked_dir / "ppt" / "slides" / "_rels"

    if not slides_rels_dir.exists():
        return referenced

    for rels_file in slides_rels_dir.glob("*.rels"):
        dom = defusedxml.minidom.parse(str(rels_file))
        for rel_elem in dom.getElementsByTagName("Relationship"):
            target = rel_elem.getAttribute("Target")
            if not target:
                continue
            resolved = (rels_file.parent.parent / target).resolve()
            try:
                referenced.add(resolved.relative_to(unpacked_dir.resolve()))
            except ValueError:
                pass

    return referenced


def cleanup_orphan_rels(unpacked_dir: Path) -> list[str]:
    """清理 charts/diagrams/drawings 中孤立的 .rels 文件。

    如果 .rels 文件对应的资源文件不存在，或该资源未被任何幻灯片引用，
    则删除该 .rels 文件。
    """
    resource_dirs = ["charts", "diagrams", "drawings"]
    removed: list[str] = []
    slide_referenced = get_slide_referenced_files(unpacked_dir)

    for dir_name in resource_dirs:
        rels_dir = unpacked_dir / "ppt" / dir_name / "_rels"
        if not rels_dir.exists():
            continue

        for rels_file in rels_dir.glob("*.rels"):
            resource_file = rels_dir.parent / rels_file.name.replace(".rels", "")
            try:
                resource_rel_path = resource_file.resolve().relative_to(unpacked_dir.resolve())
            except ValueError:
                continue

            if not resource_file.exists() or resource_rel_path not in slide_referenced:
                rels_file.unlink()
                removed.append(str(rels_file.relative_to(unpacked_dir)))

    return removed


def get_referenced_files(unpacked_dir: Path) -> set:
    """递归收集解压目录中所有 .rels 文件引用的目标路径集合。

    遍历目录下全部 .rels 文件，解析每个 Relationship 节点的 Target 属性，
    将其解析为相对于解压根目录的路径后加入结果集合。
    """
    referenced: set = set()

    for rels_file in unpacked_dir.rglob("*.rels"):
        dom = defusedxml.minidom.parse(str(rels_file))
        for rel_elem in dom.getElementsByTagName("Relationship"):
            target = rel_elem.getAttribute("Target")
            if not target:
                continue
            resolved = (rels_file.parent.parent / target).resolve()
            try:
                referenced.add(resolved.relative_to(unpacked_dir.resolve()))
            except ValueError:
                pass

    return referenced


def remove_orphaned_files(unpacked_dir: Path, referenced: set) -> list[str]:
    """移除未被任何 .rels 文件引用的资源文件。

    检查 media、embeddings、charts、diagrams、tags、drawings、ink 目录中的文件，
    以及未被引用的主题文件和备注幻灯片，将不在 referenced 集合中的文件删除。
    """
    resource_dirs = ["media", "embeddings", "charts", "diagrams", "tags", "drawings", "ink"]
    removed: list[str] = []

    for dir_name in resource_dirs:
        dir_path = unpacked_dir / "ppt" / dir_name
        if not dir_path.exists():
            continue

        for file_path in dir_path.glob("*"):
            if not file_path.is_file():
                continue
            rel_path = file_path.relative_to(unpacked_dir)
            if rel_path not in referenced:
                file_path.unlink()
                removed.append(str(rel_path))

    theme_dir = unpacked_dir / "ppt" / "theme"
    if theme_dir.exists():
        for file_path in theme_dir.glob("theme*.xml"):
            rel_path = file_path.relative_to(unpacked_dir)
            if rel_path not in referenced:
                file_path.unlink()
                removed.append(str(rel_path))
                theme_rels = theme_dir / "_rels" / f"{file_path.name}.rels"
                if theme_rels.exists():
                    theme_rels.unlink()
                    removed.append(str(theme_rels.relative_to(unpacked_dir)))

    notes_dir = unpacked_dir / "ppt" / "notesSlides"
    if notes_dir.exists():
        for file_path in notes_dir.glob("*.xml"):
            if not file_path.is_file():
                continue
            rel_path = file_path.relative_to(unpacked_dir)
            if rel_path not in referenced:
                file_path.unlink()
                removed.append(str(rel_path))

        notes_rels_dir = notes_dir / "_rels"
        if notes_rels_dir.exists():
            for file_path in notes_rels_dir.glob("*.rels"):
                notes_file = notes_dir / file_path.name.replace(".rels", "")
                if not notes_file.exists():
                    file_path.unlink()
                    removed.append(str(file_path.relative_to(unpacked_dir)))

    return removed


def update_content_types(unpacked_dir: Path, removed_files: list[str]) -> None:
    """更新 [Content_Types].xml，移除已删除文件对应的 Override 条目。

    遍历所有 Override 节点，如果其 PartName 对应的文件已被删除，
    则从 DOM 中移除该节点，最后将修改写回文件。
    """
    ct_path = unpacked_dir / "[Content_Types].xml"
    if not ct_path.exists():
        return

    dom = defusedxml.minidom.parse(str(ct_path))
    modified = False

    for override in list(dom.getElementsByTagName("Override")):
        part_name = override.getAttribute("PartName").lstrip("/")
        if part_name in removed_files:
            if override.parentNode:
                override.parentNode.removeChild(override)
                modified = True

    if modified:
        with open(ct_path, "wb") as fh:
            fh.write(dom.toxml(encoding="utf-8"))


def clean_unused_files(unpacked_dir: Path) -> list[str]:
    """执行完整的清理流程，移除解压 PPTX 目录中所有未被引用的文件。

    依次执行：移除孤立幻灯片、清除 [trash] 目录、
    循环清理孤立 .rels 和未引用资源文件，最后更新 Content_Types。
    返回所有被删除文件的相对路径列表。
    """
    all_removed: list[str] = []

    slides_removed = remove_orphaned_slides(unpacked_dir)
    all_removed.extend(slides_removed)

    trash_removed = purge_trash_folder(unpacked_dir)
    all_removed.extend(trash_removed)

    while True:
        removed_rels = cleanup_orphan_rels(unpacked_dir)
        referenced = get_referenced_files(unpacked_dir)
        removed_files = remove_orphaned_files(unpacked_dir, referenced)

        batch_removed = removed_rels + removed_files
        if not batch_removed:
            break

        all_removed.extend(batch_removed)

    if all_removed:
        update_content_types(unpacked_dir, all_removed)

    return all_removed


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python clean.py <unpacked_dir>", file=sys.stderr)
        print("Example: python clean.py unpacked/", file=sys.stderr)
        sys.exit(1)

    unpacked_dir = Path(sys.argv[1])

    if not unpacked_dir.exists():
        print(f"Error: {unpacked_dir} not found", file=sys.stderr)
        sys.exit(1)

    removed = clean_unused_files(unpacked_dir)

    if removed:
        print(f"Removed {len(removed)} unreferenced files:")
        for f in removed:
            print(f"  {f}")
    else:
        print("No unreferenced files found")
