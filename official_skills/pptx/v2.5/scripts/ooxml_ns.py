#!/usr/bin/env python3
"""OOXML 命名空间前缀治理：

背景：本管线里用 ElementTree 改写 XML 的步骤（select_slides / replace_text /
replace_image / adjust_shape）在重序列化时，若某命名空间未注册前缀，ElementTree
会自动起 `ns0/ns2/ns3…` 这种前缀。模板原本是标准前缀（a/p/r/p14/p15/c/a16…），
PowerPoint（尤其 Mac）按标准前缀解析，遇到自动前缀会判"内容有问题"→报修复。

提供两件事：
1. `register_all()`：把标准 OOXML 前缀全量注册进 ElementTree（治本，编辑脚本 import 即生效）。
2. `normalize_pptx()`：对成品 pptx 做一次兜底——把任意 `nsN:` 前缀按其 URI 改回标准前缀。
"""

from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

# URI -> 标准前缀（覆盖 ECMA-376 + 常见 MS Office 扩展）
NS_PREFIX = {
    'http://schemas.openxmlformats.org/drawingml/2006/main': 'a',
    'http://schemas.openxmlformats.org/drawingml/2006/chart': 'c',
    'http://schemas.openxmlformats.org/drawingml/2006/chartDrawing': 'cdr',
    'http://schemas.openxmlformats.org/drawingml/2006/diagram': 'dgm',
    'http://schemas.openxmlformats.org/drawingml/2006/picture': 'pic',
    'http://schemas.openxmlformats.org/drawingml/2006/compatibility': 'comp',
    'http://schemas.openxmlformats.org/drawingml/2006/lockedCanvas': 'lc',
    'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing': 'xdr',
    'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing': 'wp',
    'http://schemas.openxmlformats.org/presentationml/2006/main': 'p',
    'http://schemas.openxmlformats.org/officeDocument/2006/relationships': 'r',
    'http://schemas.openxmlformats.org/officeDocument/2006/math': 'm',
    'http://schemas.openxmlformats.org/markup-compatibility/2006': 'mc',
    'http://schemas.microsoft.com/office/drawing/2008/diagram': 'dsp',
    'http://schemas.microsoft.com/office/drawing/2010/main': 'a14',
    'http://schemas.microsoft.com/office/drawing/2012/chart': 'c15',
    'http://schemas.microsoft.com/office/drawing/2014/main': 'a16',
    'http://schemas.microsoft.com/office/drawing/2014/chart': 'c16',
    'http://schemas.microsoft.com/office/drawing/2015/06/chart': 'c16r2',
    'http://schemas.microsoft.com/office/drawing/2015/9/8/chartex': 'cx',
    'http://schemas.microsoft.com/office/drawing/2017/decorative': 'adec',
    'http://schemas.microsoft.com/office/powerpoint/2010/main': 'p14',
    'http://schemas.microsoft.com/office/powerpoint/2012/main': 'p15',
    'http://schemas.microsoft.com/office/powerpoint/2015/main': 'p16',
    'http://schemas.microsoft.com/office/powerpoint/2015/09/main': 'p159',
    'http://schemas.microsoft.com/office/powerpoint/2018/8/main': 'p188',
    'http://schemas.microsoft.com/office/mac/drawingml/2011/main': 'am3d',
    'http://schemas.microsoft.com/office/spreadsheetml/2009/9/main': 'x14',
    'http://schemas.microsoft.com/office/2006/coverPageProps': 'cppr',
}

_AUTO_RE = re.compile(r'^ns\d+$')


def register_all() -> None:
    """把标准前缀全量注册进 ElementTree（进程级生效）。供编辑脚本 import 后调用。"""
    for uri, pfx in NS_PREFIX.items():
        try:
            ET.register_namespace(pfx, uri)
        except (ValueError, KeyError):
            pass


def _normalize_xml(data: bytes) -> bytes:
    """把单个 XML part 里的自动前缀(nsN)按 URI 改回标准前缀。无自动前缀则原样返回。"""
    try:
        head = data[:4000].decode('utf-8', 'ignore')
    except Exception:
        return data
    decls = re.findall(r'xmlns:(ns\d+)="([^"]+)"', head)
    rename = {}
    for auto, uri in decls:
        # 已知 URI 用标准前缀；未知 URI 也别留 ns\d（前缀语义透明，改成 x<编号> 即可）
        std = NS_PREFIX.get(uri) or ('x' + auto[2:])
        if std != auto:
            rename[auto] = std
    if not rename:
        return data
    text = data.decode('utf-8', 'ignore')
    for auto, std in rename.items():
        # 命名空间声明
        text = text.replace(f'xmlns:{auto}=', f'xmlns:{std}=')
        # 元素/属性 QName 前缀（<ns2: , </ns2: , 空格ns2: ）
        text = re.sub(rf'([<\s/]){auto}:', rf'\g<1>{std}:', text)
        # mc:Ignorable / Requires 等属性值里以前缀单词形式出现
        text = re.sub(rf'(Ignorable|Requires)="([^"]*)"',
                      lambda m, a=auto, s=std: f'{m.group(1)}="'
                      + re.sub(rf'(^|\s){a}(\s|$)', rf'\g<1>{s}\g<2>', m.group(2)) + '"',
                      text)
    return text.encode('utf-8')


