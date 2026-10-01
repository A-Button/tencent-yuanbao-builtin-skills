#!/usr/bin/env python3
"""把演讲备注（speaker notes）写入解包后的 OOXML 树。

演讲备注存在 ``ppt/notesSlides/notesSlideN.xml`` 的 ``<p:ph type="body">`` 占位符里，
经 ``ppt/slides/_rels/slideM.xml.rels`` 的 notesSlide 关系与对应页绑定，在 PowerPoint
"视图→备注" 窗格 / 备注页视图中显示。

本脚本对每一页目标幻灯片：
  - 已有 notesSlide → 直接把正文占位符文字换成给定备注；
  - 没有 notesSlide → 克隆一份已有 notesSlide（保留页眉/页脚/母版引用等结构），改写
    其 slide 关系指向本页、写入备注正文，并补齐 ``[Content_Types].xml`` 的 Override；
    若整副一个 notesSlide 都没有，则退化为最小 notesSlide（引用已有 notesMaster）。

用法：
  python scripts/set_notes.py <unpacked_dir> notes.json [--report set_notes_report.json] [-q]
  python scripts/set_notes.py <unpacked_dir> --clear   # 清空所有 notesSlide 正文

notes.json 支持三种写法（slide 为**物理 slide 编号**，与 content_lines.tsv 里
slideN:shapeM 的 N 一致）：
  [{"slide": 1, "note": "开场：..."}, {"ref": "slide2", "note": "..."}]
  {"1": "开场：...", "2": "..."}
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace
from xml.etree import ElementTree as ET

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
NOTES_CT = "application/vnd.openxmlformats-officedocument.presentationml.notesSlide+xml"
NOTES_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesSlide"
SLIDE_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide"
NOTESMASTER_REL_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/notesMaster"

for pre, uri in (('a', A), ('p', P), ('r', R)):
    ET.register_namespace(pre, uri)


def _slide_num(spec) -> int | None:
    if isinstance(spec, int):
        return spec
    m = re.match(r'(?:slide)?(\d+)', str(spec).strip())
    return int(m.group(1)) if m else None


def _load_notes(notes_arg: str, run_root: Path) -> dict[int, str]:
    p = Path(notes_arg)
    if not p.is_absolute():
        p = run_root / notes_arg
    if not p.exists():
        # 也允许直接把 JSON 字面量传进来
        try:
            data = json.loads(notes_arg)
        except Exception:
            raise SystemExit(f'找不到 notes 文件且不是合法 JSON：{notes_arg}')
    else:
        data = json.loads(p.read_text(encoding='utf-8'))
    out: dict[int, str] = {}
    if isinstance(data, dict):
        for k, v in data.items():
            n = _slide_num(k)
            if n is not None and isinstance(v, str):
                out[n] = v
    elif isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            n = _slide_num(item.get('slide', item.get('ref')))
            note = item.get('note', item.get('text', ''))
            if n is not None and isinstance(note, str):
                out[n] = note
    return out


def _set_body_text(notes_root: ET.Element, text: str) -> bool:
    """把 notesSlide 的正文占位符（ph type=body）文字设为 text（按 \n 分段）。"""
    body_sp = None
    for sp in notes_root.iter(f'{{{P}}}sp'):
        ph = sp.find(f'.//{{{P}}}ph')
        if ph is not None and ph.get('type') == 'body':
            body_sp = sp
            break
    if body_sp is None:
        return False
    txBody = body_sp.find(f'{{{P}}}txBody')
    if txBody is None:
        txBody = ET.SubElement(body_sp, f'{{{P}}}txBody')
        ET.SubElement(txBody, f'{{{A}}}bodyPr')
        ET.SubElement(txBody, f'{{{A}}}lstStyle')
    else:
        for para in txBody.findall(f'{{{A}}}p'):
            txBody.remove(para)
    for line in (text.split('\n') or ['']):
        para = ET.SubElement(txBody, f'{{{A}}}p')
        pPr = ET.SubElement(para, f'{{{A}}}pPr')
        pPr.set('algn', 'l')
        run = ET.SubElement(para, f'{{{A}}}r')
        rPr = ET.SubElement(run, f'{{{A}}}rPr')
        rPr.set('lang', 'zh-CN')
        rPr.set('dirty', '0')
        t = ET.SubElement(run, f'{{{A}}}t')
        t.text = line
    return True


def _existing_notes_indices(unpacked: Path) -> list[int]:
    d = unpacked / 'ppt' / 'notesSlides'
    if not d.exists():
        return []
    out = []
    for f in d.glob('notesSlide*.xml'):
        m = re.match(r'notesSlide(\d+)\.xml', f.name)
        if m:
            out.append(int(m.group(1)))
    return sorted(out)


def _slide_notes_target(unpacked: Path, slide_n: int) -> str | None:
    rels = unpacked / 'ppt' / 'slides' / '_rels' / f'slide{slide_n}.xml.rels'
    if not rels.exists():
        return None
    root = ET.parse(rels).getroot()
    for r in root.iter(f'{{{REL}}}Relationship'):
        if r.get('Type') == NOTES_REL_TYPE:
            return r.get('Target')
    return None


def _next_rid(rels_root: ET.Element) -> str:
    nums = [int(m.group(1)) for r in rels_root.iter(f'{{{REL}}}Relationship')
            if (m := re.match(r'rId(\d+)', r.get('Id', '')))]
    return f'rId{(max(nums) + 1) if nums else 1}'


def _notesmaster_target_from(unpacked: Path) -> str | None:
    """任取一个已有 notesSlide 的 notesMaster 关系目标；没有则查 notesMasters 目录。"""
    d = unpacked / 'ppt' / 'notesSlides' / '_rels'
    if d.exists():
        for f in d.glob('notesSlide*.xml.rels'):
            root = ET.parse(f).getroot()
            for r in root.iter(f'{{{REL}}}Relationship'):
                if r.get('Type') == NOTESMASTER_REL_TYPE:
                    return r.get('Target')
    masters = sorted((unpacked / 'ppt' / 'notesMasters').glob('notesMaster*.xml')) \
        if (unpacked / 'ppt' / 'notesMasters').exists() else []
    if masters:
        return f'../notesMasters/{masters[0].name}'
    return None


def _add_content_type_override(unpacked: Path, part_name: str) -> None:
    ct_path = unpacked / '[Content_Types].xml'
    tree = ET.parse(ct_path)
    root = tree.getroot()
    for ov in root.findall(f'{{{CT}}}Override'):
        if ov.get('PartName') == part_name:
            return
    ov = ET.SubElement(root, f'{{{CT}}}Override')
    ov.set('PartName', part_name)
    ov.set('ContentType', NOTES_CT)
    ET.register_namespace('', CT)
    tree.write(ct_path, encoding='UTF-8', xml_declaration=True)


def _create_notes_slide(unpacked: Path, slide_n: int, text: str,
                        clone_idx: int | None, new_idx: int) -> bool:
    ns_dir = unpacked / 'ppt' / 'notesSlides'
    ns_rels_dir = ns_dir / '_rels'
    ns_dir.mkdir(parents=True, exist_ok=True)
    ns_rels_dir.mkdir(parents=True, exist_ok=True)
    master_target = _notesmaster_target_from(unpacked)

    if clone_idx is not None:
        notes_root = ET.parse(ns_dir / f'notesSlide{clone_idx}.xml').getroot()
    else:
        notes_root = ET.fromstring(_MINIMAL_NOTES)
    if not _set_body_text(notes_root, text):
        return False
    ET.ElementTree(notes_root).write(ns_dir / f'notesSlide{new_idx}.xml',
                                     encoding='UTF-8', xml_declaration=True)

    # notesSlide 自身的 rels：指向本页 slide + notesMaster
    rels = ET.Element(f'{{{REL}}}Relationships')
    if master_target:
        rm = ET.SubElement(rels, f'{{{REL}}}Relationship')
        rm.set('Id', 'rId1')
        rm.set('Type', NOTESMASTER_REL_TYPE)
        rm.set('Target', master_target)
    rs = ET.SubElement(rels, f'{{{REL}}}Relationship')
    rs.set('Id', 'rId2')
    rs.set('Type', SLIDE_REL_TYPE)
    rs.set('Target', f'../slides/slide{slide_n}.xml')
    ET.ElementTree(rels).write(ns_rels_dir / f'notesSlide{new_idx}.xml.rels',
                               encoding='UTF-8', xml_declaration=True)

    # slide 的 rels 里加一条 notesSlide 关系
    slide_rels_path = unpacked / 'ppt' / 'slides' / '_rels' / f'slide{slide_n}.xml.rels'
    if slide_rels_path.exists():
        srtree = ET.parse(slide_rels_path)
        sroot = srtree.getroot()
    else:
        sroot = ET.Element(f'{{{REL}}}Relationships')
        srtree = ET.ElementTree(sroot)
    rn = ET.SubElement(sroot, f'{{{REL}}}Relationship')
    rn.set('Id', _next_rid(sroot))
    rn.set('Type', NOTES_REL_TYPE)
    rn.set('Target', f'../notesSlides/notesSlide{new_idx}.xml')
    srtree.write(slide_rels_path, encoding='UTF-8', xml_declaration=True)

    _add_content_type_override(unpacked, f'/ppt/notesSlides/notesSlide{new_idx}.xml')
    return True


# 无任何可克隆 notesSlide 时的最小 notesSlide 骨架（含 body 占位符）。
_MINIMAL_NOTES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    f'<p:notes xmlns:a="{A}" xmlns:r="{R}" xmlns:p="{P}">'
    '<p:cSld><p:spTree>'
    '<p:nvGrpSpPr><p:cNvPr id="1" name=""/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr>'
    '<p:grpSpPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/>'
    '<a:chOff x="0" y="0"/><a:chExt cx="0" cy="0"/></a:xfrm></p:grpSpPr>'
    '<p:sp><p:nvSpPr><p:cNvPr id="2" name="Notes Placeholder"/>'
    '<p:cNvSpPr><a:spLocks noGrp="1"/></p:cNvSpPr>'
    '<p:nvPr><p:ph type="body" idx="1"/></p:nvPr></p:nvSpPr>'
    '<p:spPr/><p:txBody><a:bodyPr/><a:lstStyle/>'
    '<a:p><a:endParaRPr lang="zh-CN"/></a:p></p:txBody></p:sp>'
    '</p:spTree></p:cSld></p:notes>'
)


def run(unpacked: Path | str, notes: str | None = None, *,
        clear: bool = False, report_path: Path | str | None = None,
        quiet: bool = False) -> tuple[int, dict]:
    """写入演讲备注。返回 (exit_code, result)，可供 import 调用。"""
    unpacked = Path(unpacked)
    if not (unpacked / 'ppt' / 'slides').exists():
        err = {'error': f'不是有效的解包目录：{unpacked}'}
        if not quiet:
            print(json.dumps(err, ensure_ascii=False))
        return 2, err

    result: dict = {'set': [], 'created': [], 'skipped': [], 'errors': []}
    emit_args = SimpleNamespace(report=report_path, quiet=quiet)

    if clear:
        for idx in _existing_notes_indices(unpacked):
            f = unpacked / 'ppt' / 'notesSlides' / f'notesSlide{idx}.xml'
            root = ET.parse(f).getroot()
            _set_body_text(root, '')
            ET.ElementTree(root).write(f, encoding='UTF-8', xml_declaration=True)
            result['set'].append({'notesSlide': idx, 'cleared': True})
        _emit(emit_args, result)
        return 0, result

    if not notes:
        err = {'error': '需要 notes.json（或 --clear）'}
        if not quiet:
            print(json.dumps(err, ensure_ascii=False))
        return 2, err

    notes_map = _load_notes(notes, unpacked.parent)
    if not notes_map:
        result['errors'].append('notes 为空或解析不出任何 {slide: note} 项')
        _emit(emit_args, result)
        return 2, result

    existing = _existing_notes_indices(unpacked)
    clone_src = existing[0] if existing else None
    next_idx = (max(existing) + 1) if existing else 1

    for slide_n in sorted(notes_map):
        slide_xml = unpacked / 'ppt' / 'slides' / f'slide{slide_n}.xml'
        if not slide_xml.exists():
            result['skipped'].append({'slide': slide_n, 'reason': 'slide 不存在'})
            continue
        text = notes_map[slide_n]
        target = _slide_notes_target(unpacked, slide_n)
        if target:
            ns_path = (unpacked / 'ppt' / 'slides' / target).resolve()
            if not ns_path.exists():
                ns_path = (unpacked / 'ppt' / ('notesSlides/' + target.split('notesSlides/')[-1]))
            root = ET.parse(ns_path).getroot()
            if _set_body_text(root, text):
                ET.ElementTree(root).write(ns_path, encoding='UTF-8', xml_declaration=True)
                result['set'].append({'slide': slide_n, 'notesSlide': ns_path.name})
            else:
                result['errors'].append({'slide': slide_n, 'reason': 'notesSlide 无 body 占位符'})
        else:
            ok = _create_notes_slide(unpacked, slide_n, text, clone_src, next_idx)
            if ok:
                result['created'].append({'slide': slide_n, 'notesSlide': next_idx})
                next_idx += 1
            else:
                result['errors'].append({'slide': slide_n, 'reason': '新建 notesSlide 失败'})

    result['summary'] = {
        'set': len(result['set']),
        'created': len(result['created']),
        'skipped': len(result['skipped']),
        'errors': len(result['errors']),
    }
    _emit(emit_args, result)
    return (2 if result['errors'] else 0), result


def main() -> int:
    ap = argparse.ArgumentParser(description='把演讲备注写入解包后的 OOXML 树。')
    ap.add_argument('unpacked', help='解包目录（$RUN/unpacked）')
    ap.add_argument('notes', nargs='?', help='notes.json 路径（相对 run_dir 或绝对）或 JSON 字面量')
    ap.add_argument('--clear', action='store_true', help='清空所有 notesSlide 正文，不写新备注')
    ap.add_argument('--report', help='把结果 JSON 写到该路径')
    ap.add_argument('-q', '--quiet', action='store_true', help='不在 stdout 打印结果 JSON')
    args = ap.parse_args()
    code, _ = run(args.unpacked, args.notes, clear=args.clear,
                  report_path=args.report, quiet=args.quiet)
    return code


def _emit(args, result: dict) -> None:
    if args.report:
        Path(args.report).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if not args.quiet:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    raise SystemExit(main())
