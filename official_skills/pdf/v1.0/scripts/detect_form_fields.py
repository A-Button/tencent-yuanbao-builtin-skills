"""检测 PDF 是否包含可填充的表单字段。"""

import sys
from pypdf import PdfReader

pdf = PdfReader(sys.argv[1])
if pdf.get_fields():
    print("该 PDF 包含可填充的表单字段")
else:
    print("该 PDF 不包含可填充的表单字段，需要通过视觉方式确定数据输入位置")
