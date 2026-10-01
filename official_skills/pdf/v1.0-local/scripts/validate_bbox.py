"""验证 fields.json 中的边界框是否存在重叠或尺寸不足的问题。"""

from dataclasses import dataclass
import json
import sys


@dataclass
class BBoxItem:
    box: list[float]
    category: str
    field_data: dict


def validate_field_boxes(fields_json_stream) -> list[str]:
    msgs = []
    data = json.load(fields_json_stream)
    msgs.append(f"共读取 {len(data['form_fields'])} 个字段")

    def is_overlapping(a, b):
        no_h_overlap = a[0] >= b[2] or a[2] <= b[0]
        no_v_overlap = a[1] >= b[3] or a[3] <= b[1]
        return not (no_h_overlap or no_v_overlap)

    all_boxes = []
    for f in data["form_fields"]:
        all_boxes.append(BBoxItem(f["label_bounding_box"], "label", f))
        all_boxes.append(BBoxItem(f["entry_bounding_box"], "entry", f))

    found_error = False
    for i, bi in enumerate(all_boxes):
        for j in range(i + 1, len(all_boxes)):
            bj = all_boxes[j]
            if bi.field_data["page_number"] == bj.field_data["page_number"] and is_overlapping(bi.box, bj.box):
                found_error = True
                if bi.field_data is bj.field_data:
                    msgs.append(f"错误: `{bi.field_data['description']}` 的标签和输入区域边界框重叠 ({bi.box}, {bj.box})")
                else:
                    msgs.append(f"错误: `{bi.field_data['description']}` 的{bi.category}边界框 ({bi.box}) 与 `{bj.field_data['description']}` 的{bj.category}边界框 ({bj.box}) 重叠")
                if len(msgs) >= 20:
                    msgs.append("检查中止，请先修复已发现的边界框问题后重试")
                    return msgs
        if bi.category == "entry":
            if "entry_text" in bi.field_data:
                fs = bi.field_data["entry_text"].get("font_size", 14)
                box_h = bi.box[3] - bi.box[1]
                if box_h < fs:
                    found_error = True
                    msgs.append(f"错误: `{bi.field_data['description']}` 的输入框高度 ({box_h}) 不足以容纳文字 (字号: {fs})，请增大框高或减小字号")
                    if len(msgs) >= 20:
                        msgs.append("检查中止，请先修复已发现的边界框问题后重试")
                        return msgs

    if not found_error:
        msgs.append("通过: 所有边界框验证合格")
    return msgs


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("用法: validate_bbox.py [fields.json]")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        for msg in validate_field_boxes(f):
            print(msg)
