"""追踪修订（tracked changes）helper。

python-docx 完全不覆盖追踪修订，全部通过 `paragraph._p` 下探到 lxml 完成。所有
helper 都产生 `DOCXSchemaValidator` / `RedliningValidator` 期望的 XML：
- `<w:del>` 内一律用 `<w:delText>` / `<w:delInstrText>`
- `<w:ins>` 内不允许 `<w:delText>`
- 整段删除时段落符本身 (`<w:pPr><w:rPr><w:del/>`) 也要标记
- 首尾含空白的文本节点补 `xml:space="preserve"`
- `<w:pPr>` 子元素顺序：`pStyle → numPr → spacing → ind → jc → rPr`
"""

from __future__ import annotations

from copy import deepcopy

from docx.oxml import OxmlElement
from lxml import etree

from .ooxml import (
    convert_deltext_to_t,
    convert_t_to_deltext,
    ensure_child_order,
    next_ins_del_id,
    now_utc_z,
    qn,
    set_text_with_preserve,
)

_PPR_ORDER = [
    qn("w:pStyle"),
    qn("w:numPr"),
    qn("w:pBdr"),
    qn("w:shd"),
    qn("w:tabs"),
    qn("w:spacing"),
    qn("w:ind"),
    qn("w:jc"),
    qn("w:outlineLvl"),
    qn("w:rPr"),
]


def _doc_root(element_or_para):
    """从 python-docx Paragraph 或 lxml 元素上取到文档根 `w:document`。"""
    if hasattr(element_or_para, "_p"):
        return element_or_para._p.getroottree().getroot()
    return element_or_para.getroottree().getroot()


def _make_run(text: str, rpr_source=None):
    """构造一个 `<w:r><w:rPr>...</w:rPr><w:t>text</w:t></w:r>`。

    rpr_source 是可选的 lxml `<w:rPr>` 元素或含 rPr 的 run，深拷贝进新 run 用于
    保留原格式（粗体、字号、字体等）。
    """
    r = etree.Element(qn("w:r"))
    if rpr_source is not None:
        rpr = _extract_rpr(rpr_source)
        if rpr is not None:
            r.append(deepcopy(rpr))
    t = etree.SubElement(r, qn("w:t"))
    set_text_with_preserve(t, text)
    return r


def _extract_rpr(source):
    if source is None:
        return None
    if hasattr(source, "_r"):
        source = source._r
    if hasattr(source, "find"):
        rpr = source.find(qn("w:rPr"))
        if rpr is not None:
            return rpr
    if getattr(source, "tag", None) == qn("w:rPr"):
        return source
    return None


def insert_tracked(paragraph, text: str, *, author: str = "元宝", date: str | None = None,
                   rpr_source=None):
    """在 `paragraph` 末尾追加一个 `<w:ins>`，包住新文本。

    典型场景：在既有段落末尾加一句话（s03 也可用该 helper 实现追加）。
    返回新建的 `<w:ins>` lxml 元素。
    """
    p = paragraph._p if hasattr(paragraph, "_p") else paragraph
    ins = etree.SubElement(p, qn("w:ins"), {
        qn("w:id"): str(next_ins_del_id(_doc_root(p))),
        qn("w:author"): author,
        qn("w:date"): date or now_utc_z(),
    })
    ins.append(_make_run(text, rpr_source=rpr_source))
    return ins


def delete_tracked(paragraph, text: str, *, author: str = "元宝", date: str | None = None,
                   rpr_source=None):
    """在 `paragraph` 末尾追加一个 `<w:del>`，包住被删除的文本。

    仅当你手工构造 delete/insert 对时用；一般 `replace_run_text_with_tracked`
    或 `delete_paragraph_tracked` 更贴合业务。返回新建的 `<w:del>` 元素。
    """
    p = paragraph._p if hasattr(paragraph, "_p") else paragraph
    del_el = etree.SubElement(p, qn("w:del"), {
        qn("w:id"): str(next_ins_del_id(_doc_root(p))),
        qn("w:author"): author,
        qn("w:date"): date or now_utc_z(),
    })
    r = etree.SubElement(del_el, qn("w:r"))
    if rpr_source is not None:
        rpr = _extract_rpr(rpr_source)
        if rpr is not None:
            r.append(deepcopy(rpr))
    t = etree.SubElement(r, qn("w:delText"))
    set_text_with_preserve(t, text)
    return del_el


