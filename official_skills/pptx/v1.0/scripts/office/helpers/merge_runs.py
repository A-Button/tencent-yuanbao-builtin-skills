"""合并 DOCX 中格式相同的相邻 run 节点。

将具有相同 <w:rPr> 属性的相邻 <w:r> 元素合并为一个。
既处理段落中的 run，也处理修订标记（<w:ins>、<w:del>）内部的 run。

额外操作：
- 删除 run 上的 rsid 属性（修订元数据，不影响渲染效果）
- 删除 proofErr 元素（拼写/语法标记，会阻碍合并）
"""

from pathlib import Path

import defusedxml.minidom


def merge_runs(input_dir: str) -> tuple[int, str]:
    xml_path = Path(input_dir) / "word" / "document.xml"

    if not xml_path.exists():
        return 0, f"Error: {xml_path} not found"

    try:
        document = defusedxml.minidom.parseString(xml_path.read_text(encoding="utf-8"))
        doc_root = document.documentElement

        _delete_elements(doc_root, "proofErr")
        _remove_rsid_attributes(doc_root)

        parent_nodes = {r.parentNode for r in _collect_elements(doc_root, "r")}

        total_merged = 0
        for parent in parent_nodes:
            total_merged += _merge_adjacent_runs(parent)

        xml_path.write_bytes(document.toxml(encoding="UTF-8"))
        return total_merged, f"Merged {total_merged} runs"

    except Exception as exc:
        return 0, f"Error: {exc}"


def _collect_elements(start_node, local_tag: str) -> list:
    found = []

    def _walk(nd):
        if nd.nodeType == nd.ELEMENT_NODE:
            tag_name = nd.localName or nd.tagName
            if tag_name == local_tag or tag_name.endswith(f":{local_tag}"):
                found.append(nd)
            for ch in nd.childNodes:
                _walk(ch)

    _walk(start_node)
    return found


def _first_child_by_tag(parent_node, local_tag: str):
    for ch in parent_node.childNodes:
        if ch.nodeType == ch.ELEMENT_NODE:
            tag_name = ch.localName or ch.tagName
            if tag_name == local_tag or tag_name.endswith(f":{local_tag}"):
                return ch
    return None


def _children_by_tag(parent_node, local_tag: str) -> list:
    matched = []
    for ch in parent_node.childNodes:
        if ch.nodeType == ch.ELEMENT_NODE:
            tag_name = ch.localName or ch.tagName
            if tag_name == local_tag or tag_name.endswith(f":{local_tag}"):
                matched.append(ch)
    return matched


def _elements_are_adjacent(first, second) -> bool:
    cursor = first.nextSibling
    while cursor:
        if cursor == second:
            return True
        if cursor.nodeType == cursor.ELEMENT_NODE:
            return False
        if cursor.nodeType == cursor.TEXT_NODE and cursor.data.strip():
            return False
        cursor = cursor.nextSibling
    return False


def _delete_elements(root_node, local_tag: str):
    for el in _collect_elements(root_node, local_tag):
        if el.parentNode:
            el.parentNode.removeChild(el)


def _remove_rsid_attributes(root_node):
    for r in _collect_elements(root_node, "r"):
        for a in list(r.attributes.values()):
            if "rsid" in a.name.lower():
                r.removeAttribute(a.name)


def _merge_adjacent_runs(parent_node) -> int:
    merged_count = 0
    current_run = _get_first_run(parent_node)

    while current_run:
        while True:
            following = _following_element(current_run)
            if following and _check_is_run(following) and _runs_are_mergeable(current_run, following):
                _transfer_run_children(current_run, following)
                parent_node.removeChild(following)
                merged_count += 1
            else:
                break

        _unify_text_nodes(current_run)
        current_run = _following_run(current_run)

    return merged_count


def _get_first_run(parent_node):
    for ch in parent_node.childNodes:
        if ch.nodeType == ch.ELEMENT_NODE and _check_is_run(ch):
            return ch
    return None


def _following_element(node):
    sib = node.nextSibling
    while sib:
        if sib.nodeType == sib.ELEMENT_NODE:
            return sib
        sib = sib.nextSibling
    return None


def _following_run(node):
    sib = node.nextSibling
    while sib:
        if sib.nodeType == sib.ELEMENT_NODE:
            if _check_is_run(sib):
                return sib
        sib = sib.nextSibling
    return None


def _check_is_run(node) -> bool:
    tag_name = node.localName or node.tagName
    return tag_name == "r" or tag_name.endswith(":r")


def _runs_are_mergeable(run_a, run_b) -> bool:
    props_a = _first_child_by_tag(run_a, "rPr")
    props_b = _first_child_by_tag(run_b, "rPr")

    if (props_a is None) != (props_b is None):
        return False
    if props_a is None:
        return True
    return props_a.toxml() == props_b.toxml()


def _transfer_run_children(dest, src):
    for ch in list(src.childNodes):
        if ch.nodeType == ch.ELEMENT_NODE:
            tag_name = ch.localName or ch.tagName
            if tag_name != "rPr" and not tag_name.endswith(":rPr"):
                dest.appendChild(ch)


def _unify_text_nodes(run_node):
    t_nodes = _children_by_tag(run_node, "t")

    for idx in range(len(t_nodes) - 1, 0, -1):
        later, earlier = t_nodes[idx], t_nodes[idx - 1]

        if _elements_are_adjacent(earlier, later):
            text_before = earlier.firstChild.data if earlier.firstChild else ""
            text_after = later.firstChild.data if later.firstChild else ""
            combined = text_before + text_after

            if earlier.firstChild:
                earlier.firstChild.data = combined
            else:
                earlier.appendChild(run_node.ownerDocument.createTextNode(combined))

            if combined.startswith(" ") or combined.endswith(" "):
                earlier.setAttribute("xml:space", "preserve")
            elif earlier.hasAttribute("xml:space"):
                earlier.removeAttribute("xml:space")

            run_node.removeChild(later)
