"""在页面图片上绘制边界框，用于可视化调试。"""

import json
import sys

from PIL import Image, ImageDraw


def draw_field_boxes(page_num, fields_path, image_path, save_path):
    with open(fields_path, 'r') as f:
        data = json.load(f)

        img = Image.open(image_path)
        canvas = ImageDraw.Draw(img)
        box_count = 0

        for item in data["form_fields"]:
            if item["page_number"] == page_num:
                input_box = item['entry_bounding_box']
                label_rect = item['label_bounding_box']
                canvas.rectangle(input_box, outline='red', width=2)
                canvas.rectangle(label_rect, outline='blue', width=2)
                box_count += 2

        img.save(save_path)
        print(f"已生成调试图片: {save_path}，共绘制 {box_count} 个边界框")


if __name__ == "__main__":
    if len(sys.argv) != 5:
        print("用法: generate_debug_image.py [页码] [fields.json] [输入图片] [输出图片]")
        sys.exit(1)
    draw_field_boxes(int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4])