def replace_run_text_with_tracked(run, new_text: str, *, author: str = "元宝",
                                   date: str | None = None):
    """把整个 run 的文本用 tracked-changes 替换成 `new_text`。

    生成模式（假设旧 run 内容是 "30"、新文本是 "60"）：

        <w:r>期限为 </w:r>
        <w:del ...>
          <w:r>[原 rPr]<w:delText>30</w:delText></w:r>
        </w:del>
        <w:ins ...>
          <w:r>[原 rPr]<w:t>60</w:t></w:r>
        </w:ins>
        <w:r> 天。</w:r>

    原 run 从段落里剥出、原样塞进 `<w:del>`；新增内容放在紧邻的 `<w:ins>`。
    保留 rPr（粗体、字号、字体全部继承）。返回 `(del_element, ins_element)`。
    """
    r = run._r if hasattr(run, "_r") else run
    parent = r.getparent()
    if parent is None:
        raise ValueError("run 已从段落中脱离，无法定位插入点")

    date = date or now_utc_z()
    doc_root = _doc_root(r)
    del_id = str(next_ins_del_id(doc_root))
    ins_id = str(next_ins_del_id(doc_root))
    # 相邻 id 不能一样：ins 至少要比 del 大 1
    if ins_id == del_id:
        ins_id = str(int(del_id) + 1)

    del_el = etree.Element(qn("w:del"), {
        qn("w:id"): del_id, qn("w:author"): author, qn("w:date"): date,
    })
    ins_el = etree.Element(qn("w:ins"), {
        qn("w:id"): ins_id, qn("w:author"): author, qn("w:date"): date,
    })

    rpr_copy = deepcopy(r.find(qn("w:rPr"))) if r.find(qn("w:rPr")) is not None else None
    r_index = parent.index(r)
    parent.remove(r)
    del_el.append(r)
    convert_t_to_deltext(r)

    new_r = etree.Element(qn("w:r"))
    if rpr_copy is not None:
        new_r.append(deepcopy(rpr_copy))
    new_t = etree.SubElement(new_r, qn("w:t"))
    set_text_with_preserve(new_t, new_text)
    ins_el.append(new_r)

    parent.insert(r_index, del_el)
    parent.insert(r_index + 1, ins_el)
    return del_el, ins_el


def delete_paragraph_tracked(paragraph, *, author: str = "元宝", date: str | None = None):
    """以追踪修订方式删除整段（`<w:p>`）。

    步骤：
    1. 段落里每个 `<w:r>` 从原位剥出，套进新的 `<w:del>` 兄弟节点；`<w:t>` 转
       `<w:delText>`；同时也会 wrap 已有的其他兄弟（`<w:hyperlink>` 等）。
    2. 在 `<w:pPr><w:rPr>` 里加一个空的 `<w:del/>`，标记段落符本身被删除
       ——不然接受修订后会留一个空段。

    返回段落符 `<w:del/>` 元素。
    """
    p = paragraph._p if hasattr(paragraph, "_p") else paragraph
    date = date or now_utc_z()
    doc_root = _doc_root(p)

    # 段落里所有非 pPr / bookmark 类的直接子节点都要 wrap 进 del
    for child in list(p):
        if child.tag == qn("w:pPr"):
            continue
        if child.tag in {qn("w:bookmarkStart"), qn("w:bookmarkEnd")}:
            continue
        # 如果已经被 del 包着，就跳过
        if child.tag == qn("w:del"):
            continue
        del_el = etree.Element(qn("w:del"), {
            qn("w:id"): str(next_ins_del_id(doc_root)),
            qn("w:author"): author,
            qn("w:date"): date,
        })
        idx = p.index(child)
        p.remove(child)
        del_el.append(child)
        convert_t_to_deltext(del_el)
        p.insert(idx, del_el)

    # 段落符本身
    ppr = p.find(qn("w:pPr"))
    if ppr is None:
        ppr = etree.Element(qn("w:pPr"))
        p.insert(0, ppr)
    elif p.index(ppr) != 0:
        p.remove(ppr)
        p.insert(0, ppr)

    rpr = ppr.find(qn("w:rPr"))
    if rpr is None:
        rpr = etree.SubElement(ppr, qn("w:rPr"))

    para_del = rpr.find(qn("w:del"))
    if para_del is None:
        para_del = etree.SubElement(rpr, qn("w:del"))
    para_del.set(qn("w:id"), str(next_ins_del_id(doc_root)))
    para_del.set(qn("w:author"), author)
    para_del.set(qn("w:date"), date)

    ensure_child_order(ppr, _PPR_ORDER)
    return para_del


def reject_insertion(ins_element, *, author: str = "元宝", date: str | None = None):
    """拒绝其他作者的 `<w:ins>`：在里面每个 `<w:r>` 外嵌套一层我方 `<w:del>`。

    不修改原 `<w:ins>` 的 author。文本节点从 `<w:t>` 转成 `<w:delText>`。
    """
    date = date or now_utc_z()
    doc_root = _doc_root(ins_element)
    wrapped = []
    for r in list(ins_element.findall(qn("w:r"))):
        d = etree.Element(qn("w:del"), {
            qn("w:id"): str(next_ins_del_id(doc_root)),
            qn("w:author"): author,
            qn("w:date"): date,
        })
        idx = ins_element.index(r)
        ins_element.remove(r)
        d.append(r)
        convert_t_to_deltext(d)
        ins_element.insert(idx, d)
        wrapped.append(d)
    return wrapped


