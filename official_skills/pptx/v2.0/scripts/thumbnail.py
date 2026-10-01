"""从 PowerPoint 演示文稿幻灯片生成缩略图网格。

将幻灯片按网格布局排列，便于快速预览。
每张缩略图标注对应的 XML 文件名（如 slide1.xml）。
隐藏幻灯片以占位图样式展示。

用法:
    python thumbnail.py input.pptx [output_prefix] [--cols N]

示例:
    python thumbnail.py presentation.pptx
    # 输出: thumbnails.jpg

    python thumbnail.py template.pptx grid --cols 4
    # 输出: grid.jpg（幻灯片较多时生成 grid-1.jpg, grid-2.jpg 等）
"""

import argparse
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import defusedxml.minidom
from office.soffice import get_soffice_env
from PIL import Image, ImageDraw, ImageFont

THUMB_WIDTH = 300
RENDER_DPI = 100
MAX_COLUMNS = 6
DEFAULT_COLUMNS = 3
JPG_QUALITY = 95
CELL_PADDING = 20
FRAME_WIDTH = 2
LABEL_SIZE_RATIO = 0.10
LABEL_MARGIN_RATIO = 0.4


def main():
    """入口函数：解析参数并执行缩略图网格生成流程。"""
    parser = argparse.ArgumentParser(
        description="从 PowerPoint 幻灯片生成缩略图网格。"
    )
    parser.add_argument("input", help="输入的 PowerPoint 文件（.pptx）")
    parser.add_argument(
        "output_prefix",
        nargs="?",
        default="thumbnails",
        help="输出图片文件的前缀（默认: thumbnails）",
    )
    parser.add_argument(
        "--cols",
        type=int,
        default=DEFAULT_COLUMNS,
        help=f"列数（默认: {DEFAULT_COLUMNS}，最大: {MAX_COLUMNS}）",
    )

    args = parser.parse_args()

    cols = min(args.cols, MAX_COLUMNS)
    if args.cols > MAX_COLUMNS:
        print(f"Warning: Columns limited to {MAX_COLUMNS}")

    input_path = Path(args.input)
    if not input_path.exists() or input_path.suffix.lower() != ".pptx":
        print(f"Error: Invalid PowerPoint file: {args.input}", file=sys.stderr)
        sys.exit(1)

    output_path = Path(f"{args.output_prefix}.jpg")

    try:
        slide_info = get_slide_info(input_path)

        with tempfile.TemporaryDirectory() as td:
            temp_path = Path(td)
            visible_images = convert_to_images(input_path, temp_path)

            has_hidden = any(s["hidden"] for s in slide_info)
            if not visible_images and not has_hidden:
                print("Error: No slides found", file=sys.stderr)
                sys.exit(1)

            slides = build_slide_list(slide_info, visible_images, temp_path)
            grid_files = create_grids(slides, cols, THUMB_WIDTH, output_path)

            print(f"Created {len(grid_files)} grid(s):")
            for gf in grid_files:
                print(f"  {gf}")

    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)


def get_slide_info(pptx_path: Path) -> list[dict]:
    """解析 PPTX 文件，返回幻灯片名称及是否隐藏的信息列表。"""
    with zipfile.ZipFile(pptx_path, "r") as zf:
        rels_xml = zf.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        rels_dom = defusedxml.minidom.parseString(rels_xml)

        rid_map = {}
        for rel in rels_dom.getElementsByTagName("Relationship"):
            rid = rel.getAttribute("Id")
            target = rel.getAttribute("Target")
            rtype = rel.getAttribute("Type")
            if "slide" in rtype and target.startswith("slides/"):
                rid_map[rid] = target.replace("slides/", "")

        pres_xml = zf.read("ppt/presentation.xml").decode("utf-8")
        pres_dom = defusedxml.minidom.parseString(pres_xml)

        result = []
        for sld_id in pres_dom.getElementsByTagName("p:sldId"):
            rid = sld_id.getAttribute("r:id")
            if rid not in rid_map:
                continue
            is_hidden = sld_id.getAttribute("show") == "0"
            result.append({"name": rid_map[rid], "hidden": is_hidden})

        return result


def build_slide_list(
    slide_info: list[dict],
    visible_images: list[Path],
    temp_dir: Path,
) -> list[tuple[Path, str]]:
    """将幻灯片信息与渲染图片对应，隐藏幻灯片使用占位图替代。"""
    if visible_images:
        with Image.open(visible_images[0]) as sample:
            placeholder_size = sample.size
    else:
        placeholder_size = (1920, 1080)

    result = []
    vis_cursor = 0

    for entry in slide_info:
        if entry["hidden"]:
            ph_path = temp_dir / f"hidden-{entry['name']}.jpg"
            ph_img = create_hidden_placeholder(placeholder_size)
            ph_img.save(ph_path, "JPEG")
            result.append((ph_path, f"{entry['name']} (hidden)"))
        else:
            if vis_cursor < len(visible_images):
                result.append((visible_images[vis_cursor], entry["name"]))
                vis_cursor += 1

    return result


