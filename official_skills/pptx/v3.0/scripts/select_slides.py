#!/usr/bin/env python3
"""Keep/reorder/duplicate selected slides in an unpacked PPTX.

Supports slide duplication: when a slide number appears more than once in
--slides (e.g. --slides 1,3,3,5), the repeated slide is physically copied
(XML + rels + notes) so each copy is independent and can be edited separately.

Run scripts/clean.py after this command to remove orphaned slide XML/media/rels.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from collections import Counter
from pathlib import Path
from xml.etree import ElementTree as ET


_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'
_CT_NS = 'http://schemas.openxmlformats.org/package/2006/content-types'

ET.register_namespace('p', _P)
ET.register_namespace('r', _R)
# 注册全量标准 OOXML 前缀，避免 ElementTree 把未注册命名空间序列化成 ns0/ns2…（会让 PowerPoint 报损坏）
try:
    from ooxml_ns import register_all as _reg_ns
    _reg_ns()
except Exception:
    pass


def _write_xml(tree: ET.ElementTree, path: Path, default_ns: str | None = None) -> None:
    """Serialize ``tree`` to ``path``, optionally forcing ``default_ns`` prefix-less.

    The OOXML relationships (``_REL_NS``) and content-types (``_CT_NS``) parts both use
    a prefix-less (default) namespace on their root element. ElementTree keeps only a
    single global slot for the empty prefix, so these two namespaces cannot both be
    registered permanently. We therefore set the correct default namespace immediately
    before each write. Without this, ElementTree emits an auto-generated prefix
    (e.g. ``<ns0:Relationship>`` / ``<ns0:Override>``), which breaks prefix-sensitive
    consumers like clean.py and prevents PowerPoint from opening the deck.
    """
    if default_ns is not None:
        ET.register_namespace('', default_ns)
    tree.write(path, xml_declaration=True, encoding='UTF-8')


def _slide_num_from_target(target: str) -> int | None:
    m = re.search(r'slides/slide(\d+)\.xml$', target)
    return int(m.group(1)) if m else None


def _rid_to_slide(unpacked: Path) -> dict[str, int]:
    rels = unpacked / 'ppt' / '_rels' / 'presentation.xml.rels'
    if not rels.exists():
        sys.exit(f'找不到 {rels}')
    tree = ET.parse(rels)
    out: dict[str, int] = {}
    for rel in tree.getroot().iter(f'{{{_REL_NS}}}Relationship'):
        num = _slide_num_from_target(rel.get('Target', ''))
        if num is not None:
            out[rel.get('Id', '')] = num
    return out


def _next_slide_num(unpacked: Path) -> int:
    """Return the next available slide number."""
    slides_dir = unpacked / 'ppt' / 'slides'
    existing = [int(m.group(1)) for f in slides_dir.glob('slide*.xml')
                if (m := re.match(r'slide(\d+)\.xml$', f.name))]
    return max(existing) + 1 if existing else 1


def _next_rid(rels_tree: ET.ElementTree) -> str:
    """Return next available rId in a rels file."""
    max_id = 0
    for rel in rels_tree.getroot().iter(f'{{{_REL_NS}}}Relationship'):
        rid = rel.get('Id', '')
        m = re.match(r'rId(\d+)', rid)
        if m:
            max_id = max(max_id, int(m.group(1)))
    return f'rId{max_id + 1}'


# 复制一页时必须随之"深拷贝"的独占部件（否则两页共享同一部件，PowerPoint 判损坏需修复）。
# 图片(image)/外链可安全共享，故不在此列；这些则必须各自独立。
_OWNED_PART_RELS = {
    'chart', 'chartEx',
    'diagramData', 'diagramLayout', 'diagramQuickStyle', 'diagramColors', 'diagramDrawing',
    'oleObject', 'package', 'tags',
}


def _reltype_local(t: str) -> str:
    return t.rsplit('/', 1)[-1] if t else ''


def _next_numbered_name(dirpath: Path, name: str) -> str:
    """给同目录下一个未占用的编号文件名，如 chart1.xml -> chart2.xml。"""
    m = re.match(r'(.*?)(\d+)(\.[^.]+)$', name)
    if m:
        prefix, ext = m.group(1), m.group(3)
    else:
        m2 = re.match(r'(.*)(\.[^.]+)$', name)
        prefix, ext = (m2.group(1), m2.group(2)) if m2 else (name, '')
    num_re = re.compile(re.escape(prefix) + r'(\d+)' + re.escape(ext) + r'$')
    nums = [int(mm.group(1)) for f in dirpath.glob('*') if (mm := num_re.match(f.name))]
    return f'{prefix}{(max(nums) + 1) if nums else 1}{ext}'


def _add_override_like(unpacked: Path, src_part: Path, dst_part: Path) -> None:
    """若源部件在 [Content_Types].xml 有 Override，则给新部件加同类型 Override。"""
    ct_path = unpacked / '[Content_Types].xml'
    if not ct_path.exists():
        return
    ct_tree = ET.parse(ct_path)
    root = ct_tree.getroot()
    src_pn = '/' + str(src_part.relative_to(unpacked)).replace('\\', '/')
    dst_pn = '/' + str(dst_part.relative_to(unpacked)).replace('\\', '/')
    for ov in list(root):
        if ov.tag.endswith('}Override') or ov.tag == 'Override':
            if ov.get('PartName') == src_pn:
                new_ov = ET.SubElement(root, ov.tag)
                new_ov.set('PartName', dst_pn)
                new_ov.set('ContentType', ov.get('ContentType', ''))
                _write_xml(ct_tree, ct_path, _CT_NS)
                return


def _clone_owned_part(unpacked: Path, src_abs: Path, clone_map: dict[str, Path]) -> Path:
    """递归深拷贝一个独占部件（含其自身 rels 及其引用的独占子部件），返回新部件绝对路径。"""
    key = str(src_abs)
    if key in clone_map:
        return clone_map[key]
    dirpath = src_abs.parent
    new_name = _next_numbered_name(dirpath, src_abs.name)
    dst_abs = dirpath / new_name
    shutil.copy2(src_abs, dst_abs)
    clone_map[key] = dst_abs
    _add_override_like(unpacked, src_abs, dst_abs)

    src_rels = dirpath / '_rels' / (src_abs.name + '.rels')
    if src_rels.exists():
        rels_tree = ET.parse(src_rels)
        for rel in rels_tree.getroot().iter(f'{{{_REL_NS}}}Relationship'):
            if rel.get('TargetMode') == 'External':
                continue
            if _reltype_local(rel.get('Type', '')) in _OWNED_PART_RELS:
                sub_src = Path(os.path.normpath(str(dirpath / rel.get('Target', ''))))
                if sub_src.exists():
                    sub_dst = _clone_owned_part(unpacked, sub_src, clone_map)
                    rel.set('Target', os.path.relpath(str(sub_dst), str(dirpath)).replace('\\', '/'))
        _write_xml(rels_tree, dirpath / '_rels' / (new_name + '.rels'), _REL_NS)
    return dst_abs


def _clone_owned_parts_for_slide(unpacked: Path, slide_rels_path: Path) -> None:
    """复制页后，把该页 rels 中指向独占部件(chart/SmartArt/内嵌对象)的目标改为独立副本。"""
    if not slide_rels_path.exists():
        return
    slides_dir = slide_rels_path.parent.parent  # ppt/slides
    tree = ET.parse(slide_rels_path)
    clone_map: dict[str, Path] = {}
    changed = False
    for rel in tree.getroot().iter(f'{{{_REL_NS}}}Relationship'):
        if rel.get('TargetMode') == 'External':
            continue
        if _reltype_local(rel.get('Type', '')) in _OWNED_PART_RELS:
            src_part = Path(os.path.normpath(str(slides_dir / rel.get('Target', ''))))
            if src_part.exists():
                new_part = _clone_owned_part(unpacked, src_part, clone_map)
                rel.set('Target', os.path.relpath(str(new_part), str(slides_dir)).replace('\\', '/'))
                changed = True
    if changed:
        _write_xml(tree, slide_rels_path, _REL_NS)


def _duplicate_slide(unpacked: Path, src_num: int, pres_rels_tree: ET.ElementTree) -> tuple[int, str]:
    """Physically copy a slide and return (new_num, new_rId)."""
    new_num = _next_slide_num(unpacked)
    slides_dir = unpacked / 'ppt' / 'slides'
    rels_dir = slides_dir / '_rels'

    # Copy slide XML
    src_xml = slides_dir / f'slide{src_num}.xml'
    dst_xml = slides_dir / f'slide{new_num}.xml'
    shutil.copy2(src_xml, dst_xml)

    # Copy slide rels if exists
    src_rels = rels_dir / f'slide{src_num}.xml.rels'
    if src_rels.exists():
        dst_rels = rels_dir / f'slide{new_num}.xml.rels'
        shutil.copy2(src_rels, dst_rels)

    # Copy notes slide if referenced
    notes_dir = unpacked / 'ppt' / 'notesSlides'
    if src_rels.exists():
        src_rels_tree = ET.parse(src_rels)
        for rel in src_rels_tree.getroot().iter(f'{{{_REL_NS}}}Relationship'):
            target = rel.get('Target', '')
            m = re.search(r'notesSlides/notesSlide(\d+)\.xml$', target.replace('\\', '/'))
            if m:
                notes_num = int(m.group(1))
                src_note = notes_dir / f'notesSlide{notes_num}.xml'
                if src_note.exists():
                    # Find next notes number
                    existing_notes = [int(nm.group(1)) for f in notes_dir.glob('notesSlide*.xml')
                                      if (nm := re.match(r'notesSlide(\d+)\.xml$', f.name))]
                    new_notes_num = max(existing_notes) + 1 if existing_notes else 1
                    dst_note = notes_dir / f'notesSlide{new_notes_num}.xml'
                    shutil.copy2(src_note, dst_note)
                    # Update reference in the copied rels
                    dst_rels_path = rels_dir / f'slide{new_num}.xml.rels'
                    if dst_rels_path.exists():
                        dst_rels_tree = ET.parse(dst_rels_path)
                        for r2 in dst_rels_tree.getroot().iter(f'{{{_REL_NS}}}Relationship'):
                            if r2.get('Target', '') == target:
                                r2.set('Target', f'../notesSlides/notesSlide{new_notes_num}.xml')
                        _write_xml(dst_rels_tree, dst_rels_path, _REL_NS)
                    # Add to [Content_Types].xml
                    ct_path = unpacked / '[Content_Types].xml'
                    if ct_path.exists():
                        ct_tree = ET.parse(ct_path)
                        ct_root = ct_tree.getroot()
                        override = ET.SubElement(ct_root, 'Override')
                        override.set('PartName', f'/ppt/notesSlides/notesSlide{new_notes_num}.xml')
                        override.set('ContentType', 'application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml')
                        _write_xml(ct_tree, ct_path, _CT_NS)
                break

    # 深拷贝独占部件（图表/SmartArt/内嵌对象），避免副本与原页共享同一部件 → PowerPoint 损坏修复
    _clone_owned_parts_for_slide(unpacked, rels_dir / f'slide{new_num}.xml.rels')

    # Add to presentation.xml.rels
    new_rid = _next_rid(pres_rels_tree)
    new_rel = ET.SubElement(pres_rels_tree.getroot(), f'{{{_REL_NS}}}Relationship')
    new_rel.set('Id', new_rid)
    new_rel.set('Type', 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide')
    new_rel.set('Target', f'slides/slide{new_num}.xml')

    # Add to [Content_Types].xml
    ct_path = unpacked / '[Content_Types].xml'
    if ct_path.exists():
        ct_tree = ET.parse(ct_path)
        ct_root = ct_tree.getroot()
        override = ET.SubElement(ct_root, 'Override')
        override.set('PartName', f'/ppt/slides/slide{new_num}.xml')
        override.set('ContentType', 'application/vnd.openxmlformats-officedocument.presentationml.slide+xml')
        _write_xml(ct_tree, ct_path, _CT_NS)

    return new_num, new_rid


def main() -> int:
    ap = argparse.ArgumentParser(description='Keep/reorder/duplicate selected slides in unpacked PPTX.')
    ap.add_argument('unpacked')
    ap.add_argument('--slides', required=True, help='Comma-separated slide numbers, e.g. 1,3,3,5 (repeats are duplicated)')
    args = ap.parse_args()

    unpacked = Path(args.unpacked)
    keep = [int(x) for x in args.slides.split(',') if x.strip()]
    if not keep:
        sys.exit('slides 不能为空')

    pres = unpacked / 'ppt' / 'presentation.xml'
    if not pres.exists():
        sys.exit(f'找不到 {pres}')

    pres_rels_path = unpacked / 'ppt' / '_rels' / 'presentation.xml.rels'
    pres_rels_tree = ET.parse(pres_rels_path)

    rid_to_slide = _rid_to_slide(unpacked)
    slide_to_rid: dict[int, str] = {v: k for k, v in rid_to_slide.items()}

    tree = ET.parse(pres)
    root = tree.getroot()
    sld_lst = root.find(f'.//{{{_P}}}sldIdLst')
    if sld_lst is None:
        sys.exit('presentation.xml 中找不到 p:sldIdLst')

    # Build elem map。同时记录**所有原始 sldId 的全局最大值**：复制页的新 id 必须
    # 从这个全局 max 之上递增分配，否则可能与"尚未 re-append 的原始页 id"撞车，
    # 产生重复 <p:sldId id>，导致 PowerPoint 打开时报"需要修复"。
    slide_to_elem: dict[int, ET.Element] = {}
    next_sld_id = 255
    for elem in list(sld_lst):
        sid = elem.get('id')
        if sid and sid.isdigit():
            next_sld_id = max(next_sld_id, int(sid))
        rid = elem.get(f'{{{_R}}}id')
        num = rid_to_slide.get(rid or '')
        if num is not None:
            slide_to_elem[num] = elem
        sld_lst.remove(elem)

    # Check all requested slides exist
    unique_requested = set(keep)
    missing = [n for n in unique_requested if n not in slide_to_elem]
    if missing:
        sys.exit(f'这些页不存在或未在 presentation 中引用: {missing}')

    # Track how many times each slide has been used (for duplication)
    usage_count: Counter[int] = Counter()
    duplicated = 0

    for num in keep:
        usage_count[num] += 1
        if usage_count[num] == 1:
            # First occurrence: use original
            sld_lst.append(slide_to_elem[num])
        else:
            # Subsequent occurrence: physical copy
            new_num, new_rid = _duplicate_slide(unpacked, num, pres_rels_tree)
            next_sld_id += 1  # 全局递增，保证整个 sldIdLst 内唯一
            new_elem = ET.SubElement(sld_lst, f'{{{_P}}}sldId')
            new_elem.set('id', str(next_sld_id))
            new_elem.set(f'{{{_R}}}id', new_rid)
            duplicated += 1

    # Save presentation.xml and rels
    _write_xml(tree, pres)
    _write_xml(pres_rels_tree, pres_rels_path, _REL_NS)

    print(f'已保留/重排 {len(keep)} 页 (其中复制 {duplicated} 份): {keep}')
    print('下一步运行: python scripts/clean.py <unpacked_dir>')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
