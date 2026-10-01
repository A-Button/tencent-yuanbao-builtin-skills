#!/usr/bin/env python3
"""结构完整性 advisory：提醒缺少封面/目录/过渡/结尾页。

结构完整性带强主观性（短副本本就不需要目录/过渡），强行 blocking 会误杀，故本检查
**只产出 advisory（warning），不阻断交付**——真正的约束写在 SKILL 工作流里，由模型在
规划阶段保证。这里只在成品明显偏离时给模型一个可执行的提醒。

判定（仅对 ≥ 阈值页数的副本提示，避免打扰小副本）：
- 封面：首页应是标题页（文字精炼）；首页文字过密则提示。
- 目录：≥8 页却无"目录/CONTENTS/AGENDA/大纲"页则提示。
- 过渡：≥10 页却无任何"分节过渡页"（极短文字页）则提示。
- 结尾：末页无"谢谢/感谢/THANKS/Q&A/联系"等收尾语则提示。
"""

from __future__ import annotations

import argparse
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_REL = 'http://schemas.openxmlformats.org/package/2006/relationships'

_TOC_RE = re.compile(r'目\s*录|CONTENT|AGENDA|大纲|目次', re.I)
_END_RE = re.compile(r'谢谢|感谢|THANK|Q\s*&\s*A|敬请|联系我们|期待|完$|完[!！]|结束|the\s*end', re.I)

_MIN_TOC = 8
_MIN_TRANSITION = 10


def _presentation_order(z: zipfile.ZipFile) -> list[int]:
    try:
        pres = z.read('ppt/presentation.xml')
        rels = z.read('ppt/_rels/presentation.xml.rels')
    except KeyError:
        return []
    rid_to_slide: dict[str, int] = {}
    try:
        for rel in ET.fromstring(rels).iter(f'{{{_REL}}}Relationship'):
            m = re.search(r'slides/slide(\d+)\.xml$', rel.get('Target', ''))
            if m:
                rid_to_slide[rel.get('Id', '')] = int(m.group(1))
    except ET.ParseError:
        return []
    order: list[int] = []
    try:
        for sld in ET.fromstring(pres).iter(f'{{{_P}}}sldId'):
            rid = sld.get(f'{{{_R}}}id')
            if rid in rid_to_slide:
                order.append(rid_to_slide[rid])
    except ET.ParseError:
        return []
    return order


def _slide_text(z: zipfile.ZipFile, n: int) -> tuple[str, int]:
    """返回 (合并文本, 文本框数)。"""
    try:
        root = ET.fromstring(z.read(f'ppt/slides/slide{n}.xml'))
    except (KeyError, ET.ParseError):
        return '', 0
    texts = []
    shapes = 0
    for sp in root.iter(f'{{{_P}}}sp'):
        t = ''.join(x.text or '' for x in sp.iter(f'{{{_A}}}t')).strip()
        if t:
            texts.append(t)
            shapes += 1
    return '\n'.join(texts), shapes


def check(final_pptx: str) -> dict:
    advisories: list[dict] = []
    try:
        z = zipfile.ZipFile(final_pptx)
    except (zipfile.BadZipFile, OSError) as e:
        return {'advisory_count': 0, 'advisories': [], 'note': f'无法读取: {e}'}

    order = _presentation_order(z)
    if not order:
        order = sorted(int(re.findall(r'\d+', n)[0]) for n in z.namelist()
                       if re.fullmatch(r'ppt/slides/slide\d+\.xml', n))
    n = len(order)
    if n < 4:
        z.close()
        return {'advisory_count': 0, 'advisories': [], 'slide_count': n}

    texts = [(s, *_slide_text(z, s)) for s in order]
    z.close()
    all_text = '\n'.join(t for _, t, _ in texts)

    # 封面：首页文字过密（多个文本框且总字数偏多）多半不是封面
    first_txt, first_shapes = texts[0][1], texts[0][2]
    if first_shapes >= 5 and len(first_txt) > 120:
        advisories.append({'type': 'cover', 'severity': 'warning',
                           'detail': '首页文字偏密，疑似不是封面页；建议首页用简洁的标题/副标题封面。'})

    # 目录
    if n >= _MIN_TOC and not _TOC_RE.search(all_text):
        advisories.append({'type': 'toc', 'severity': 'warning',
                           'detail': f'共 {n} 页但未发现目录/CONTENTS 页；建议加一页目录并与正文章节一致。'})

    # 过渡（分节）：极短文字页（除首末页）
    transitions = sum(1 for s, t, sh in texts[1:-1] if 0 < len(t) <= 30)
    if n >= _MIN_TRANSITION and transitions == 0:
        advisories.append({'type': 'transition', 'severity': 'warning',
                           'detail': f'共 {n} 页但无分节过渡页；建议在章节之间加简短过渡页。'})

    # 结尾
    last_txt = texts[-1][1]
    if not _END_RE.search(last_txt):
        advisories.append({'type': 'closing', 'severity': 'warning',
                           'detail': '末页无明显收尾语（谢谢/Q&A/联系方式等）；建议加一页结尾。'})

    return {'advisory_count': len(advisories), 'advisories': advisories, 'slide_count': n}


def main() -> int:
    ap = argparse.ArgumentParser(description='Structure completeness advisory (non-blocking).')
    ap.add_argument('pptx')
    ap.add_argument('--report', help='把 JSON 报告写到该路径')
    args = ap.parse_args()
    report = check(args.pptx)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding='utf-8')
    print(text)
    return 0  # advisory 永不阻断


if __name__ == '__main__':
    raise SystemExit(main())
