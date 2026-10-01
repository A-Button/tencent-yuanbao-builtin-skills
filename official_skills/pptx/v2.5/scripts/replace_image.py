#!/usr/bin/env python3
"""把生成好的图片替换到模板「已有图片位」上——即替换某个 <p:pic> 引用的媒体。

设计原则：只替换模板里**已存在**的图片位，绝不新增 <p:pic>、绝不改其位置/尺寸，
也不会创建背景图。这样既能换上贴合内容的插图，又不破坏模板版式。

工作于「解包后的目录」（unpack.py 产物）。

列出某页的图片位：
    python replace_image.py list <unpacked_dir> --slide 5

替换第 5 页第 1 个图片位为本地图片：
    python replace_image.py set <unpacked_dir> --slide 5 --index 1 --image /path/new.png

说明：
- index 从 1 开始，按 <p:pic> 在该页 XML 中出现的顺序。
- 新图写入 ppt/media/ 并更新该页 rels 的 r:embed 目标，原图保持其它引用不变。
"""

from __future__ import annotations

import argparse
import re
import shutil
import struct
import sys
import tempfile

from pathlib import Path
from xml.etree import ElementTree as ET


_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
_REL_NS = 'http://schemas.openxmlformats.org/package/2006/relationships'

try:
    from ooxml_ns import register_all as _reg_ns
    _reg_ns()
except Exception:
    pass

_EMU_PER_INCH = 914400.0


def _pic_frame_ext(slide_path: Path, index: int) -> tuple[int, int] | None:
    """读取第 index 个图片位的框尺寸（cx, cy，EMU），用于按展示尺寸降分辨率。"""
    try:
        root = ET.parse(slide_path).getroot()
    except ET.ParseError:
        return None
    pics = list(root.iter(f'{{{_P}}}pic'))
    if index < 1 or index > len(pics):
        return None
    ext = pics[index - 1].find(f'.//{{{_P}}}spPr/{{{_A}}}xfrm/{{{_A}}}ext')
    if ext is None:
        return None
    try:
        return int(ext.get('cx', '0')), int(ext.get('cy', '0'))
    except (TypeError, ValueError):
        return None


def _pic_rot(slide_path: Path, index: int) -> int:
    """读取第 index 个图片位 xfrm 的旋转角，归一化为 0/90/180/270（顺时针度）。

    PPT rot 单位是 1/60000 度，顺时针为正。非正交角（非 90 的倍数）返回 0（不处理）。
    """
    try:
        root = ET.parse(slide_path).getroot()
    except ET.ParseError:
        return 0
    pics = list(root.iter(f'{{{_P}}}pic'))
    if index < 1 or index > len(pics):
        return 0
    xfrm = pics[index - 1].find(f'.//{{{_P}}}spPr/{{{_A}}}xfrm')
    if xfrm is None:
        return 0
    try:
        deg = round(int(xfrm.get('rot', '0')) / 60000) % 360
    except (TypeError, ValueError):
        return 0
    return deg if deg in (90, 180, 270) else 0


