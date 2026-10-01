"""
从不可填充的 PDF 中提取表单结构。

分析 PDF 以找到：
- 文本标签及其精确坐标
- 水平线（行边界）
- 复选框（小矩形）

输出 JSON 文件，可用于生成准确的字段坐标以进行表单填写。

用法: python analyze_pdf_structure.py <输入PDF> <输出JSON>
"""

import json
import sys
import pdfplumber


def parse_structure(src_pdf):
    result = {
        "pages": [],
        "labels": [],
        "lines": [],
        "checkboxes": [],
        "row_boundaries": []
    }

    with pdfplumber.open(src_pdf) as pdf:
        for pg_num, page in enumerate(pdf.pages, 1):
            result["pages"].append({
                "page_number": pg_num,
                "width": float(page.width),
                "height": float(page.height)
            })

            text_items = page.extract_words()
            for w in text_items:
                result["labels"].append({
                    "page": pg_num,
                    "text": w["text"],
                    "x0": round(float(w["x0"]), 1),
                    "top": round(float(w["top"]), 1),
                    "x1": round(float(w["x1"]), 1),
                    "bottom": round(float(w["bottom"]), 1)
                })

            for ln in page.lines:
                if abs(float(ln["x1"]) - float(ln["x0"])) > page.width * 0.5:
                    result["lines"].append({
                        "page": pg_num,
                        "y": round(float(ln["top"]), 1),
                        "x0": round(float(ln["x0"]), 1),
                        "x1": round(float(ln["x1"]), 1)
                    })

            for r in page.rects:
                rw = float(r["x1"]) - float(r["x0"])
                rh = float(r["bottom"]) - float(r["top"])
                if 5 <= rw <= 15 and 5 <= rh <= 15 and abs(rw - rh) < 2:
                    result["checkboxes"].append({
                        "page": pg_num,
                        "x0": round(float(r["x0"]), 1),
                        "top": round(float(r["top"]), 1),
                        "x1": round(float(r["x1"]), 1),
                        "bottom": round(float(r["bottom"]), 1),
                        "center_x": round((float(r["x0"]) + float(r["x1"])) / 2, 1),
                        "center_y": round((float(r["top"]) + float(r["bottom"])) / 2, 1)
                    })

    page_lines = {}
    for ln in result["lines"]:
        pg = ln["page"]
        if pg not in page_lines:
            page_lines[pg] = []
        page_lines[pg].append(ln["y"])

    for pg, positions in page_lines.items():
        positions = sorted(set(positions))
        for i in range(len(positions) - 1):
            result["row_boundaries"].append({
                "page": pg,
                "row_top": positions[i],
                "row_bottom": positions[i + 1],
                "row_height": round(positions[i + 1] - positions[i], 1)
            })

    return result


def main():
    if len(sys.argv) != 3:
        print("用法: analyze_pdf_structure.py <输入PDF> <输出JSON>")
        sys.exit(1)

    src_pdf = sys.argv[1]
    out_path = sys.argv[2]

    print(f"正在分析 {src_pdf} 的结构...")
    data = parse_structure(src_pdf)

    with open(out_path, "w") as f:
        json.dump(data, f, indent=2)

    print(f"检测结果:")
    print(f"  - {len(data['pages'])} 页")
    print(f"  - {len(data['labels'])} 个文本标签")
    print(f"  - {len(data['lines'])} 条水平线")
    print(f"  - {len(data['checkboxes'])} 个复选框")
    print(f"  - {len(data['row_boundaries'])} 个行边界")
    print(f"已保存到 {out_path}")


if __name__ == "__main__":
    main()
