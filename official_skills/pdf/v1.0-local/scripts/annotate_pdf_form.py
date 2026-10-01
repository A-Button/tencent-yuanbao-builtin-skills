"""通过添加自由文本注释的方式填写不可填充的 PDF 表单。"""

import json
import sys

from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText


def image_to_pdf_coords(bbox, img_w, img_h, pdf_w, pdf_h):
    """将图片像素坐标转换为 PDF 坐标。"""
    sx = pdf_w / img_w
    sy = pdf_h / img_h

    left = bbox[0] * sx
    right = bbox[2] * sx
    top = pdf_h - (bbox[1] * sy)
    bottom = pdf_h - (bbox[3] * sy)

    return left, bottom, right, top


def normalize_pdf_coords(bbox, pdf_h):
    """将 PDF 坐标（y 向下）转换为 pypdf 所需的坐标格式。"""
    left = bbox[0]
    right = bbox[2]
    pypdf_top = pdf_h - bbox[1]
    pypdf_bottom = pdf_h - bbox[3]

    return left, pypdf_bottom, right, pypdf_top


def fill_with_annotations(src_pdf, fields_path, out_pdf):
    with open(fields_path, "r") as f:
        form_data = json.load(f)

    reader = PdfReader(src_pdf)
    writer = PdfWriter()
    writer.append(reader)

    page_sizes = {}
    for i, page in enumerate(reader.pages):
        mb = page.mediabox
        page_sizes[i + 1] = [mb.width, mb.height]

    added_items = []
    for field in form_data["form_fields"]:
        pg = field["page_number"]

        pg_info = next(p for p in form_data["pages"] if p["page_number"] == pg)
        pw, ph = page_sizes[pg]

        if "pdf_width" in pg_info:
            target_rect = normalize_pdf_coords(
                field["entry_bounding_box"],
                float(ph)
            )
        else:
            target_rect = image_to_pdf_coords(
                field["entry_bounding_box"],
                pg_info["image_width"], pg_info["image_height"],
                float(pw), float(ph)
            )

        if "entry_text" not in field or "text" not in field["entry_text"]:
            continue
        text_cfg = field["entry_text"]
        content = text_cfg["text"]
        if not content:
            continue

        font_name = text_cfg.get("font", "Arial")
        font_size = str(text_cfg.get("font_size", 14)) + "pt"
        font_color = text_cfg.get("font_color", "000000")

        ann = FreeText(
            text=content,
            rect=target_rect,
            font=font_name,
            font_size=font_size,
            font_color=font_color,
            border_color=None,
            background_color=None,
        )
        added_items.append(ann)
        writer.add_annotation(page_number=pg - 1, annotation=ann)

    with open(out_pdf, "wb") as output:
        writer.write(output)

    print(f"表单填写完成，已保存到 {out_pdf}")
    print(f"共添加 {len(added_items)} 个文本注释")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("用法: annotate_pdf_form.py [输入PDF] [fields.json] [输出PDF]")
        sys.exit(1)
    fill_with_annotations(sys.argv[1], sys.argv[2], sys.argv[3])