def create_hidden_placeholder(size: tuple[int, int]) -> Image.Image:
    """生成指定尺寸的隐藏幻灯片占位图（灰底交叉线）。"""
    img = Image.new("RGB", size, color="#F0F0F0")
    draw = ImageDraw.Draw(img)
    stroke = max(5, min(size) // 100)
    draw.line([(0, 0), size], fill="#CCCCCC", width=stroke)
    draw.line([(size[0], 0), (0, size[1])], fill="#CCCCCC", width=stroke)
    return img


def convert_to_images(pptx_path: Path, temp_dir: Path) -> list[Path]:
    """将 PPTX 转换为 PDF，再将 PDF 各页导出为 JPEG 图片。"""
    pdf_path = temp_dir / f"{pptx_path.stem}.pdf"

    proc = subprocess.run(
        [
            "soffice",
            "--headless",
            "--convert-to",
            "pdf",
            "--outdir",
            str(temp_dir),
            str(pptx_path),
        ],
        capture_output=True,
        text=True,
        env=get_soffice_env(),
    )
    if proc.returncode != 0 or not pdf_path.exists():
        raise RuntimeError("PDF conversion failed")

    proc = subprocess.run(
        [
            "pdftoppm",
            "-jpeg",
            "-r",
            str(RENDER_DPI),
            str(pdf_path),
            str(temp_dir / "slide"),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError("Image conversion failed")

    return sorted(temp_dir.glob("slide-*.jpg"))


def create_grids(
    slides: list[tuple[Path, str]],
    cols: int,
    width: int,
    output_path: Path,
) -> list[str]:
    """按需将幻灯片分块，逐块生成网格图并保存为 JPEG 文件。"""
    capacity = cols * (cols + 1)
    saved_files = []

    for chunk_num, offset in enumerate(range(0, len(slides), capacity)):
        chunk = slides[offset : min(offset + capacity, len(slides))]
        grid_img = create_grid(chunk, cols, width)

        if len(slides) <= capacity:
            dest = output_path
        else:
            dest = output_path.parent / f"{output_path.stem}-{chunk_num + 1}{output_path.suffix}"

        dest.parent.mkdir(parents=True, exist_ok=True)
        grid_img.save(str(dest), quality=JPG_QUALITY)
        saved_files.append(str(dest))

    return saved_files


def create_grid(
    slides: list[tuple[Path, str]],
    cols: int,
    width: int,
) -> Image.Image:
    """将一组幻灯片缩略图拼合为带标签的网格图片。"""
    font_size = int(width * LABEL_SIZE_RATIO)
    label_margin = int(font_size * LABEL_MARGIN_RATIO)

    with Image.open(slides[0][0]) as first:
        aspect = first.height / first.width
    height = int(width * aspect)

    num_rows = (len(slides) + cols - 1) // cols
    cell_h = height + font_size + label_margin * 2
    grid_w = cols * width + (cols + 1) * CELL_PADDING
    grid_h = num_rows * cell_h + (num_rows + 1) * CELL_PADDING

    canvas = Image.new("RGB", (grid_w, grid_h), "white")
    draw = ImageDraw.Draw(canvas)

    try:
        font = ImageFont.load_default(size=font_size)
    except Exception:
        font = ImageFont.load_default()

    for idx, (img_path, slide_name) in enumerate(slides):
        row = idx // cols
        col = idx % cols
        x = col * width + (col + 1) * CELL_PADDING
        y_base = row * cell_h + (row + 1) * CELL_PADDING

        bbox = draw.textbbox((0, 0), slide_name, font=font)
        text_w = bbox[2] - bbox[0]
        draw.text(
            (x + (width - text_w) // 2, y_base + label_margin),
            slide_name,
            fill="black",
            font=font,
        )

        y_thumb = y_base + label_margin + font_size + label_margin

        with Image.open(img_path) as img:
            img.thumbnail((width, height), Image.Resampling.LANCZOS)
            w, h = img.size
            tx = x + (width - w) // 2
            ty = y_thumb + (height - h) // 2
            canvas.paste(img, (tx, ty))

            if FRAME_WIDTH > 0:
                draw.rectangle(
                    [
                        (tx - FRAME_WIDTH, ty - FRAME_WIDTH),
                        (tx + w + FRAME_WIDTH - 1, ty + h + FRAME_WIDTH - 1),
                    ],
                    outline="gray",
                    width=FRAME_WIDTH,
                )

    return canvas


if __name__ == "__main__":
    main()