_PARA_RE = re.compile(r'(<(?P<pfx>\w+:)?p>)(?P<body>(?:(?!</(?:\w+:)?p>).)*?)(</(?:\w+:)?p>)', re.S)
_EPR_RE = re.compile(r'<(?:\w+:)?endParaRPr\b[^>]*?(?:/>|>.*?</(?:\w+:)?endParaRPr>)', re.S)
_RUNLIKE_RE = re.compile(r'<(?:\w+:)?(?:r|br|fld)\b')


def _reorder_body(body: str) -> str:
    """把段落 body 内的 endParaRPr 移到末尾（OOXML 强制：pPr? , run* , endParaRPr?）。"""
    m = _EPR_RE.search(body)
    if not m:
        return body
    after = body[m.end():]
    if not _RUNLIKE_RE.search(after):  # endParaRPr 后面没有 run/br/fld，已合规
        return body
    epr = m.group(0)
    return body[:m.start()] + after + epr


def fix_paragraph_order(path: Path) -> dict:
    """对成品里 slides/layouts/masters 的每个段落，强制 endParaRPr 置于末尾。"""
    src = Path(path)
    zin = zipfile.ZipFile(src)
    blobs = {n: zin.read(n) for n in zin.namelist()}
    zin.close()
    fixed = []

    def _sub(mm):
        return mm.group(1) + _reorder_body(mm.group('body')) + mm.group(4)

    for n, b in list(blobs.items()):
        if not re.match(r'ppt/(slides|slideLayouts|slideMasters|notesSlides)/[^/]+\.xml$', n):
            continue
        text = b.decode('utf-8', 'ignore')
        new = _PARA_RE.sub(_sub, text)
        if new != text:
            blobs[n] = new.encode('utf-8')
            fixed.append(n)
    if fixed:
        ordered = sorted(blobs.keys(), key=lambda n: (n != '[Content_Types].xml', n))
        tmp = src.with_suffix('.potmp.pptx')
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for n in ordered:
                zout.writestr(n, blobs[n])
        tmp.replace(src)
    return {'ok': True, 'reordered_parts': len(fixed), 'parts': fixed}


def normalize_pptx(path: Path) -> dict:
    """对成品 pptx 原地归一化所有 XML part 的命名空间前缀。返回处理统计。"""
    src = Path(path)
    zin = zipfile.ZipFile(src)
    blobs = {n: zin.read(n) for n in zin.namelist()}
    zin.close()
    fixed = []
    for n, b in blobs.items():
        if n.endswith('.xml') or n.endswith('.rels'):
            nb = _normalize_xml(b)
            if nb != b:
                blobs[n] = nb
                fixed.append(n)
    if fixed:
        ordered = sorted(blobs.keys(), key=lambda n: (n != '[Content_Types].xml', n))
        tmp = src.with_suffix('.nstmp.pptx')
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for n in ordered:
                zout.writestr(n, blobs[n])
        tmp.replace(src)
    return {'ok': True, 'normalized_parts': len(fixed), 'parts': fixed}


import posixpath

# 复制页后必须独立、不能被两页共享的独占部件（否则 PowerPoint 判损坏需修复）
_OWNED_RELS = {
    'chart', 'chartEx',
    'diagramData', 'diagramLayout', 'diagramQuickStyle', 'diagramColors', 'diagramDrawing',
    'oleObject', 'package', 'tags',
}


def _rt_local(t: str) -> str:
    return t.rsplit('/', 1)[-1] if t else ''


def _rels_name(part: str) -> str:
    d, b = posixpath.dirname(part), posixpath.basename(part)
    return f'{d}/_rels/{b}.rels' if d else f'_rels/{b}.rels'


