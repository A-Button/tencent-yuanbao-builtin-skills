"""使用提取的字段信息填充可填充 PDF 表单。"""

import json
import sys

from pypdf import PdfReader, PdfWriter

from parse_form_fields import extract_fields


def fill_fields(src_pdf: str, values_path: str, out_pdf: str):
    with open(values_path) as f:
        entries = json.load(f)

    page_field_map = {}
    for entry in entries:
        if "value" in entry:
            fid = entry["field_id"]
            pg = entry["page"]
            if pg not in page_field_map:
                page_field_map[pg] = {}
            page_field_map[pg][fid] = entry["value"]

    reader = PdfReader(src_pdf)

    found_error = False
    known_fields = extract_fields(reader)
    field_lookup = {f["field_id"]: f for f in known_fields}
    for entry in entries:
        existing = field_lookup.get(entry["field_id"])
        if not existing:
            found_error = True
            print(f"错误: `{entry['field_id']}` 不是有效的字段 ID")
        elif entry["page"] != existing["page"]:
            found_error = True
            print(f"错误: `{entry['field_id']}` 的页码不正确（提供 {entry['page']}，应为 {existing['page']}）")
        else:
            if "value" in entry:
                err = check_field_value(existing, entry["value"])
                if err:
                    print(err)
                    found_error = True
    if found_error:
        sys.exit(1)

    writer = PdfWriter(clone_from=reader)
    for pg, vals in page_field_map.items():
        writer.update_page_form_field_values(writer.pages[pg - 1], vals, auto_regenerate=False)

    writer.set_need_appearances_writer(True)

    with open(out_pdf, "wb") as f:
        writer.write(f)


def check_field_value(field_info, val):
    """校验填入值是否与字段类型匹配。"""
    ftype = field_info["type"]
    fid = field_info["field_id"]
    if ftype == "checkbox":
        on_val = field_info["checked_value"]
        off_val = field_info["unchecked_value"]
        if val != on_val and val != off_val:
            return f'错误: 复选框 "{fid}" 的值 "{val}" 无效。勾选值为 "{on_val}"，取消勾选值为 "{off_val}"'
    elif ftype == "radio_group":
        valid_vals = [opt["value"] for opt in field_info["radio_options"]]
        if val not in valid_vals:
            return f'错误: 单选组 "{fid}" 的值 "{val}" 无效。有效值: {valid_vals}'
    elif ftype == "choice":
        valid_vals = [opt["value"] for opt in field_info["choice_options"]]
        if val not in valid_vals:
            return f'错误: 选择框 "{fid}" 的值 "{val}" 无效。有效值: {valid_vals}'
    return None


def patch_pypdf_choice_handling():
    """修补 pypdf 对带显示文本的选择列表的处理逻辑。"""
    from pypdf.generic import DictionaryObject
    from pypdf.constants import FieldDictionaryAttributes

    original_fn = DictionaryObject.get_inherited

    def patched_fn(self, key: str, default=None):
        result = original_fn(self, key, default)
        if key == FieldDictionaryAttributes.Opt:
            if isinstance(result, list) and all(isinstance(v, list) and len(v) == 2 for v in result):
                result = [r[0] for r in result]
        return result

    DictionaryObject.get_inherited = patched_fn


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("用法: populate_form_fields.py [输入PDF] [field_values.json] [输出PDF]")
        sys.exit(1)
    patch_pypdf_choice_handling()
    fill_fields(sys.argv[1], sys.argv[2], sys.argv[3])
