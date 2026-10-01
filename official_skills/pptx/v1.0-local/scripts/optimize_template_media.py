#!/usr/bin/env python3
"""离线批量给 PPTX 模板媒体减肥（一次性工具，不在运行期热路径）。

模板自带超大无损 RGBA PNG 背景图（单张 7-8MB），每个成品都继承之，导致 20-40MB。
本工具对每个 .pptx：
  - 把 ppt/media 下的位图按长边上限降分辨率（仅缩小不放大）；
  - 不含 alpha 的图重编码为 JPEG(quality)；含 alpha 的 PNG 降分辨率 + optimize；
  - 重命名带来的扩展名变化，同步改写所有 .rels 的 Target 与 [Content_Types].xml；
  - 清理任何 rels 都未引用的孤儿 media（含孤儿 .wdp HD-Photo 副本）。

安全优先：被引用的 .wdp（艺术效果的 HD-Photo 副本）默认**保留**——删它需要同时改
blip 的 mc:AlternateContent 引用，易致损坏；其体积占比远小于 PNG，不强行处理。

用法：
  python optimize_template_media.py <pptx 或 目录> [--in-place [--backup]] [--out FILE]
                                     [--max-edge 2000] [--quality 82] [--dry-run]
默认对单文件输出 <name>.slim.pptx；目录则递归处理所有 *.pptx。
"""

from __future__ import annotations

import argparse
import io
import re
import shutil
import sys
import zipfile
from pathlib import Path

try:
    from PIL import Image
except Exception:  # noqa: BLE001
    Image = None

_RASTER_EXT = {'.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff', '.tif'}


def _has_real_alpha(im) -> bool:
    """是否含**真实**半透明：RGBA/LA 但 alpha 通道并非全 255 才算。

    很多模板背景图是 RGBA 却整张不透明（alpha 恒为 255），这类可安全转 JPEG 大幅瘦身。
    """
    if im.mode in ('RGBA', 'LA'):
        try:
            return im.getchannel('A').getextrema()[0] < 255
        except (ValueError, KeyError):
            return True
    if im.mode == 'PA':
        return True
    if im.mode == 'P' and 'transparency' in im.info:
        return True
    return False


def _reencode(data: bytes, name: str, max_edge: int, quality: int) -> tuple[bytes, str] | None:
    """返回 (新字节, 新扩展名) 或 None（无法处理/不值得）。"""
    if Image is None:
        return None
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception:
        return None
    w, h = im.size
    if w <= 0 or h <= 0:
        return None
    ratio = min(1.0, max_edge / float(max(w, h)))
    if ratio < 1.0:
        im = im.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
    buf = io.BytesIO()
    if _has_real_alpha(im):
        im.convert('RGBA').save(buf, 'PNG', optimize=True)
        new_ext = '.png'
    else:
        im.convert('RGB').save(buf, 'JPEG', quality=quality, optimize=True)
        new_ext = '.jpg'
    out = buf.getvalue()
    # 只有确实更小才采用，否则保留原图（避免把已优化的小图反而做大）。
    if len(out) >= len(data) and new_ext == Path(name).suffix.lower():
        return None
    if len(out) >= len(data):
        return None
    return out, new_ext


def _referenced_media(names, read) -> set[str]:
    """从所有 .rels 收集被引用的 media 文件名（basename）。"""
    refs: set[str] = set()
    for n in names:
        if not n.endswith('.rels'):
            continue
        raw = read(n).decode('utf-8', 'ignore')
        for t in re.findall(r'Target="([^"]+)"', raw):
            if 'media/' in t:
                refs.add(t.rsplit('/', 1)[-1])
    return refs


