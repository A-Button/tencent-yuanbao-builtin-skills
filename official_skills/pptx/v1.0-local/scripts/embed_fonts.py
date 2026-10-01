#!/usr/bin/env python3
"""把成品 pptx 用到的字体按字重子集化内嵌，保证换机打开字重一致、消除合成粗体混排。

为什么需要：模板大量引用带字重的 CJK 字体（Source Han Serif SC Heavy/Medium、PingFang SC
Light、FZ…Song 等），成品默认不内嵌字体。换台没装这些精确字重的机器打开，查看器就会
部分用常规、部分合成(faux)粗体 → 字重错乱。把字体内嵌进 pptx 后，PowerPoint/WPS 按
typeface 名直接用内嵌字体渲染，所见即所得。

做法（低风险）：
  - **不改 slide XML**，PowerPoint 按 typeface 名匹配内嵌字体即可。
  - 收集成品所有 <a:t> 文本字符 → 子集化（只嵌用到的字形），体积很小。
  - 每个用到的 typeface 名，按"族(黑/宋)+字重"映射到容器已装的 Source Han / Noto CJK 字体，
    生成 regular + bold 两个槽位（覆盖 b="1" 的运行）。
  - 写 ppt/fonts/*.fntdata + presentation.xml 的 embeddedFontLst + rels + Content_Types，
    并置 embedTrueTypeFonts="1"。

依赖：fontTools。无 fontTools 或找不到字体则原样返回（不阻断交付）。
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
import zipfile
from io import BytesIO
from pathlib import Path

_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'

_SANS_DIR = '/usr/share/fonts/opentype/source-han-sans'
_NOTO_DIR = '/usr/share/fonts/opentype/noto'

_SANS_WEIGHT = {
    'thin': 'ExtraLight', 'extralight': 'ExtraLight', 'light': 'Light',
    'demilight': 'Light', 'normal': 'Normal', 'regular': 'Regular',
    'medium': 'Medium', 'semibold': 'Bold', 'demibold': 'Bold',
    'bold': 'Bold', 'heavy': 'Heavy', 'black': 'Heavy',
}
_SERIF_WEIGHT = {
    'thin': 'ExtraLight', 'extralight': 'ExtraLight', 'light': 'Light',
    'demilight': 'Light', 'normal': 'Regular', 'regular': 'Regular',
    'medium': 'Medium', 'semibold': 'SemiBold', 'demibold': 'SemiBold',
    'bold': 'Bold', 'heavy': 'Black', 'black': 'Black',
}

_SERIF_KEYS = ('serif', 'song', '宋', 'ming', '明', 'fz')

_TTC_IDX_CACHE: dict[str, int] = {}


def _detect_weight(name: str) -> str:
    low = name.lower()
    for kw in ('extralight', 'demilight', 'semibold', 'demibold', 'thin', 'light',
               'medium', 'heavy', 'black', 'bold', 'normal', 'regular'):
        if kw in low:
            return kw
    return 'regular'


def _is_serif(name: str) -> bool:
    low = name.lower()
    return any(k in low for k in _SERIF_KEYS)


def _ttc_sc_index(path: str) -> int:
    if path in _TTC_IDX_CACHE:
        return _TTC_IDX_CACHE[path]
    idx = 0
    try:
        from fontTools.ttLib import TTCollection
        ttc = TTCollection(path, lazy=True)
        for i, font in enumerate(ttc.fonts):
            try:
                names = ' '.join(str(n) for n in font['name'].names if n.nameID in (1, 4, 16))
            except Exception:
                names = ''
            if 'SC' in names or '简' in names or 'Simplified' in names:
                idx = i
                break
        ttc.close()
    except Exception:
        idx = 0
    _TTC_IDX_CACHE[path] = idx
    return idx


def _pick_file(serif: bool, weight_kw: str):
    if serif:
        suffix = _SERIF_WEIGHT.get(weight_kw, 'Regular')
        cands = [f'{_NOTO_DIR}/NotoSerifCJK-{suffix}.ttc'] + sorted(glob.glob(f'{_NOTO_DIR}/NotoSerifCJK-*.ttc'))
        for f in cands:
            if Path(f).exists():
                return f, _ttc_sc_index(f)
        return None
    suffix = _SANS_WEIGHT.get(weight_kw, 'Regular')
    cands = [f'{_SANS_DIR}/SourceHanSansSC-{suffix}.otf'] + sorted(glob.glob(f'{_SANS_DIR}/SourceHanSansSC-*.otf'))
    for f in cands:
        if Path(f).exists():
            return f, 0
    return None


def _otf_to_ttf(font, max_err: float = 1.0) -> bool:
    """把 CFF(OTTO) 字体的轮廓转成 TrueType(glyf)。PowerPoint 不支持内嵌 CFF 字体，
    只认 TrueType；不转的话成品在 PowerPoint 里会报"内容有问题需修复"。
    成功返回 True，失败返回 False（调用方应放弃内嵌该字体）。"""
    if font.sfntVersion != 'OTTO' or 'CFF ' not in font:
        return True
    from fontTools.ttLib import newTable
    from fontTools.pens.cu2quPen import Cu2QuPen
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    glyph_order = font.getGlyphOrder()
    glyph_set = font.getGlyphSet()
    quad = {}
    for gname in glyph_order:
        tt_pen = TTGlyphPen(glyph_set)
        # CFF 外轮廓方向与 TrueType 相反，需反向
        glyph_set[gname].draw(Cu2QuPen(tt_pen, max_err, reverse_direction=True))
        quad[gname] = tt_pen.glyph()

    font['loca'] = newTable('loca')
    glyf = font['glyf'] = newTable('glyf')
    glyf.glyphOrder = glyph_order
    glyf.glyphs = quad
    del font['CFF ']
    if 'VORG' in font:
        del font['VORG']
    glyf.compile(font)

    hmtx = font['hmtx']
    for gname, g in glyf.glyphs.items():
        if hasattr(g, 'xMin'):
            hmtx[gname] = (hmtx[gname][0], g.xMin)

    maxp = font['maxp'] = newTable('maxp')
    maxp.tableVersion = 0x00010000
    maxp.maxZones = 1
    maxp.maxTwilightPoints = 0
    maxp.maxStorage = 0
    maxp.maxFunctionDefs = 0
    maxp.maxInstructionDefs = 0
    maxp.maxStackElements = 0
    maxp.maxSizeOfInstructions = 0
    maxp.maxComponentElements = max(
        (len(getattr(g, 'components', [])) for g in glyf.glyphs.values()), default=0)
    maxp.compile(font)

    if 'post' in font:
        # 3.0：不存字形名（子集化已丢名）；PowerPoint 不需要，且避免 format2.0 需 mapping
        font['post'].formatType = 3.0
    font.sfntVersion = '\x00\x01\x00\x00'
    return True


# PowerPoint 自带的通用 Latin/符号字体：不内嵌（本机一定有，且内嵌 CJK 替身会"名不符"反而坏）。
_SKIP_TYPEFACES = {
    'arial', 'arial black', 'arial narrow', 'calibri', 'calibri light', 'cambria',
    'cambria math', 'candara', 'consolas', 'constantia', 'corbel', 'courier new',
    'georgia', 'segoe ui', 'segoe ui light', 'segoe ui semibold', 'segoe ui semilight',
    'segoe ui black', 'tahoma', 'times new roman', 'trebuchet ms', 'verdana',
    'book antiqua', 'garamond', 'century gothic', 'lucida sans', 'lucida console',
    'franklin gothic medium', 'impact', 'comic sans ms', 'symbol', 'wingdings',
    'wingdings 2', 'wingdings 3', 'webdings', 'marlett',
}


def _force_name(font, family: str, bold: bool) -> None:
    """把字体内部 name 表强制改成与 PPT 声明的 typeface 一致，并修正粗细样式位。
    PowerPoint（尤其 Mac）按字体内部族名校验内嵌字体，名不符会判损坏→报修复。"""
    sub = 'Bold' if bold else 'Regular'
    full = f'{family} {sub}' if bold else family
    ps = (family + ('-Bold' if bold else '')).replace(' ', '')
    name = font['name']
    for pid, eid, lid in ((3, 1, 0x409), (1, 0, 0)):
        name.setName(family, 1, pid, eid, lid)
        name.setName(sub, 2, pid, eid, lid)
        name.setName(full, 4, pid, eid, lid)
        name.setName(ps, 6, pid, eid, lid)
        name.setName(family, 16, pid, eid, lid)
        name.setName(sub, 17, pid, eid, lid)
    if 'head' in font:
        ms = font['head'].macStyle
        font['head'].macStyle = (ms | 0x1) if bold else (ms & ~0x1)
    if 'OS/2' in font:
        fs = font['OS/2'].fsSelection
        if bold:
            fs = (fs | 0x20) & ~0x40
        else:
            fs = (fs & ~0x20) | 0x40
        font['OS/2'].fsSelection = fs


def _subset_base(path: str, fontnum: int, text: str):
    """子集化 + CFF→TTF，返回 TTFont 的序列化字节（未改名）。最慢的一步，按物理文件缓存。"""
    try:
        from fontTools import subset
        from fontTools.ttLib import TTFont
    except Exception:
        return None
    try:
        font = TTFont(path, fontNumber=fontnum, lazy=True)
        opts = subset.Options()
        opts.glyph_names = False
        opts.name_IDs = [1, 2, 3, 4, 6, 16, 17]
        opts.notdef_outline = True
        opts.recalc_bounds = False
        opts.drop_tables += ['BASE', 'JSTF', 'DSIG']
        ss = subset.Subsetter(options=opts)
        cps = {ord(c) for c in text if ord(c) >= 32}
        cps.update(range(0x20, 0x7f))
        ss.populate(unicodes=cps)
        ss.subset(font)
        if not _otf_to_ttf(font):
            return None
        buf = BytesIO()
        font.save(buf)
        return buf.getvalue()
    except Exception:
        return None


def _named_part(base_bytes: bytes, family: str, bold: bool):
    """基于已子集化字节，克隆并把内部 name 改成 family（含粗细样式位），返回新字节。"""
    try:
        from fontTools.ttLib import TTFont
    except Exception:
        return None
    try:
        font = TTFont(BytesIO(base_bytes))
        _force_name(font, family, bold)
        buf = BytesIO()
        font.save(buf)
        return buf.getvalue()
    except Exception:
        return None


def _xml_escape(s: str) -> str:
    return s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')


def embed(src: Path, dst: Path) -> dict:
    zin = zipfile.ZipFile(src)
    blobs = {n: zin.read(n) for n in zin.namelist()}
    zin.close()
    pres_name = 'ppt/presentation.xml'
    if pres_name not in blobs:
        return {'ok': False, 'reason': 'no presentation.xml'}

    # 待嵌字体名只从 slides 收集（可见正文真正用到的），避免母版/主题里的几十个语言回退名。
    typefaces: set[str] = set()
    for n, b in blobs.items():
        if re.match(r'ppt/slides/slide\d+\.xml$', n):
            for tf in re.findall(r'typeface="([^"]+)"', b.decode('utf-8', 'ignore')):
                if tf and not tf.startswith('+'):
                    typefaces.add(tf)
    # 子集用字符取并集（覆盖 slides/母版/版式/备注，宁多勿缺）。
    text_chars: set[str] = set()
    for n, b in blobs.items():
        if re.match(r'ppt/(slides|slideLayouts|slideMasters|notesSlides)/[^/]+\.xml$', n):
            for t in re.findall(r'<a:t>(.*?)</a:t>', b.decode('utf-8', 'ignore'), re.S):
                text_chars.update(t)
    embed_tfs = [t for t in sorted(typefaces) if t.lower() not in _SKIP_TYPEFACES]
    if not embed_tfs or not text_chars:
        return {'ok': False, 'reason': 'no embeddable typeface/text'}
    text = ''.join(text_chars)

    base_cache: dict[tuple, bytes] = {}
    part_bytes: dict[str, bytes] = {}
    rel_id: dict[str, str] = {}
    rels_name = 'ppt/_rels/presentation.xml.rels'
    rels_raw = blobs.get(rels_name, (b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                                     b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>')).decode('utf-8', 'ignore')
    existing_ids = [int(m) for m in re.findall(r'Id="rId(\d+)"', rels_raw)]
    next_rid = (max(existing_ids) + 1) if existing_ids else 1
    state = {'seq': 0, 'rid': next_rid}

    def _base(serif: bool, weight_kw: str):
        picked = _pick_file(serif, weight_kw)
        if picked is None:
            return None
        if picked not in base_cache:
            data = _subset_base(picked[0], picked[1], text)
            if not data:
                return None
            base_cache[picked] = data
        return base_cache[picked]

    def _make_part(family: str, serif: bool, weight_kw: str, bold: bool):
        base = _base(serif, weight_kw)
        if base is None:
            return None
        data = _named_part(base, family, bold)
        if not data:
            return None
        state['seq'] += 1
        part = f"ppt/fonts/font{state['seq']}.fntdata"
        part_bytes[part] = data
        rel_id[part] = f"rId{state['rid']}"
        state['rid'] += 1
        return part

    # 每个 typeface 单独成份，内部 name 改成与声明一致。
    # 只给"基础字重"名补 bold 槽；已带字重的名(Bold/Light/SemiBold…)只嵌 regular，省体积。
    embedded: list[tuple] = []
    for tf in embed_tfs:
        serif = _is_serif(tf)
        wk = _detect_weight(tf)
        reg_part = _make_part(tf, serif, wk, bold=False)
        if reg_part is None:
            continue
        bold_part = _make_part(tf, serif, 'bold', bold=True) if wk in ('regular', 'normal') else None
        embedded.append((tf, reg_part, bold_part))
    if not embedded:
        return {'ok': False, 'reason': 'no embeddable font'}

    for part, data in part_bytes.items():
        blobs[part] = data

    add_rels = ''.join(
        f'<Relationship Id="{rid}" Type="{_R}/font" Target="fonts/{Path(part).name}"/>'
        for part, rid in rel_id.items()
    )
    blobs[rels_name] = rels_raw.replace('</Relationships>', add_rels + '</Relationships>').encode('utf-8')

    pres = blobs[pres_name].decode('utf-8', 'ignore')
    lst = ['<p:embeddedFontLst>']
    for tf, reg, bold in embedded:
        ent = [f'<p:embeddedFont><p:font typeface="{_xml_escape(tf)}"/><p:regular r:id="{rel_id[reg]}"/>']
        if bold:
            ent.append(f'<p:bold r:id="{rel_id[bold]}"/>')
        ent.append('</p:embeddedFont>')
        lst.append(''.join(ent))
    lst.append('</p:embeddedFontLst>')
    block = ''.join(lst)

    if 'embedTrueTypeFonts' not in pres:
        pres = re.sub(r'(<p:presentation\b)', r'\1 embedTrueTypeFonts="1"', pres, count=1)
    if '</p:notesSz>' in pres:
        pres = pres.replace('</p:notesSz>', '</p:notesSz>' + block, 1)
    elif re.search(r'<p:notesSz\b[^>]*/>', pres):
        pres = re.sub(r'(<p:notesSz\b[^>]*/>)', r'\1' + block, pres, count=1)
    elif re.search(r'<p:sldSz\b[^>]*/>', pres):
        pres = re.sub(r'(<p:sldSz\b[^>]*/>)', r'\1' + block, pres, count=1)
    else:
        return {'ok': False, 'reason': 'no insertion point'}
    blobs[pres_name] = pres.encode('utf-8')

    ct_name = '[Content_Types].xml'
    ct = blobs[ct_name].decode('utf-8', 'ignore')
    if 'Extension="fntdata"' not in ct:
        ct = ct.replace('</Types>', '<Default Extension="fntdata" ContentType="application/x-fontdata"/></Types>')
        blobs[ct_name] = ct.encode('utf-8')

    ordered = sorted(blobs.keys(), key=lambda n: (n != '[Content_Types].xml', n))
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for n in ordered:
            zout.writestr(n, blobs[n])
    return {'ok': True, 'typefaces': len(typefaces), 'embedded': len(embedded),
            'font_parts': len(part_bytes), 'glyphs': len(text_chars),
            'added_bytes': sum(len(b) for b in part_bytes.values())}


def main() -> int:
    ap = argparse.ArgumentParser(description='Embed subset fonts into a pptx for portable rendering.')
    ap.add_argument('pptx')
    ap.add_argument('--in-place', action='store_true')
    ap.add_argument('--out')
    args = ap.parse_args()

    src = Path(args.pptx)
    if not src.exists():
        print(f'文件不存在: {src}', file=sys.stderr)
        return 1
    dst = src.with_suffix('.embedtmp.pptx')
    try:
        rep = embed(src, dst)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({'ok': False, 'reason': f'{type(e).__name__}: {e}'}, ensure_ascii=False))
        if dst.exists():
            dst.unlink()
        return 0
    if not rep.get('ok'):
        if dst.exists():
            dst.unlink()
        print(json.dumps(rep, ensure_ascii=False))
        return 0
    if args.in_place:
        dst.replace(src)
    elif args.out:
        dst.replace(Path(args.out))
    else:
        dst.replace(src.with_suffix('.embed.pptx'))
    print(json.dumps(rep, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
