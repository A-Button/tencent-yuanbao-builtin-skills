"""批注（comments）helper。

python-docx 也不覆盖批注。我们直接管理四个 part：
- `word/comments.xml`               `<w:comments>` 的正文
- `word/commentsExtended.xml`       `<w15:commentEx>`，负责回复链（paraIdParent）
- `word/commentsIds.xml`            `<w16cid:commentId>`，稳定标识
- `word/commentsExtensible.xml`     `<w16cex:commentExtensible>`，扩展元数据

四个 part 会在首次调用 `add_comment` 时按需 provision：从
`skills/docx/scripts/templates/*.xml` 拷贝原始骨架（复用现成的 mc:Ignorable
声明），再交给 `XmlPart` 承载。`[Content_Types].xml` 与 `word/_rels/document.xml.rels`
由 python-docx 在 `doc.save()` 时根据 `relate_to()` 自动写入。
"""

from __future__ import annotations

from pathlib import Path

from docx.opc.packuri import PackURI
from docx.opc.part import XmlPart
from docx.oxml import OxmlElement, parse_xml
from lxml import etree

from .ooxml import hex_id_8, next_comment_id, now_utc_z, qn, set_text_with_preserve

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"

_COMMENT_PARTS = [
    (
        "comments.xml",
        "http://schemas.openxmlformats.org/officeDocument/2006/relationships/comments",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml",
    ),
    (
        "commentsExtended.xml",
        "http://schemas.microsoft.com/office/2011/relationships/commentsExtended",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtended+xml",
    ),
    (
        "commentsIds.xml",
        "http://schemas.microsoft.com/office/2016/09/relationships/commentsIds",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsIds+xml",
    ),
    (
        "commentsExtensible.xml",
        "http://schemas.microsoft.com/office/2018/08/relationships/commentsExtensible",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.commentsExtensible+xml",
    ),
]


def _find_part(doc, partname: str):
    for p in doc.part.package.iter_parts():
        if str(p.partname) == partname:
            return p
    return None


def _get_element(part):
    """拿到 part 的 lxml 根元素，兼容 XmlPart（有 .element）与普通 Part（只有 blob）。

    普通 Part（如加载自现存文档的 commentsExtended/Ids/Extensible）没有 `.element`
    属性；这里把解析结果缓存在 `part._docxlib_element` 上，后续调用复用同一个
    lxml 树，并在 `_flush_element` 时把变更写回 `part._blob`。
    """
    if hasattr(part, "element") and part.element is not None:
        return part.element
    cached = getattr(part, "_docxlib_element", None)
    if cached is not None:
        return cached
    blob = part.blob
    element = etree.fromstring(blob)
    part._docxlib_element = element
    return element


def _flush_element(part) -> None:
    """把可能被 mutation 过的 lxml 元素序列化回 part._blob。

    XmlPart 会在 save 时自己重新序列化 element，什么也不用做；普通 Part 需要
    手动同步。
    """
    if hasattr(part, "element") and getattr(part, "element", None) is not None:
        return
    element = getattr(part, "_docxlib_element", None)
    if element is None:
        return
    part._blob = etree.tostring(element, xml_declaration=True, encoding="UTF-8", standalone=True)


def _ensure_comment_parts(doc, templates_dir: Path = _TEMPLATE_DIR) -> None:
    """幂等地补齐四个 comments part。已存在则跳过。"""
    for fname, rel_type, ct in _COMMENT_PARTS:
        uri = f"/word/{fname}"
        if _find_part(doc, uri) is not None:
            continue
        blob = (templates_dir / fname).read_bytes()
        element = parse_xml(blob)
        part = XmlPart(PackURI(uri), ct, element, doc.part.package)
        doc.part.relate_to(part, rel_type)


def _resolve_anchor(anchor):
    """接收 Paragraph 或 Run，返回 (paragraph_element, insert_before_index, insert_after_index)。

    - Paragraph：range 覆盖整段所有 run（`<w:pPr>` 之后到段末）
    - Run：range 只覆盖这一个 run
    """
    if hasattr(anchor, "_r"):
        r = anchor._r
        p = r.getparent()
        idx = list(p).index(r)
        return p, idx, idx + 1
    if hasattr(anchor, "_p"):
        p = anchor._p
        # 找 pPr 之后的第一个索引
        children = list(p)
        start = 0
        for i, c in enumerate(children):
            if c.tag != qn("w:pPr"):
                start = i
                break
        else:
            start = len(children)
        return p, start, len(children)
    raise TypeError(f"anchor 必须是 python-docx Paragraph 或 Run，收到 {type(anchor).__name__}")


