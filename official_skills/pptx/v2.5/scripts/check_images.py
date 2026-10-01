#!/usr/bin/env python3
"""交付门：选中页里的"显著图位"必须换成主题图，不能留模板库存照片。

做法：把成品里每个 <p:pic> 的媒体字节做哈希，与**原模板**的媒体哈希集合比对。
若某图位的媒体仍命中模板原图、且该图位足够大（面积占比 ≥ 阈值），判定为
`untouched_template_image`（blocking）——提示模型用 image_generation 生成主题图后替换。

- 替换后的图经 replace_image 重压缩/旋转，哈希必然变化，不会被误判。
- 小图标/角标/装饰（面积占比 < 阈值）不计，避免误杀 logo。
- 仅看 pic 自身 spPr/xfrm/ext 的面积；组合内无绝对尺寸的 pic 跳过（多为装饰）。

退出码：有 blocking 返回 2，否则 0。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
import zipfile
from pathlib import Path

_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def _template_media_hashes(template: str) -> set[str]:
    hashes: set[str] = set()
    try:
        with zipfile.ZipFile(template) as z:
            for n in z.namelist():
                if n.startswith('ppt/media/') and not n.endswith('/'):
                    hashes.add(hashlib.md5(z.read(n)).hexdigest())
    except (zipfile.BadZipFile, OSError, KeyError):
        pass
    return hashes


def _slide_size(z: zipfile.ZipFile) -> tuple[int, int]:
    try:
        raw = z.read('ppt/presentation.xml').decode('utf-8', 'ignore')
        m = re.search(r'<p:sldSz[^>]*cx="(\d+)"[^>]*cy="(\d+)"', raw)
        if m:
            return int(m.group(1)), int(m.group(2))
    except KeyError:
        pass
    return 0, 0


def _rels_map(z: zipfile.ZipFile, slide_name: str) -> dict[str, str]:
    base = posixpath.dirname(slide_name)
    rels = f'{base}/_rels/{posixpath.basename(slide_name)}.rels'
    out: dict[str, str] = {}
    try:
        raw = z.read(rels).decode('utf-8', 'ignore')
    except KeyError:
        return out
    for rid, tgt in re.findall(r'Id="([^"]+)"[^>]*Target="([^"]+)"', raw):
        out[rid] = posixpath.normpath(posixpath.join(base, tgt))
    return out


def check(final_pptx: str, template: str, min_area_frac: float) -> dict:
    issues: list[dict] = []
    tpl_hashes = _template_media_hashes(template)
    try:
        z = zipfile.ZipFile(final_pptx)
    except (zipfile.BadZipFile, OSError) as e:
        return {'blocking_count': 0, 'issues': [], 'note': f'无法读取 {final_pptx}: {e}'}

    sx, sy = _slide_size(z)
    slide_area = sx * sy
    significant = 0
    slide_names = sorted(
        (n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+\.xml', n)),
        key=lambda n: int(re.findall(r'\d+', n)[0]),
    )
    for name in slide_names:
        raw = z.read(name).decode('utf-8', 'ignore')
        rmap = _rels_map(z, name)
        sn = int(re.findall(r'\d+', name)[0])
        # 逐个 <p:pic> 块切出来，拿它自己的 ext 与 blip embed
        for idx, block in enumerate(re.findall(r'<p:pic>.*?</p:pic>', raw, re.S), start=1):
            mext = re.search(r'<a:off[^>]*/>\s*<a:ext[^>]*cx="(\d+)"[^>]*cy="(\d+)"', block)
            if not mext:
                continue
            area = int(mext.group(1)) * int(mext.group(2))
            if not slide_area or area / slide_area < min_area_frac:
                continue
            significant += 1
            membed = re.search(r'<a:blip[^>]*r:embed="([^"]+)"', block)
            if not membed:
                continue
            media = rmap.get(membed.group(1))
            if not media:
                continue
            try:
                h = hashlib.md5(z.read(media)).hexdigest()
            except KeyError:
                continue
            if h in tpl_hashes:
                issues.append({
                    'severity': 'blocking', 'type': 'untouched_template_image',
                    'ref': f'slide{sn}:image{idx}',
                    'detail': f'第 {sn} 页第 {idx} 个图位仍是模板原图（占版面 {area/slide_area:.0%}）；'
                              '用 image_generation 生成贴合主题的图后替换该图位。',
                })
    z.close()
    blocking = sum(1 for i in issues if i['severity'] == 'blocking')
    return {'blocking_count': blocking, 'significant_pics': significant,
            'issue_count': len(issues), 'issues': issues}


def main() -> int:
    ap = argparse.ArgumentParser(description='Check selected-deck significant image slots were replaced.')
    ap.add_argument('final_pptx')
    ap.add_argument('--template', required=True, help='原模板 .pptx（用于媒体哈希基线）')
    ap.add_argument('--min-area-frac', type=float, default=0.06,
                    help='判定"显著图位"的最小面积占比（默认 0.06=6%%）')
    ap.add_argument('--report', help='把 JSON 报告写到该路径')
    args = ap.parse_args()

    report = check(args.final_pptx, args.template, args.min_area_frac)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding='utf-8')
    print(text)
    return 2 if report['blocking_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
