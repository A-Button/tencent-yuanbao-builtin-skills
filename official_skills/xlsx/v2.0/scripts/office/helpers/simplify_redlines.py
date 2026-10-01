"""通过合并相邻的 w:ins 或 w:del 元素来简化修订标记。

将来自同一作者的相邻 <w:ins> 元素合并为一个元素，
<w:del> 元素同理。这使得大量修订的文档更易于处理。

规则：
- 仅合并同类型元素（w:ins 与 w:ins，w:del 与 w:del）
- 仅在同一作者时合并（忽略时间戳差异）
- 仅在真正相邻时合并（中间仅有空白字符）
"""

import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import defusedxml.minidom

_WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def simplify_redlines(input_dir: str) -> tuple[int, str]:
    doc_xml = Path(input_dir) / "word" / "document.xml"

    if not doc_xml.exists():
        return 0, f"Error: {doc_xml} not found"

    try:
        dom = defusedxml.minidom.parseString(doc_xml.read_text(encoding="utf-8"))
        root = dom.documentElement

        total = 0
        for container in _find_elements(root, "p") + _find_elements(root, "tc"):
            total += _merge_tracked_changes_in(container, "ins")
            total += _merge_tracked_changes_in(container, "del")

        doc_xml.write_bytes(dom.toxml(encoding="UTF-8"))
        return total, f"Simplified {total} tracked changes"

    except Exception as e:
        return 0, f"Error: {e}"


def _merge_tracked_changes_in(container, tag: str) -> int:
    tracked = [
        child for child in container.childNodes
        if child.nodeType == child.ELEMENT_NODE and _is_element(child, tag)
    ]

    if len(tracked) < 2:
        return 0

    count = 0
    i = 0
    while i < len(tracked) - 1:
        curr = tracked[i]
        nxt = tracked[i + 1]

        if _can_merge_tracked(curr, nxt):
            _merge_tracked_content(curr, nxt)
            container.removeChild(nxt)
            tracked.pop(i + 1)
            count += 1
        else:
            i += 1

    return count


def _is_element(node, tag: str) -> bool:
    name = node.localName or node.tagName
    return name == tag or name.endswith(f":{tag}")


def _get_author(elem) -> str:
    author = elem.getAttribute("w:author")
    if not author:
        for attr in elem.attributes.values():
            if attr.localName == "author" or attr.name.endswith(":author"):
                return attr.value
    return author


def _can_merge_tracked(elem1, elem2) -> bool:
    if _get_author(elem1) != _get_author(elem2):
        return False

    node = elem1.nextSibling
    while node and node != elem2:
        if node.nodeType == node.ELEMENT_NODE:
            return False
        if node.nodeType == node.TEXT_NODE and node.data.strip():
            return False
        node = node.nextSibling

    return True


def _merge_tracked_content(target, source):
    while source.firstChild:
        child = source.firstChild
        source.removeChild(child)
        target.appendChild(child)


def _find_elements(root, tag: str) -> list:
    results = []

    def walk(node):
        if node.nodeType == node.ELEMENT_NODE:
            name = node.localName or node.tagName
            if name == tag or name.endswith(f":{tag}"):
                results.append(node)
            for child in node.childNodes:
                walk(child)

    walk(root)
    return results


def get_tracked_change_authors(doc_xml_path: Path) -> dict[str, int]:
    if not doc_xml_path.exists():
        return {}

    try:
        tree = ET.parse(doc_xml_path)
        root = tree.getroot()
    except ET.ParseError:
        return {}

    ns = {"w": _WORD_NS}
    author_attr = f"{{{_WORD_NS}}}author"

    authors: dict[str, int] = {}
    for tag in ("ins", "del"):
        for elem in root.findall(f".//w:{tag}", ns):
            author = elem.get(author_attr)
            if author:
                authors[author] = authors.get(author, 0) + 1

    return authors


def _get_authors_from_docx(docx_path: Path) -> dict[str, int]:
    try:
        with zipfile.ZipFile(docx_path, "r") as zf:
            if "word/document.xml" not in zf.namelist():
                return {}
            with zf.open("word/document.xml") as f:
                tree = ET.parse(f)
                root = tree.getroot()

                ns = {"w": _WORD_NS}
                author_attr = f"{{{_WORD_NS}}}author"

                authors: dict[str, int] = {}
                for tag in ("ins", "del"):
                    for elem in root.findall(f".//w:{tag}", ns):
                        author = elem.get(author_attr)
                        if author:
                            authors[author] = authors.get(author, 0) + 1
                return authors
    except (zipfile.BadZipFile, ET.ParseError):
        return {}


def infer_author(modified_dir: Path, original_docx: Path, default: str = "Assistant") -> str:
    modified_xml = modified_dir / "word" / "document.xml"
    modified_authors = get_tracked_change_authors(modified_xml)

    if not modified_authors:
        return default

    original_authors = _get_authors_from_docx(original_docx)

    new_changes: dict[str, int] = {}
    for author, count in modified_authors.items():
        diff = count - original_authors.get(author, 0)
        if diff > 0:
            new_changes[author] = diff

    if not new_changes:
        return default

    if len(new_changes) == 1:
        return next(iter(new_changes))

    raise ValueError(
        f"Multiple authors added new changes: {new_changes}. "
        "Cannot infer which author to validate."
    )