def _build_comment_xml(comment_id: int, author: str, initials: str, text: str, para_id: str):
    return f"""
<w:comment xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
           xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"
           w:id="{comment_id}" w:author="{author}" w:date="{now_utc_z()}" w:initials="{initials}">
  <w:p w14:paraId="{para_id}" w14:textId="77777777">
    <w:r>
      <w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>
      <w:annotationRef/>
    </w:r>
    <w:r>
      <w:rPr>
        <w:rFonts w:ascii="Source Han Sans SC" w:hAnsi="Source Han Sans SC"
                  w:eastAsia="思源黑体" w:cs="Source Han Sans SC"/>
        <w:color w:val="000000"/>
        <w:sz w:val="20"/>
        <w:szCs w:val="20"/>
      </w:rPr>
      <w:t>{text}</w:t>
    </w:r>
  </w:p>
</w:comment>
""".strip()


def _append_from_snippet(root_element, snippet_xml: str) -> None:
    """把 snippet（一段 XML）作为子元素挂到 root_element 下。"""
    frag = etree.fromstring(snippet_xml)
    root_element.append(frag)


def add_comment(
    doc,
    anchor,
    text: str,
    *,
    author: str = "元宝",
    initials: str = "Y",
    comment_id: int | None = None,
    templates_dir: Path = _TEMPLATE_DIR,
) -> int:
    """给 anchor（Paragraph 或 Run）添加一条批注。

    自动完成：
    - 首次使用时 provision 四个 comments part
    - 在 anchor 前后插入 `<w:commentRangeStart>` / `<w:commentRangeEnd>` + `<w:commentReference>`
      标记（都是 `<w:p>` 的直接子元素，不会嵌到 `<w:r>` 里）
    - 追加 `<w:comment>` / `<w15:commentEx>` / `<w16cid:commentId>` / `<w16cex:commentExtensible>`

    返回本条批注的整数 id（`comment_id` 为 None 时自动取当前 comments.xml 内的最小可用值）。
    """
    _ensure_comment_parts(doc, templates_dir)

    p, before_idx, after_idx = _resolve_anchor(anchor)

    comments_part = _find_part(doc, "/word/comments.xml")
    ext_part = _find_part(doc, "/word/commentsExtended.xml")
    ids_part = _find_part(doc, "/word/commentsIds.xml")
    cex_part = _find_part(doc, "/word/commentsExtensible.xml")

    comments_root = _get_element(comments_part)
    ext_root = _get_element(ext_part)
    ids_root = _get_element(ids_part)
    cex_root = _get_element(cex_part)

    if comment_id is None:
        comment_id = next_comment_id(comments_root)

    para_id = hex_id_8()
    durable_id = hex_id_8()

    # 1) 追加 <w:comment>
    _append_from_snippet(
        comments_root, _build_comment_xml(comment_id, author, initials, text, para_id)
    )

    # 2) commentsExtended.xml：无 parent 时只标 done=0
    ext_snippet = (
        f'<w15:commentEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"'
        f' w15:paraId="{para_id}" w15:done="0"/>'
    )
    _append_from_snippet(ext_root, ext_snippet)

    # 3) commentsIds.xml
    ids_snippet = (
        f'<w16cid:commentId xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid"'
        f' w16cid:paraId="{para_id}" w16cid:durableId="{durable_id}"/>'
    )
    _append_from_snippet(ids_root, ids_snippet)

    # 4) commentsExtensible.xml
    cex_snippet = (
        f'<w16cex:commentExtensible xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex"'
        f' w16cex:durableId="{durable_id}" w16cex:dateUtc="{now_utc_z()}"/>'
    )
    _append_from_snippet(cex_root, cex_snippet)

    # 5) 在段落里插入 range markers + reference
    range_start = OxmlElement("w:commentRangeStart")
    range_start.set(qn("w:id"), str(comment_id))
    range_end = OxmlElement("w:commentRangeEnd")
    range_end.set(qn("w:id"), str(comment_id))
    ref_run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    rstyle = OxmlElement("w:rStyle")
    rstyle.set(qn("w:val"), "CommentReference")
    rpr.append(rstyle)
    ref_run.append(rpr)
    ref = OxmlElement("w:commentReference")
    ref.set(qn("w:id"), str(comment_id))
    ref_run.append(ref)

    p.insert(before_idx, range_start)
    p.insert(after_idx + 1, range_end)
    p.insert(after_idx + 2, ref_run)

    # 把 mutation 冲刷回普通 Part 的 blob（XmlPart 无操作）
    for part in (comments_part, ext_part, ids_part, cex_part):
        _flush_element(part)

    return comment_id