def optimize_pptx(src: Path, dst: Path, max_edge: int, quality: int) -> dict:
    zin = zipfile.ZipFile(src)
    names = zin.namelist()
    blobs = {n: zin.read(n) for n in names}
    zin.close()

    referenced = _referenced_media(names, lambda n: blobs[n])
    rename: dict[str, str] = {}      # old basename -> new basename
    drop: set[str] = set()           # 完整 archive 名
    before = sum(len(b) for n, b in blobs.items() if n.startswith('ppt/media/'))

    media_names = [n for n in names if n.startswith('ppt/media/')]
    for n in media_names:
        base = n.rsplit('/', 1)[-1]
        ext = Path(n).suffix.lower()
        # 孤儿 media（含孤儿 .wdp）直接删
        if base not in referenced:
            drop.add(n)
            continue
        if ext not in _RASTER_EXT:
            continue  # .wdp 等被引用的非位图：保留（删除有损坏风险）
        res = _reencode(blobs[n], n, max_edge, quality)
        if res is None:
            continue
        new_bytes, new_ext = res
        blobs[n] = new_bytes
        if new_ext != ext:
            new_base = Path(base).stem + new_ext
            rename[base] = new_base

    # 应用删除
    for n in drop:
        blobs.pop(n, None)

    # 应用重命名：改 media 的 archive 名 + 改写所有 rels Target
    if rename:
        for n in list(blobs.keys()):
            if n.startswith('ppt/media/'):
                base = n.rsplit('/', 1)[-1]
                if base in rename:
                    blobs[f'ppt/media/{rename[base]}'] = blobs.pop(n)
        for n in list(blobs.keys()):
            if n.endswith('.rels'):
                raw = blobs[n].decode('utf-8', 'ignore')
                for old, new in rename.items():
                    raw = raw.replace(f'media/{old}', f'media/{new}')
                blobs[n] = raw.encode('utf-8')
        # 确保 [Content_Types].xml 含新扩展名默认项
        ct_name = '[Content_Types].xml'
        if ct_name in blobs:
            ct = blobs[ct_name].decode('utf-8', 'ignore')
            for new in set(rename.values()):
                ext = Path(new).suffix.lstrip('.')
                if not re.search(rf'Extension="{ext}"', ct, re.IGNORECASE):
                    mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else f'image/{ext}'
                    ct = ct.replace('</Types>', f'<Default Extension="{ext}" ContentType="{mime}"/></Types>')
            blobs[ct_name] = ct.encode('utf-8')

    after = sum(len(b) for n, b in blobs.items() if n.startswith('ppt/media/'))

    # 重新打包（[Content_Types].xml 放最前是良好习惯）
    ordered = sorted(blobs.keys(), key=lambda n: (n != '[Content_Types].xml', n))
    dst.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dst, 'w', zipfile.ZIP_DEFLATED) as zout:
        for n in ordered:
            zout.writestr(n, blobs[n])
    return {'src': str(src), 'dst': str(dst), 'media_before': before, 'media_after': after,
            'reencoded': len(rename), 'dropped_orphans': len(drop)}


def main() -> int:
    ap = argparse.ArgumentParser(description='批量给 PPTX 模板媒体减肥。')
    ap.add_argument('path', help='单个 .pptx 或包含模板的目录')
    ap.add_argument('--in-place', action='store_true', help='就地覆盖（建议配 --backup）')
    ap.add_argument('--backup', action='store_true', help='就地模式下保留 <name>.pptx.bak')
    ap.add_argument('--out', help='单文件模式输出路径（默认 <name>.slim.pptx）')
    ap.add_argument('--max-edge', type=int, default=2000)
    ap.add_argument('--quality', type=int, default=82)
    ap.add_argument('--dry-run', action='store_true', help='只报告预计大小，不写文件')
    args = ap.parse_args()

    if Image is None:
        print('需要 Pillow：pip install Pillow', file=sys.stderr)
        return 1

    root = Path(args.path)
    files = sorted(root.rglob('*.pptx')) if root.is_dir() else [root]
    files = [f for f in files if f.is_file() and not f.name.endswith('.slim.pptx')]
    if not files:
        print('未找到 .pptx', file=sys.stderr)
        return 1

    total_before = total_after = 0
    for f in files:
        if args.dry_run:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.pptx', delete=True) as tmp:
                r = optimize_pptx(f, Path(tmp.name), args.max_edge, args.quality)
        elif args.in_place:
            if args.backup:
                shutil.copy2(f, f.with_suffix(f.suffix + '.bak'))
            import tempfile
            tmp = f.with_suffix('.slimtmp.pptx')
            r = optimize_pptx(f, tmp, args.max_edge, args.quality)
            tmp.replace(f)
            r['dst'] = str(f)
        else:
            out = Path(args.out) if (args.out and not root.is_dir()) else f.with_suffix('.slim.pptx')
            r = optimize_pptx(f, out, args.max_edge, args.quality)
        total_before += r['media_before']
        total_after += r['media_after']
        print(f"{f.name}: media {r['media_before']/1e6:.1f}MB -> {r['media_after']/1e6:.1f}MB "
              f"(reencoded={r['reencoded']}, dropped={r['dropped_orphans']})")
    print(f'合计 media: {total_before/1e6:.1f}MB -> {total_after/1e6:.1f}MB')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
