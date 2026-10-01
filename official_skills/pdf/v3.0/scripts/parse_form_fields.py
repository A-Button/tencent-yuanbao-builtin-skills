"""从可填充 PDF 中解析表单字段信息，输出为 JSON。"""

import json
import sys

from pypdf import PdfReader


def resolve_field_path(annotation):
    """沿父级链拼接完整的字段路径。"""
    parts = []
    while annotation:
        name = annotation.get('/T')
        if name:
            parts.append(name)
        annotation = annotation.get('/Parent')
    return ".".join(reversed(parts)) if parts else None


def build_field_info(raw_field, fid):
    """将 pypdf 字段对象转换为标准化的字段信息字典。"""
    info = {"field_id": fid}
    ft = raw_field.get('/FT')
    if ft == "/Tx":
        info["type"] = "text"
    elif ft == "/Btn":
        info["type"] = "checkbox"
        states = raw_field.get("/_States_", [])
        if len(states) == 2:
            if "/Off" in states:
                info["checked_value"] = states[0] if states[0] != "/Off" else states[1]
                info["unchecked_value"] = "/Off"
            else:
                print(f"复选框 `${fid}` 的状态值异常，勾选/取消勾选值可能不正确，请填写后手动验证结果。")
                info["checked_value"] = states[0]
                info["unchecked_value"] = states[1]
    elif ft == "/Ch":
        info["type"] = "choice"
        states = raw_field.get("/_States_", [])
        info["choice_options"] = [{
            "value": s[0],
            "text": s[1],
        } for s in states]
    else:
        info["type"] = f"unknown ({ft})"
    return info


def extract_fields(reader: PdfReader):
    """从 PDF 中提取所有表单字段及其位置信息。"""
    raw_fields = reader.get_fields()

    fields_map = {}
    radio_candidates = set()

    for fid, raw in raw_fields.items():
        if raw.get("/Kids"):
            if raw.get("/FT") == "/Btn":
                radio_candidates.add(fid)
            continue
        fields_map[fid] = build_field_info(raw, fid)

    radio_map = {}

    for pg_idx, page in enumerate(reader.pages):
        annots = page.get('/Annots', [])
        for ann in annots:
            fid = resolve_field_path(ann)
            if fid in fields_map:
                fields_map[fid]["page"] = pg_idx + 1
                fields_map[fid]["rect"] = ann.get('/Rect')
            elif fid in radio_candidates:
                try:
                    on_vals = [v for v in ann["/AP"]["/N"] if v != "/Off"]
                except KeyError:
                    continue
                if len(on_vals) == 1:
                    rect = ann.get("/Rect")
                    if fid not in radio_map:
                        radio_map[fid] = {
                            "field_id": fid,
                            "type": "radio_group",
                            "page": pg_idx + 1,
                            "radio_options": [],
                        }
                    radio_map[fid]["radio_options"].append({
                        "value": on_vals[0],
                        "rect": rect,
                    })

    located = []
    for item in fields_map.values():
        if "page" in item:
            located.append(item)
        else:
            print(f"无法确定字段 {item.get('field_id')} 的位置，已跳过")

    def field_sort_key(f):
        if "radio_options" in f:
            r = f["radio_options"][0]["rect"] or [0, 0, 0, 0]
        else:
            r = f.get("rect") or [0, 0, 0, 0]
        return [f.get("page"), [-r[1], r[0]]]

    result = located + list(radio_map.values())
    result.sort(key=field_sort_key)

    return result


def export_fields(pdf_path: str, output_path: str):
    reader = PdfReader(pdf_path)
    fields = extract_fields(reader)
    with open(output_path, "w") as f:
        json.dump(fields, f, indent=2)
    print(f"已导出 {len(fields)} 个字段到 {output_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("用法: parse_form_fields.py [输入PDF] [输出JSON]")
        sys.exit(1)
    export_fields(sys.argv[1], sys.argv[2])
