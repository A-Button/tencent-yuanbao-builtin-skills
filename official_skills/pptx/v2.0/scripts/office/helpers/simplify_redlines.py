"""简化修订标记：合并相邻的同类型追踪变更元素。

将来自同一作者的相邻 <w:ins> 元素合并为单个元素，<w:del> 同理。
这样可以减少大量修订标记的文档中追踪变更包装器的数量，使文档更易处理。

合并规则：
- 仅合并同类型元素（w:ins 对 w:ins，w:del 对 w:del）
- 仅在作者相同时合并（忽略时间戳差异）
- 仅在真正相邻时合并（中间只允许存在空白文本节点）
"""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import defusedxml.minidom

WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def simplify_redlines(input_dir: str) -> tuple[int, str]:
    doc_xml = Path(input_dir) / "word" / "document.xml"

    if not doc_xml.exists():
        return 0, f"Error: {doc_xml} not found"

    try:
        raw_xml = doc_xml.read_text(encoding="utf-8")
        dom = defusedxml.minidom.parseString(raw_xml)
        root_element = dom.documentElement

        merged = 0

        targets = _collect_elements(root_element, "p") + _collect_elements(
            root_element, "tc"
        )

        for target in targets:
            merged += _consolidate_tracked_changes(target, "ins")
            merged += _consolidate_tracked_changes(target, "del")

        doc_xml.write_bytes(dom.toxml(encoding="UTF-8"))
        return merged, f"Simplified {merged} tracked changes"

    except Exception as e:
        return 0, f"Error: {e}"


def _consolidate_tracked_changes(container, tag: str) -> int:
    tracked_nodes = [
        c
        for c in container.childNodes
        if c.nodeType == c.ELEMENT_NODE and _matches_tag(c, tag)
    ]

    if len(tracked_nodes) < 2:
        return 0

    count = 0
    idx = 0
    while idx < len(tracked_nodes) - 1:
        current = tracked_nodes[idx]
        following = tracked_nodes[idx + 1]

        if _is_mergeable_tracked_change(current, following):
            _transfer_tracked_children(current, following)
            container.removeChild(following)
            tracked_nodes.pop(idx + 1)
            count += 1
        else:
            idx += 1

    return count


def _matches_tag(node, tag: str) -> bool:
    local = node.localName or node.tagName
    return local == tag or local.endswith(f":{tag}")


def _read_author_attr(elem) -> str:
    val = elem.getAttribute("w:author")
    if not val:
        for attr in elem.attributes.values():
            if attr.localName == "author" or attr.name.endswith(":author"):
                return attr.value
    return val


def _is_mergeable_tracked_change(first, second) -> bool:
    if _read_author_attr(first) != _read_author_attr(second):
        return False

    sibling = first.nextSibling
    while sibling is not None and sibling != second:
        if sibling.nodeType == sibling.ELEMENT_NODE:
            return False
        if sibling.nodeType == sibling.TEXT_NODE and sibling.data.strip():
            return False
        sibling = sibling.nextSibling

    return True


def _transfer_tracked_children(dest, src):
    while src.firstChild:
        node = src.firstChild
        src.removeChild(node)
        dest.appendChild(node)


def _collect_elements(root, tag: str) -> list:
    found: list = []

    def _walk(node):
        if node.nodeType == node.ELEMENT_NODE:
            local = node.localName or node.tagName
            if local == tag or local.endswith(f":{tag}"):
                found.append(node)
            for child in node.childNodes:
                _walk(child)

    _walk(root)
    return found


def get_tracked_change_authors(doc_xml_path: Path) -> dict[str, int]:
    if not doc_xml_path.exists():
        return {}

    try:
        tree = ET.parse(doc_xml_path)
        root = tree.getroot()
    except ET.ParseError:
        return {}

    ns = {"w": WORD_NS}
    author_key = f"{{{WORD_NS}}}author"

    authors: dict[str, int] = {}
    for kind in ("ins", "del"):
        for elem in root.findall(f".//w:{kind}", ns):
            name = elem.get(author_key)
            if name:
                authors[name] = authors.get(name, 0) + 1

    return authors


def _extract_authors_from_docx(docx_path: Path) -> dict[str, int]:
    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return {}
            with zf.open("word/document.xml") as f:
                tree = ET.parse(f)
                root = tree.getroot()

                ns = {"w": WORD_NS}
                author_key = f"{{{WORD_NS}}}author"

                authors: dict[str, int] = {}
                for kind in ("ins", "del"):
                    for elem in root.findall(f".//w:{kind}", ns):
                        name = elem.get(author_key)
                        if name:
                            authors[name] = authors.get(name, 0) + 1
                return authors
    except (zipfile.BadZipFile, ET.ParseError):
        return {}


def infer_author(modified_dir: Path, original_docx: Path, default: str = "yuanbao") -> str:
    modified_xml = modified_dir / "word" / "document.xml"
    modified_authors = get_tracked_change_authors(modified_xml)

    if not modified_authors:
        return default

    original_authors = _extract_authors_from_docx(original_docx)

    new_changes: dict[str, int] = {}
    for author, count in modified_authors.items():
        baseline = original_authors.get(author, 0)
        delta = count - baseline
        if delta > 0:
            new_changes[author] = delta

    if not new_changes:
        return default

    if len(new_changes) == 1:
        return next(iter(new_changes))

    raise ValueError(
        f"Multiple authors added new changes: {new_changes}. "
        "Cannot infer which author to validate."
    )
