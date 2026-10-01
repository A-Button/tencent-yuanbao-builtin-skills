"""将 PDF 每一页转换为 PNG 图片。"""

import os
import sys

from pdf2image import convert_from_path


def render_pages(src_pdf, out_dir, max_size=1000):
    pages = convert_from_path(src_pdf, dpi=200)

    for idx, img in enumerate(pages):
        w, h = img.size
        if w > max_size or h > max_size:
            ratio = min(max_size / w, max_size / h)
            img = img.resize((int(w * ratio), int(h * ratio)))

        out_path = os.path.join(out_dir, f"page_{idx+1}.png")
        img.save(out_path)
        print(f"已保存第 {idx+1} 页: {out_path} (尺寸: {img.size})")

    print(f"共转换 {len(pages)} 页为 PNG 图片")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: pdf_to_images.py [输入PDF] [输出目录]")
        sys.exit(1)
    render_pages(sys.argv[1], sys.argv[2])
