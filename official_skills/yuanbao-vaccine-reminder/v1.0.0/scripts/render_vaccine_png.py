#!/usr/bin/env python3
"""Render the vaccine HTML middleware into PNG views without a browser."""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import pymupdf
    from weasyprint import HTML
except Exception as exc:  # includes missing Pango/Cairo dynamic libraries
    raise RuntimeError(
        "缺少无浏览器出图依赖：weasyprint==70.0、pymupdf==1.28.2、"
        "Pango/Cairo 和中文字体。"
    ) from exc


CAPTURE_CSS = """
@page{size:1810px 2600px;margin:0}
body{background:#fff!important;font-family:"Noto Sans CJK SC","Noto Serif CJK SC",sans-serif!important}
.toolbar,.view-radio{display:none!important}.workspace{padding:0!important}
.paper{width:1810px!important;max-width:none!important;margin:0!important;padding:50px 44px 36px!important;box-shadow:none!important}
.scroll{overflow:visible!important}table{font-size:15px!important;min-width:0!important}
.legend{display:flex!important}.head h1{font-size:34px!important}
"""

VIEW_CSS = {
    "time": ".time-view{display:block!important}.vaccine-view{display:none!important}",
    "vaccine": ".vaccine-view{display:block!important}.time-view{display:none!important}",
}

ZOOM = 2.0


def crop_bbox(page, pad: float = 30.0):
    blocks = [block for block in page.get_text("blocks") if str(block[4]).strip()]
    bottom = max((block[3] for block in blocks), default=page.rect.height)
    return pymupdf.Rect(0, 0, page.rect.width, min(page.rect.height, bottom + pad))


def render(html_path: Path, view: str, out_path: Path) -> dict:
    if view not in VIEW_CSS:
        raise ValueError(f"不支持的视图: {view}")
    html = html_path.read_text(encoding="utf-8")
    html = html.replace(
        "@page{size:A3 landscape;margin:8mm}",
        "@page{size:1810px 2600px;margin:0}",
    )
    html = html.replace(
        "</head>",
        f"<style>{CAPTURE_CSS}{VIEW_CSS[view]}</style></head>",
    )
    temp_html = html_path.with_name(f"{html_path.stem}-{view}.html")
    temp_pdf = out_path.with_suffix(".pdf")
    temp_html.write_text(html, encoding="utf-8")
    try:
        HTML(filename=str(temp_html), base_url=str(html_path.parent)).write_pdf(str(temp_pdf))
        doc = pymupdf.open(str(temp_pdf))
        page = doc[0]
        pix = page.get_pixmap(
            matrix=pymupdf.Matrix(ZOOM, ZOOM),
            clip=crop_bbox(page),
            alpha=False,
        )
        pix.save(str(out_path))
        info = {"path": str(out_path.resolve()), "width": pix.width, "height": pix.height}
        doc.close()
        return info
    finally:
        temp_html.unlink(missing_ok=True)
        temp_pdf.unlink(missing_ok=True)


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit("usage: render_vaccine_png.py HTML OUTPUT_DIR [NAME]")
    source, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    name = sys.argv[3] if len(sys.argv) > 3 else "output"
    outdir.mkdir(parents=True, exist_ok=True)
    for view, suffix in (("time", "按时间"), ("vaccine", "按疫苗")):
        print(render(source, view, outdir / f"{name}-{suffix}.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
