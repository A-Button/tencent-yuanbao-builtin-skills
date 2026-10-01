"""清理解压后的 PPTX 目录中未被引用的文件。

用法: python scripts/clean.py <unpacked_dir>

删除被引用关系剔除后产生的孤立内容：不在 sldIdLst 中的幻灯片及其 .rels、
[trash] 目录、孤立的 charts/diagrams/drawings .rels、未被引用的 media/embeddings/
charts/diagrams/tags/drawings/ink/theme/notesSlides 文件，并同步 [Content_Types].xml。
删除多余幻灯片后运行本脚本可避免残留媒体导致打开异常。
"""

import sys
from pathlib import Path
from xml.etree import ElementTree as ET

try:
    import defusedxml.minidom as _minidom
except ImportError:  # pragma: no cover
    import xml.dom.minidom as _minidom


_P = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _elements_by_localname(dom, localname: str) -> list:
    """Return all elements whose local (prefix-stripped) tag name matches.

    ``minidom.getElementsByTagName`` is prefix-sensitive, so it misses elements
    serialized with an auto-generated prefix (e.g. ``ns0:Relationship``). Matching on
    the local name keeps clean.py robust regardless of how upstream tools serialized
    the relationships / content-types parts.
    """
    return [
        el
        for el in dom.getElementsByTagName("*")
        if el.tagName.rsplit(":", 1)[-1] == localname
    ]


def get_slides_in_sldidlst(unpacked_dir: Path) -> set[str]:
    pres_path = unpacked_dir / "ppt" / "presentation.xml"
    pres_rels_path = unpacked_dir / "ppt" / "_rels" / "presentation.xml.rels"
    if not pres_path.exists() or not pres_rels_path.exists():
        return set()

    # Parse via ElementTree with namespace-URI matching so prefix style (p:/r:/ns0:)
    # never affects which slides are considered referenced.
    rid_to_slide: dict[str, str] = {}
    for rel in ET.parse(pres_rels_path).getroot().iter(f"{{{_REL_NS}}}Relationship"):
        target = rel.get("Target", "")
        rel_type = rel.get("Type", "")
        if "slide" in rel_type and target.startswith("slides/"):
            rid_to_slide[rel.get("Id", "")] = target[len("slides/"):]

    referenced: set[str] = set()
    for sld_id in ET.parse(pres_path).getroot().iter(f"{{{_P}}}sldId"):
        rid = sld_id.get(f"{{{_R}}}id")
        if rid in rid_to_slide:
            referenced.add(rid_to_slide[rid])
    return referenced


def remove_orphaned_slides(unpacked_dir: Path) -> list[str]:
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
        slide_file.unlink()
        removed.append(str(slide_file.relative_to(unpacked_dir)))
        rels_file = slides_rels_dir / f"{slide_file.name}.rels"
        if rels_file.exists():
            rels_file.unlink()
            removed.append(str(rels_file.relative_to(unpacked_dir)))

    if removed and pres_rels_path.exists():
        rels_dom = _minidom.parse(str(pres_rels_path))
        modified = False
        for rel_elem in list(_elements_by_localname(rels_dom, "Relationship")):
            target = rel_elem.getAttribute("Target")
            if target.startswith("slides/"):
                slide_name = target[len("slides/"):]
                if slide_name not in referenced_slides and rel_elem.parentNode:
                    rel_elem.parentNode.removeChild(rel_elem)
                    modified = True
        if modified:
            with open(pres_rels_path, "wb") as fh:
                fh.write(rels_dom.toxml(encoding="utf-8"))
    return removed


def purge_trash_folder(unpacked_dir: Path) -> list[str]:
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
    referenced: set = set()
    slides_rels_dir = unpacked_dir / "ppt" / "slides" / "_rels"
    if not slides_rels_dir.exists():
        return referenced
    for rels_file in slides_rels_dir.glob("*.rels"):
        dom = _minidom.parse(str(rels_file))
        for rel_elem in _elements_by_localname(dom, "Relationship"):
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
    referenced: set = set()
    for rels_file in unpacked_dir.rglob("*.rels"):
        dom = _minidom.parse(str(rels_file))
        for rel_elem in _elements_by_localname(dom, "Relationship"):
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
    ct_path = unpacked_dir / "[Content_Types].xml"
    if not ct_path.exists():
        return
    dom = _minidom.parse(str(ct_path))
    modified = False
    for override in list(_elements_by_localname(dom, "Override")):
        part_name = override.getAttribute("PartName").lstrip("/")
        if part_name in removed_files and override.parentNode:
            override.parentNode.removeChild(override)
            modified = True
    if modified:
        with open(ct_path, "wb") as fh:
            fh.write(dom.toxml(encoding="utf-8"))


def clean_unused_files(unpacked_dir: Path) -> list[str]:
    all_removed: list[str] = []
    all_removed.extend(remove_orphaned_slides(unpacked_dir))
    all_removed.extend(purge_trash_folder(unpacked_dir))
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
        print("Usage: python scripts/clean.py <unpacked_dir>", file=sys.stderr)
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
