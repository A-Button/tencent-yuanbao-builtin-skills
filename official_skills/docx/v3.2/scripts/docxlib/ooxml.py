"""OOXML 命名空间、qn() 扩展、ID 生成器和小工具。

`docx.oxml.ns.qn` 只认识 python-docx 内建的 prefix，不覆盖 `w14/w15/w16cid/w16cex`
等追踪修订/批注需要的现代 word 命名空间。这里把 NS 表和 qn() 补齐。
"""

from __future__ import annotations

import random
from datetime import datetime, timezone

from lxml import etree

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "xml": "http://www.w3.org/XML/1998/namespace",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}


def qn(clark: str) -> str:
    """把 `w:ins` 之类的前缀名转成 lxml 用的 Clark notation `{ns}ins`。

    支持 NS 表里所有前缀；`xml:space` 会走标准 XML 命名空间。
    """
    if ":" not in clark:
        return clark
    prefix, local = clark.split(":", 1)
    if prefix not in NS:
        raise KeyError(f"未登记的命名空间前缀：{prefix}")
    return f"{{{NS[prefix]}}}{local}"


def now_utc_z() -> str:
    """返回 OOXML 追踪修订/批注需要的 UTC 时间字符串（Z 后缀，秒级）。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def hex_id_8() -> str:
    """生成 `paraId`、`durableId` 用的 8 位十六进制大写字符串。

    随机范围 `[1, 0x7FFFFFFE]`，同时满足 `paraId < 0x80000000` 与
    `durableId < 0x7FFFFFFF` 的校验约束（见 `validators/docx.py`）。
    """
    return f"{random.randint(1, 0x7FFFFFFE):08X}"


def next_ins_del_id(doc_root) -> int:
    """扫描整份文档的 `w:ins/@w:id`、`w:del/@w:id`，返回下一个可用整数 id。"""
    used = _collect_ids(doc_root, [qn("w:ins"), qn("w:del")], qn("w:id"))
    return (max(used) + 1) if used else 1


def next_comment_id(comments_root) -> int:
    """扫 comments.xml 里所有 `w:comment/@w:id`，返回下一个可用整数 id。"""
    used = _collect_ids(comments_root, [qn("w:comment")], qn("w:id"))
    if used:
        return max(used) + 1
    return 0  # word 里第一条批注约定 id=0


def _collect_ids(root, tags: list[str], attr: str) -> list[int]:
    ids: list[int] = []
    for tag in tags:
        for elem in root.iter(tag):
            val = elem.get(attr)
            if val is None:
                continue
            try:
                ids.append(int(val))
            except ValueError:
                pass
    return ids


def needs_xml_space_preserve(text: str) -> bool:
    """text 首尾有空白（空格/制表符/换行）时返回 True，需要 xml:space='preserve'。"""
    return bool(text) and (text[0] in " \t\n\r" or text[-1] in " \t\n\r")


def set_text_with_preserve(t_elem, text: str) -> None:
    """给 `<w:t>` 或 `<w:delText>` 元素填 text，必要时补 xml:space='preserve'。

    OOXML 规范要求：`<w:t>` 首尾含空白时必须显式加 `xml:space="preserve"`，
    否则接受修订/接受后消失。`DOCXSchemaValidator.validate_whitespace_preservation`
    会因此报错，所以库里所有 `<w:t>` / `<w:delText>` 都走这个 helper。
    """
    t_elem.text = text
    if needs_xml_space_preserve(text):
        t_elem.set(qn("xml:space"), "preserve")


def convert_t_to_deltext(elem) -> None:
    """把某个子树里所有 `<w:t>` 改成 `<w:delText>`、`<w:instrText>` 改成 `<w:delInstrText>`。

    `<w:del>` 内不允许出现 `<w:t>` / `<w:instrText>`（`validate_deletions` 硬断），
    所以往 `<w:del>` 里 wrap 已有内容时要跑这个转换。
    """
    for t in elem.iter(qn("w:t")):
        t.tag = qn("w:delText")
    for it in elem.iter(qn("w:instrText")):
        it.tag = qn("w:delInstrText")


def convert_deltext_to_t(elem) -> None:
    """反向：把子树里所有 `<w:delText>` 转回 `<w:t>`。

    `<w:ins>` 内不允许出现 `<w:delText>`（`validate_insertions` 硬断），
    所以从 `<w:del>` 复制内容到 `<w:ins>` 时要跑这个转换。
    """
    for t in elem.iter(qn("w:delText")):
        t.tag = qn("w:t")
    for it in elem.iter(qn("w:delInstrText")):
        it.tag = qn("w:instrText")


def ensure_child_order(parent, order: list[str]) -> None:
    """确保 parent 直接子元素按 `order` 里的 tag 顺序排列，未列出的保持相对顺序。

    专门给 `<w:pPr>` 用：`pStyle → numPr → spacing → ind → jc → rPr`。
    OOXML XSD 强制这个顺序，随意 append 会挂 schema 校验。
    """
    priority = {tag: i for i, tag in enumerate(order)}
    fallback = len(order)
    children = list(parent)
    children.sort(key=lambda c: priority.get(c.tag, fallback))
    for child in children:
        parent.append(child)