def _optimize_for_frame(src: Path, frame: tuple[int, int] | None, workdir: Path,
                        dpi: int, max_edge: int, quality: int, rot: int = 0) -> Path | None:
    """按图片位展示尺寸降分辨率 + 重压缩；不透明图转 JPEG。失败/无 PIL 返回 None。

    - 目标长边 = min(原图长边, max_edge, 框长边@dpi×1.3)（cover 裁剪留些余量），仅缩小不放大。
    - 有 alpha → 保留 PNG（缩放+optimize）；无 alpha → 转 JPEG(quality)。
    - rot：图片位 xfrm 自带的旋转角（顺时针度，0/90/180/270）。模板有些相框是斜放的，
      普通照片直接插进去会被一起转歪；这里**预先反向旋转源图**，让最终显示为正。
      预旋转后位图朝向变了，后续 cover-fit 仍按 ext(cx,cy) 计算（srcRect 在旋转前的位图空间生效）。
    """
    try:
        from PIL import Image, ImageOps
    except Exception:
        return None
    try:
        im = Image.open(src)
        im.load()
    except Exception:
        return None
    # 先按 EXIF 方向校正（有些相机图自带 orientation），避免再叠加旋转出错。
    try:
        im = ImageOps.exif_transpose(im)
    except Exception:
        pass
    w, h = im.size
    if w <= 0 or h <= 0:
        return None
    if frame and frame[0] and frame[1]:
        frame_long = max(frame[0], frame[1]) / _EMU_PER_INCH * dpi * 1.3
    else:
        frame_long = float(max_edge)
    target_long = min(float(max(w, h)), float(max_edge), max(frame_long, 64.0))
    ratio = target_long / max(w, h)
    if ratio < 1.0:
        im = im.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
    # 反向旋转抵消图位旋转：rot=270°(CW) → 预旋 90°CW(ROTATE_270)；rot=90° → 预旋 270°CW(ROTATE_90)。
    if rot == 270:
        im = im.transpose(Image.ROTATE_270)
    elif rot == 90:
        im = im.transpose(Image.ROTATE_90)
    elif rot == 180:
        im = im.transpose(Image.ROTATE_180)
    # 仅"真实半透明"才保留 PNG；RGBA 但整张不透明的图转 JPEG 更省。
    has_alpha = False
    if im.mode in ('RGBA', 'LA'):
        try:
            has_alpha = im.getchannel('A').getextrema()[0] < 255
        except (ValueError, KeyError):
            has_alpha = True
    elif im.mode == 'PA' or (im.mode == 'P' and 'transparency' in im.info):
        has_alpha = True
    try:
        if has_alpha:
            out = workdir / 'opt.png'
            im.convert('RGBA').save(out, 'PNG', optimize=True)
        else:
            out = workdir / 'opt.jpg'
            im.convert('RGB').save(out, 'JPEG', quality=quality, optimize=True)
    except Exception:
        return None
    return out


def _image_size(path: Path) -> tuple[int, int] | None:
    """纯 stdlib 读取常见图片的像素宽高（png/jpeg/gif/bmp/webp），失败返回 None。"""
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if len(data) < 24:
        return None
    # PNG
    if data[:8] == b'\x89PNG\r\n\x1a\n':
        w, h = struct.unpack('>II', data[16:24])
        return int(w), int(h)
    # GIF
    if data[:6] in (b'GIF87a', b'GIF89a'):
        w, h = struct.unpack('<HH', data[6:10])
        return int(w), int(h)
    # BMP
    if data[:2] == b'BM':
        w, h = struct.unpack('<ii', data[18:26])
        return abs(int(w)), abs(int(h))
    # WEBP (RIFF)
    if data[:4] == b'RIFF' and data[8:12] == b'WEBP':
        fmt = data[12:16]
        try:
            if fmt == b'VP8 ':
                w = struct.unpack('<H', data[26:28])[0] & 0x3FFF
                h = struct.unpack('<H', data[28:30])[0] & 0x3FFF
                return int(w), int(h)
            if fmt == b'VP8L':
                b0, b1, b2, b3 = data[21], data[22], data[23], data[24]
                w = ((b1 & 0x3F) << 8 | b0) + 1
                h = ((b3 & 0x0F) << 10 | b2 << 2 | (b1 & 0xC0) >> 6) + 1
                return int(w), int(h)
            if fmt == b'VP8X':
                w = (data[24] | data[25] << 8 | data[26] << 16) + 1
                h = (data[27] | data[28] << 8 | data[29] << 16) + 1
                return int(w), int(h)
        except (struct.error, IndexError):
            return None
    # JPEG
    if data[:2] == b'\xff\xd8':
        i = 2
        n = len(data)
        while i + 9 < n:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                          0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                h, w = struct.unpack('>HH', data[i + 5:i + 9])
                return int(w), int(h)
            if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
                i += 2
                continue
            seg = struct.unpack('>H', data[i + 2:i + 4])[0]
            i += 2 + seg
    return None


def _cover_srcrect(img_w: int, img_h: int, frame_cx: int, frame_cy: int) -> dict | None:
    """计算把图片按 cover 方式填入框所需的裁剪（srcRect，单位 1/1000 %）。

    返回 {'l','t','r','b'}；无需裁剪返回 None。
    """
    if img_w <= 0 or img_h <= 0 or frame_cx <= 0 or frame_cy <= 0:
        return None
    img_ar = img_w / img_h
    frame_ar = frame_cx / frame_cy
    rect = {'l': 0, 't': 0, 'r': 0, 'b': 0}
    if abs(img_ar - frame_ar) < 1e-3:
        return None
    if img_ar > frame_ar:
        # 图片更宽 → 裁左右
        crop = 1.0 - frame_ar / img_ar
        side = int(round(crop / 2 * 100000))
        rect['l'] = rect['r'] = max(0, min(side, 49999))
    else:
        # 图片更高 → 裁上下
        crop = 1.0 - img_ar / frame_ar
        side = int(round(crop / 2 * 100000))
        rect['t'] = rect['b'] = max(0, min(side, 49999))
    if rect['l'] == 0 and rect['t'] == 0:
        return None
    return rect