def reply_comment(
    doc,
    parent_id: int,
    text: str,
    *,
    author: str = "元宝",
    initials: str = "Y",
    comment_id: int | None = None,
    templates_dir: Path = _TEMPLATE_DIR,
) -> int:
    """给已有批注 parent_id 追加一条回复。

    产出结构与 `add_comment` 类似，但：
    - `commentsExtended.xml` 里的新条目会带 `w15:paraIdParent`，指向父批注的 `w14:paraId`
    - 在 document.xml 中，回复的 `<w:commentRangeStart/End>` 需要**嵌套**在父批注的
      range 之内；我们通过找到父批注的 range 并在其内部相同位置插入完成

    返回新批注的整数 id。
    """
    _ensure_comment_parts(doc, templates_dir)

    comments_part = _find_part(doc, "/word/comments.xml")
    ext_part = _find_part(doc, "/word/commentsExtended.xml")
    ids_part = _find_part(doc, "/word/commentsIds.xml")
    cex_part = _find_part(doc, "/word/commentsExtensible.xml")

    comments_root = _get_element(comments_part)
    ext_root = _get_element(ext_part)
    ids_root = _get_element(ids_part)
    cex_root = _get_element(cex_part)

    # 找父批注的 paraId
    parent_para_id = None
    for c in comments_root.iter(qn("w:comment")):
        if c.get(qn("w:id")) == str(parent_id):
            first_p = c.find(qn("w:p"))
            if first_p is not None:
                parent_para_id = first_p.get(qn("w14:paraId"))
            break
    if parent_para_id is None:
        raise ValueError(f"父批注 {parent_id} 不存在或缺少 paraId")

    if comment_id is None:
        comment_id = next_comment_id(comments_root)

    para_id = hex_id_8()
    durable_id = hex_id_8()

    _append_from_snippet(
        comments_root, _build_comment_xml(comment_id, author, initials, text, para_id)
    )

    ext_snippet = (
        f'<w15:commentEx xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"'
        f' w15:paraId="{para_id}" w15:paraIdParent="{parent_para_id}" w15:done="0"/>'
    )
    _append_from_snippet(ext_root, ext_snippet)

    ids_snippet = (
        f'<w16cid:commentId xmlns:w16cid="http://schemas.microsoft.com/office/word/2016/wordml/cid"'
        f' w16cid:paraId="{para_id}" w16cid:durableId="{durable_id}"/>'
    )
    _append_from_snippet(ids_root, ids_snippet)

    cex_snippet = (
        f'<w16cex:commentExtensible xmlns:w16cex="http://schemas.microsoft.com/office/word/2018/wordml/cex"'
        f' w16cex:durableId="{durable_id}" w16cex:dateUtc="{now_utc_z()}"/>'
    )
    _append_from_snippet(cex_root, cex_snippet)

    # 在父批注的 rangeStart 之后、rangeEnd 之前嵌套一对新 range + 一个 reference run
    doc_root = doc.part.element
    parent_start = None
    parent_end = None
    for elem in doc_root.iter(qn("w:commentRangeStart")):
        if elem.get(qn("w:id")) == str(parent_id):
            parent_start = elem
            break
    for elem in doc_root.iter(qn("w:commentRangeEnd")):
        if elem.get(qn("w:id")) == str(parent_id):
            parent_end = elem
            break
    if parent_start is None or parent_end is None:
        raise ValueError(f"父批注 {parent_id} 在 document.xml 中缺 range 标记")

    parent_p = parent_start.getparent()
    end_p = parent_end.getparent()
    if parent_p is not end_p:
        # 罕见：父批注 range 跨段落。放到父 rangeStart 所在段落尾部作为兜底。
        end_p = parent_p

    start_idx = list(parent_p).index(parent_start) + 1
    end_idx = list(end_p).index(parent_end)

    child_start = OxmlElement("w:commentRangeStart")
    child_start.set(qn("w:id"), str(comment_id))
    child_end = OxmlElement("w:commentRangeEnd")
    child_end.set(qn("w:id"), str(comment_id))
    ref_run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    rstyle = OxmlElement("w:rStyle")
    rstyle.set(qn("w:val"), "CommentReference")
    rpr.append(rstyle)
    ref_run.append(rpr)
    ref = OxmlElement("w:commentReference")
    ref.set(qn("w:id"), str(comment_id))
    ref_run.append(ref)

    parent_p.insert(start_idx, child_start)
    end_p.insert(end_idx, child_end)
    end_p.insert(end_idx + 1, ref_run)

    for part in (comments_part, ext_part, ids_part, cex_part):
        _flush_element(part)

    return comment_id