def restore_deletion(del_element, *, author: str = "元宝", date: str | None = None):
    """恢复其他作者的 `<w:del>`：在其之后追加一个兄弟 `<w:ins>` 承载相同文本。

    不修改原 `<w:del>` 的 author；把内部 `<w:r>` 深拷贝后从 `<w:delText>` 转回
    `<w:t>` 放进新 `<w:ins>`。返回新建的 `<w:ins>` 元素。
    """
    doc_root = _doc_root(del_element)
    ins = etree.Element(qn("w:ins"), {
        qn("w:id"): str(next_ins_del_id(doc_root)),
        qn("w:author"): author,
        qn("w:date"): date or now_utc_z(),
    })
    for r in del_element.findall(qn("w:r")):
        new_r = deepcopy(r)
        convert_deltext_to_t(new_r)
        ins.append(new_r)
    del_element.addnext(ins)
    return ins


def find_ins_by_author(doc, author: str) -> list:
    """遍历 `doc` 找出指定 author 的所有 `<w:ins>` 元素。"""
    root = doc.part.element if hasattr(doc, "part") else doc
    return [
        e for e in root.iter(qn("w:ins"))
        if e.get(qn("w:author")) == author
    ]


def find_del_by_author(doc, author: str) -> list:
    """遍历 `doc` 找出指定 author 的所有 `<w:del>` 元素（不包含段落符 pPr/rPr 里的）。"""
    root = doc.part.element if hasattr(doc, "part") else doc
    return [
        e for e in root.iter(qn("w:del"))
        if e.get(qn("w:author")) == author and e.getparent().tag != qn("w:rPr")
    ]


def accept_all_tracked(doc) -> tuple[int, int]:
    """接受文档内所有追踪修订（相当于 Word 里「接受所有修订」）。

    - 每个 `<w:ins>`：把内部子节点原位提升到父节点，再删掉 `<w:ins>` 外壳
    - 每个 `<w:del>`：整节点删除（其内容也一并消失）
    - `<w:pPr><w:rPr><w:del/>` 段落符标记：把当前段落与下一段合并（把当前段的
      内容并到下一段前面，再删掉当前段）
    - `<w:moveFrom>` / `<w:moveTo>`：类比 del / ins 处理

    返回 `(接受 ins 数, 接受 del 数)`（不含段落符合并）。
    """
    root = doc.part.element if hasattr(doc, "part") else doc

    # 段落符合并（要在 del 消除之前完成，因为合并时要保留下一段内容）
    for para_del in list(root.iter(qn("w:del"))):
        parent = para_del.getparent()
        if parent is None or parent.tag != qn("w:rPr"):
            continue
        ppr = parent.getparent()
        p = ppr.getparent() if ppr is not None else None
        if p is None or p.tag != qn("w:p"):
            continue
        # 把 p 从其容器中删除；p 的正文（非 pPr 部分）需要延续到下一段前
        container = p.getparent()
        if container is None:
            continue
        idx = container.index(p)
        # 找下一段 w:p
        next_p = None
        for sib in container[idx + 1:]:
            if sib.tag == qn("w:p"):
                next_p = sib
                break
        # 段落符 del 场景：接受后当前段与下一段合并；先把当前段正文 prepend 到下一段
        if next_p is not None:
            next_ppr = next_p.find(qn("w:pPr"))
            insert_at = 0 if next_ppr is None else (list(next_p).index(next_ppr) + 1)
            for child in list(p):
                if child.tag == qn("w:pPr"):
                    continue
                p.remove(child)
                next_p.insert(insert_at, child)
                insert_at += 1
        container.remove(p)

    ins_count = 0
    del_count = 0
    for ins in list(root.iter(qn("w:ins"))):
        parent = ins.getparent()
        if parent is None:
            continue
        idx = parent.index(ins)
        for child in list(ins):
            ins.remove(child)
            parent.insert(idx, child)
            idx += 1
        parent.remove(ins)
        ins_count += 1

    for del_el in list(root.iter(qn("w:del"))):
        parent = del_el.getparent()
        if parent is None:
            continue
        # 段落符 del 已经在上面处理，这里跳过
        if parent.tag == qn("w:rPr"):
            continue
        parent.remove(del_el)
        del_count += 1

    for move_from in list(root.iter(qn("w:moveFrom"))):
        parent = move_from.getparent()
        if parent is not None:
            parent.remove(move_from)
    for move_to in list(root.iter(qn("w:moveTo"))):
        parent = move_to.getparent()
        if parent is None:
            continue
        idx = parent.index(move_to)
        for child in list(move_to):
            move_to.remove(child)
            parent.insert(idx, child)
            idx += 1
        parent.remove(move_to)

    return ins_count, del_count