def _slide_xml(unpacked: Path, slide: int) -> Path:
    p = unpacked / 'ppt' / 'slides' / f'slide{slide}.xml'
    if not p.exists():
        sys.exit(f'找不到 {p}')
    return p


def _rels_path(unpacked: Path, slide: int) -> Path:
    return unpacked / 'ppt' / 'slides' / '_rels' / f'slide{slide}.xml.rels'


def _list_pics(slide_path: Path) -> list[dict]:
    """返回该页 <p:pic> 列表：{index, name, embed(r:embed id), desc}。"""
    ET.register_namespace('a', _A)
    ET.register_namespace('p', _P)
    ET.register_namespace('r', _R)
    tree = ET.parse(slide_path)
    root = tree.getroot()
    pics = []
    for i, pic in enumerate(root.iter(f'{{{_P}}}pic'), start=1):
        name = ''
        nv = pic.find(f'.//{{{_P}}}cNvPr')
        if nv is not None:
            name = nv.get('name', '')
        blip = pic.find(f'.//{{{_A}}}blip')
        embed = blip.get(f'{{{_R}}}embed') if blip is not None else None
        pics.append({'index': i, 'name': name, 'embed': embed})
    return pics


def _resolve_media_target(rels_path: Path, embed_id: str) -> str | None:
    if not rels_path.exists():
        return None
    tree = ET.parse(rels_path)
    for rel in tree.getroot():
        if rel.get('Id') == embed_id:
            return rel.get('Target')  # e.g. ../media/image3.jpeg
    return None


def cmd_list(args) -> int:
    unpacked = Path(args.unpacked)
    pics = _list_pics(_slide_xml(unpacked, args.slide))
    if not pics:
        print(f'第 {args.slide} 页没有图片位（<p:pic>）。')
        return 0
    rels = _rels_path(unpacked, args.slide)
    print(f'第 {args.slide} 页共有 {len(pics)} 个图片位：')
    for p in pics:
        target = _resolve_media_target(rels, p['embed']) if p['embed'] else None
        print(f"  #{p['index']}  name={p['name']!r}  embed={p['embed']}  media={target}")
    return 0


def _unique_media_name(media_dir: Path, suffix: str) -> str:
    """在 ppt/media 下生成一个不与现有文件冲突的新媒体名（避免覆盖共享原图）。"""
    import uuid
    for _ in range(50):
        name = f'img_{uuid.uuid4().hex[:10]}{suffix}'
        if not (media_dir / name).exists():
            return name
    return f'img_{uuid.uuid4().hex}{suffix}'


def _download_to_temp(url: str) -> Path | None:
    """把 http(s) 图片下载到临时文件，按 Content-Type / 字节魔数定扩展名。失败返回 None。"""
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            ctype = (resp.headers.get('Content-Type') or '').lower()
    except Exception:
        return None
    if not data:
        return None
    if 'png' in ctype or data[:8] == b'\x89PNG\r\n\x1a\n':
        suffix = '.png'
    elif 'jpeg' in ctype or 'jpg' in ctype or data[:2] == b'\xff\xd8':
        suffix = '.jpg'
    elif 'webp' in ctype or (data[:4] == b'RIFF' and data[8:12] == b'WEBP'):
        suffix = '.webp'
    else:
        suffix = '.png'
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(data)
    tmp.close()
    return Path(tmp.name)


def cmd_set(args) -> int:
    unpacked = Path(args.unpacked)
    dl_tmp: Path | None = None
    if re.match(r'https?://', str(args.image), re.IGNORECASE):
        dl_tmp = _download_to_temp(args.image)
        if dl_tmp is None:
            sys.exit(f'下载图片失败: {args.image}')
        img = dl_tmp
    else:
        img = Path(args.image)
        if not img.exists():
            sys.exit(f'图片不存在: {img}')
    try:
        return _cmd_set_impl(args, unpacked, img)
    finally:
        if dl_tmp is not None:
            try:
                dl_tmp.unlink()
            except OSError:
                pass