def deshare_owned_parts(path: Path) -> dict:
    """检测被多页共享的独占部件(chart/SmartArt/ole)，为额外引用方克隆独立副本。兜底+修现有文件。"""
    src = Path(path)
    zin = zipfile.ZipFile(src)
    blobs = {n: zin.read(n) for n in zin.namelist()}
    zin.close()
    names = set(blobs)
    ct_name = '[Content_Types].xml'
    ct = blobs.get(ct_name, b'').decode('utf-8', 'ignore')
    overrides = {m.group(1): m.group(2)
                 for m in re.finditer(r'<Override PartName="([^"]+)" ContentType="([^"]+)"/>', ct)}
    new_overrides: list[tuple[str, str]] = []
    claimed: dict[str, str] = {}
    stats = {'cloned': 0}

    def next_name(part: str) -> str:
        d, nm = posixpath.dirname(part), posixpath.basename(part)
        m = re.match(r'(.*?)(\d+)(\.[^.]+)$', nm)
        if m:
            prefix, ext = m.group(1), m.group(3)
        else:
            m2 = re.match(r'(.*)(\.[^.]+)$', nm)
            prefix, ext = (m2.group(1), m2.group(2)) if m2 else (nm, '')
        i = 1
        while True:
            cand = f'{d}/{prefix}{i}{ext}' if d else f'{prefix}{i}{ext}'
            if cand not in names:
                return cand
            i += 1

    def clone_recursive(part: str) -> str:
        dst = next_name(part)
        blobs[dst] = blobs[part]
        names.add(dst)
        pn = '/' + part
        if pn in overrides:
            new_overrides.append((dst, overrides[pn]))
        rn = _rels_name(part)
        if rn in blobs:
            rtxt = blobs[rn].decode('utf-8', 'ignore')

            def sub(mm):
                a = mm.group(0)
                typ = re.search(r'Type="([^"]+)"', a)
                tgt = re.search(r'Target="([^"]+)"', a)
                mode = re.search(r'TargetMode="([^"]+)"', a)
                if tgt and typ and not (mode and mode.group(1) == 'External') \
                        and _rt_local(typ.group(1)) in _OWNED_RELS:
                    s = posixpath.normpath(posixpath.join(posixpath.dirname(part), tgt.group(1)))
                    if s in names:
                        sd = clone_recursive(s)
                        nt = posixpath.relpath(sd, posixpath.dirname(part))
                        return a.replace(f'Target="{tgt.group(1)}"', f'Target="{nt}"')
                return a
            blobs[_rels_name(dst)] = re.sub(r'<Relationship\b[^>]*/>', sub, rtxt).encode('utf-8')
            names.add(_rels_name(dst))
        return dst

    slide_parts = sorted([n for n in names if re.match(r'ppt/slides/slide\d+\.xml$', n)],
                         key=lambda s: int(re.search(r'\d+', s).group()))
    for sp in slide_parts:
        rn = _rels_name(sp)
        if rn not in blobs:
            continue
        rtxt = blobs[rn].decode('utf-8', 'ignore')

        def sub(mm, _sp=sp):
            a = mm.group(0)
            typ = re.search(r'Type="([^"]+)"', a)
            tgt = re.search(r'Target="([^"]+)"', a)
            mode = re.search(r'TargetMode="([^"]+)"', a)
            if not (tgt and typ) or (mode and mode.group(1) == 'External'):
                return a
            if _rt_local(typ.group(1)) not in _OWNED_RELS:
                return a
            owned = posixpath.normpath(posixpath.join(posixpath.dirname(_sp), tgt.group(1)))
            if owned not in names:
                return a
            if owned not in claimed:
                claimed[owned] = _sp
                return a
            dst = clone_recursive(owned)
            nt = posixpath.relpath(dst, posixpath.dirname(_sp))
            stats['cloned'] += 1
            return a.replace(f'Target="{tgt.group(1)}"', f'Target="{nt}"')
        new = re.sub(r'<Relationship\b[^>]*/>', sub, rtxt)
        if new != rtxt:
            blobs[rn] = new.encode('utf-8')

    if new_overrides:
        ins = ''.join(f'<Override PartName="/{d}" ContentType="{c}"/>' for d, c in new_overrides)
        blobs[ct_name] = ct.replace('</Types>', ins + '</Types>').encode('utf-8')
    if stats['cloned']:
        ordered = sorted(blobs.keys(), key=lambda n: (n != ct_name, n))
        tmp = src.with_suffix('.dstmp.pptx')
        with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
            for n in ordered:
                zout.writestr(n, blobs[n])
        tmp.replace(src)
    return {'ok': True, 'cloned_parts': stats['cloned']}


def main() -> int:
    import json
    if len(sys.argv) < 2:
        print('用法: ooxml_ns.py <pptx>', file=sys.stderr)
        return 1
    p = Path(sys.argv[1])
    rep = {'ns': normalize_pptx(p), 'para_order': fix_paragraph_order(p),
           'deshare': deshare_owned_parts(p)}
    print(json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