def _cmd_set_impl(args, unpacked: Path, img: Path) -> int:
    slide_path = _slide_xml(unpacked, args.slide)
    pics = _list_pics(slide_path)
    match = next((p for p in pics if p['index'] == args.index), None)
    if match is None:
        sys.exit(f'第 {args.slide} 页没有第 {args.index} 个图片位（共有 {len(pics)} 个）。'
                 f'本技能不新增图片位，请选择已有的图片位。')
    embed_id = match['embed']
    if not embed_id:
        sys.exit(f'图片位 #{args.index} 缺少 r:embed，无法替换。')

    rels_path = _rels_path(unpacked, args.slide)
    target = _resolve_media_target(rels_path, embed_id)
    if not target:
        sys.exit(f'在 {rels_path.name} 中找不到 {embed_id} 对应的媒体。')

    # 目标媒体绝对路径： ppt/slides/../media/imageN.ext → ppt/media/imageN.ext
    media_rel = (slide_path.parent / target).resolve()
    media_dir = unpacked / 'ppt' / 'media'
    media_dir.mkdir(parents=True, exist_ok=True)

    # 防膨胀：按图片位展示尺寸把源图降分辨率 + 重压缩（不透明转 JPEG），再写入。
    # 同时按图位自带旋转反向预旋源图，保证最终显示为正（修"照片被转 90°"）。
    rot = _pic_rot(slide_path, args.index)
    with tempfile.TemporaryDirectory() as td:
        img_eff = img
        if not getattr(args, 'no_optimize', False):
            frame = _pic_frame_ext(slide_path, args.index)
            opt = _optimize_for_frame(img, frame, Path(td), args.dpi, args.max_edge, args.quality, rot)
            if opt is not None:
                img_eff = opt
        if rot:
            print(f'图片位 #{args.index} 自带旋转 {rot}°，已反向预旋源图使显示为正。')

        # 关键：**总是写入唯一的新媒体文件**，只改当前图位的 rels，绝不就地覆盖原媒体。
        # 模板常把同一张图共享给多个图位（同一 image1.jpeg 被多页引用），就地覆盖会
        # "一改全改"——这正是之前所有图位显示同一张图（清一色）的根因。
        new_suffix = img_eff.suffix.lower()
        new_name = _unique_media_name(media_dir, new_suffix)
        shutil.copyfile(img_eff, media_dir / new_name)
        _update_rel_target(rels_path, embed_id, f'../media/{new_name}')
        _ensure_content_type(unpacked, new_suffix)
        print(f'已替换图片位 #{args.index}：写入独立媒体 {new_name}（不动其它图位共享的原图）。')

        # 自适应：按图片框纵横比对源图做 cover 居中裁剪，避免被拉伸/压扁（反馈 row10）
        fit = getattr(args, 'fit', 'cover')
        if fit == 'cover':
            msg = _apply_cover_fit(slide_path, args.index, img_eff)
            if msg:
                print(msg)
    return 0


def _apply_cover_fit(slide_path: Path, index: int, img: Path) -> str | None:
    size = _image_size(img)
    if not size:
        return f'提示：无法读取图片尺寸，跳过自适应裁剪（图片位 #{index}）。'
    img_w, img_h = size
    ET.register_namespace('a', _A)
    ET.register_namespace('p', _P)
    ET.register_namespace('r', _R)
    tree = ET.parse(slide_path)
    root = tree.getroot()
    pics = list(root.iter(f'{{{_P}}}pic'))
    if index < 1 or index > len(pics):
        return None
    pic = pics[index - 1]
    ext = pic.find(f'.//{{{_P}}}spPr/{{{_A}}}xfrm/{{{_A}}}ext')
    if ext is None:
        return None
    try:
        cx = int(ext.get('cx', '0'))
        cy = int(ext.get('cy', '0'))
    except (TypeError, ValueError):
        return None
    rect = _cover_srcrect(img_w, img_h, cx, cy)
    blip_fill = pic.find(f'{{{_P}}}blipFill')
    if blip_fill is None:
        return None
    # 移除旧的 srcRect
    for old in blip_fill.findall(f'{{{_A}}}srcRect'):
        blip_fill.remove(old)
    if rect is None:
        # 纵横比一致，确保 stretch 填充即可
        _ensure_stretch(blip_fill)
        tree.write(slide_path, xml_declaration=True, encoding='UTF-8')
        return f'图片位 #{index}：纵横比匹配，无需裁剪。'
    src = ET.Element(f'{{{_A}}}srcRect')
    for k in ('l', 't', 'r', 'b'):
        if rect[k]:
            src.set(k, str(rect[k]))
    # srcRect 必须在 blip 之后、stretch/tile 之前
    blip = blip_fill.find(f'{{{_A}}}blip')
    if blip is not None:
        children = list(blip_fill)
        blip_fill.insert(children.index(blip) + 1, src)
    else:
        blip_fill.insert(0, src)
    _ensure_stretch(blip_fill)
    tree.write(slide_path, xml_declaration=True, encoding='UTF-8')
    pct = ', '.join(f'{k}={rect[k] / 1000:.1f}%' for k in ('l', 't', 'r', 'b') if rect[k])
    return f'图片位 #{index}：已按框比例 cover 裁剪（{pct}），避免拉伸。'


def _ensure_stretch(blip_fill: ET.Element) -> None:
    """保证 blipFill 用 stretch+fillRect 填满框（cover 配合 srcRect 才生效）。"""
    if blip_fill.find(f'{{{_A}}}tile') is not None:
        return  # 平铺是模板刻意设计，不动
    stretch = blip_fill.find(f'{{{_A}}}stretch')
    if stretch is None:
        stretch = ET.SubElement(blip_fill, f'{{{_A}}}stretch')
    if stretch.find(f'{{{_A}}}fillRect') is None:
        ET.SubElement(stretch, f'{{{_A}}}fillRect')


def _update_rel_target(rels_path: Path, embed_id: str, new_target: str) -> None:
    ET.register_namespace('', _REL_NS)
    tree = ET.parse(rels_path)
    for rel in tree.getroot():
        if rel.get('Id') == embed_id:
            rel.set('Target', new_target)
            break
    tree.write(rels_path, xml_declaration=True, encoding='UTF-8')


_CT_DEFAULTS = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.gif': 'image/gif', '.webp': 'image/webp', '.bmp': 'image/bmp',
}


def _ensure_content_type(unpacked: Path, suffix: str) -> None:
    ct_path = unpacked / '[Content_Types].xml'
    if not ct_path.exists():
        return
    ext = suffix.lstrip('.')
    text = ct_path.read_text(encoding='utf-8')
    if re.search(rf'Extension="{ext}"', text, re.IGNORECASE):
        return
    mime = _CT_DEFAULTS.get(suffix, 'application/octet-stream')
    insert = f'<Default Extension="{ext}" ContentType="{mime}"/>'
    text = text.replace('</Types>', insert + '</Types>')
    ct_path.write_text(text, encoding='utf-8')


def main() -> int:
    ap = argparse.ArgumentParser(description='替换模板中已有的图片位（不新增图片）。')
    sub = ap.add_subparsers(dest='cmd', required=True)

    pl = sub.add_parser('list', help='列出某页的图片位')
    pl.add_argument('unpacked')
    pl.add_argument('--slide', type=int, required=True)
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser('set', help='替换某页某个图片位')
    ps.add_argument('unpacked')
    ps.add_argument('--slide', type=int, required=True)
    ps.add_argument('--index', type=int, required=True)
    ps.add_argument('--image', required=True, help='本地路径或 http(s) 图片 URL（URL 会自动下载）')
    ps.add_argument('--fit', choices=['cover', 'none'], default='cover',
                    help='cover=按框纵横比居中裁剪避免拉伸（默认）；none=不裁剪')
    ps.add_argument('--dpi', type=int, default=150, help='降分辨率目标 DPI（默认 150）')
    ps.add_argument('--max-edge', type=int, default=2000, help='像素长边上限（默认 2000）')
    ps.add_argument('--quality', type=int, default=82, help='JPEG 质量（默认 82）')
    ps.add_argument('--no-optimize', action='store_true', help='跳过降分辨率/重压缩，原样写入')
    ps.set_defaults(func=cmd_set)

    args = ap.parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
