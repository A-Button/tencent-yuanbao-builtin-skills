# PDF 处理指南

本指南涵盖使用 Python 库和命令行工具进行 PDF 处理的常用操作。更高级的用法、JavaScript 库及更多示例见[进阶参考](进阶参考.md)。如需填写 PDF 表单，请阅读[表单填写指南](表单填写.md)并按照说明操作。

## 快速入门

```python
from pypdf import PdfReader, PdfWriter

# 读取 PDF
reader = PdfReader("document.pdf")
print(f"页数: {len(reader.pages)}")

# 提取文字
text = ""
for page in reader.pages:
    text += page.extract_text()
```

---

## Python 库

### pypdf —— 基础操作

#### 合并 PDF
```python
from pypdf import PdfWriter, PdfReader

writer = PdfWriter()
for pdf_file in ["doc1.pdf", "doc2.pdf", "doc3.pdf"]:
    reader = PdfReader(pdf_file)
    for page in reader.pages:
        writer.add_page(page)

with open("merged.pdf", "wb") as output:
    writer.write(output)
```

#### 拆分 PDF
```python
reader = PdfReader("input.pdf")
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f"page_{i+1}.pdf", "wb") as output:
        writer.write(output)
```

#### 提取元数据
```python
reader = PdfReader("document.pdf")
meta = reader.metadata
print(f"标题: {meta.title}")
print(f"作者: {meta.author}")
print(f"主题: {meta.subject}")
print(f"创建工具: {meta.creator}")
```

#### 旋转页面
```python
reader = PdfReader("input.pdf")
writer = PdfWriter()

page = reader.pages[0]
page.rotate(90)  # 顺时针旋转90度
writer.add_page(page)

with open("rotated.pdf", "wb") as output:
    writer.write(output)
```

#### 密码保护
```python
from pypdf import PdfReader, PdfWriter

reader = PdfReader("input.pdf")
writer = PdfWriter()

for page in reader.pages:
    writer.add_page(page)

# 设置密码
writer.encrypt("userpassword", "ownerpassword")

with open("encrypted.pdf", "wb") as output:
    writer.write(output)
```

### pdfplumber —— 文字与表格提取

#### 提取文字（保留版面）
```python
import pdfplumber

with pdfplumber.open("document.pdf") as pdf:
    for page in pdf.pages:
        text = page.extract_text()
        print(text)
```

#### 提取表格
```python
with pdfplumber.open("document.pdf") as pdf:
    for i, page in enumerate(pdf.pages):
        tables = page.extract_tables()
        for j, table in enumerate(tables):
            print(f"第 {i+1} 页 表格 {j+1}:")
            for row in table:
                print(row)
```

#### 表格导出为 Excel
```python
import pandas as pd

with pdfplumber.open("document.pdf") as pdf:
    all_tables = []
    for page in pdf.pages:
        tables = page.extract_tables()
        for table in tables:
            if table:
                df = pd.DataFrame(table[1:], columns=table[0])
                all_tables.append(df)

if all_tables:
    combined_df = pd.concat(all_tables, ignore_index=True)
    combined_df.to_excel("extracted_tables.xlsx", index=False)
```

### reportlab —— 创建 PDF

#### 中文字体注册（必读）

**重要**：ReportLab 的内置字体（Helvetica / Times-Roman / Courier）**不含任何中文字形**，直接 `drawString("中文")` 或对 `Paragraph` 使用默认样式都会渲染成空白或方块。生成任何含中文的 PDF 前，都必须先注册一款支持中文的 TrueType 字体。

本技能统一使用**思源黑体（Source Han Sans）**。沙盒中实际安装的是 Google 版 **Noto Sans CJK**（与 Adobe 思源黑体字形完全一致，同一套母带，只是品牌不同），路径 `/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc`。它是 TTC 合集（`0=JP, 1=KR, 2=SC, 3=TC, 4=HK`），简体中文是索引 `2`。

下面 7 行是注册片段，**把它原样复制到你 PDF 生成脚本的最前面**（在用任何 ReportLab 接口之前），脚本运行时这 7 行就会把字体注册进 ReportLab。下面所有 ReportLab 示例都已自带这一段：

```python
import os
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

CJK_FONT = "SourceHanSans"
_NOTO_TTC = os.environ.get("CJK_FONT_PATH", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
pdfmetrics.registerFont(TTFont(CJK_FONT, _NOTO_TTC, subfontIndex=2))  # 0=JP 1=KR 2=SC 3=TC 4=HK
```

注册之后，把变量 `CJK_FONT`（其值为 `"SourceHanSans"`）传给 `Canvas.setFont` / `style.fontName` / `Table` 的 `('FONTNAME', ...)` 等任何需要字体名的地方即可。如需在沙盒外用别的字体，设环境变量 `CJK_FONT_PATH` 指向另一个 TTC 即可（仍会按 `subfontIndex=2` 取简体子字体；若你的字体不是 TTC，请直接把上面的 `subfontIndex=2` 去掉）。

> 如果想要更完整的查找/回退逻辑（env var 路径不存在时回退到默认路径、TTC 子字体索引兜底等），可以参考 `scripts/fonts.py` 的实现。但绝大多数场景下上面这 7 行就够了。

#### 基础创建
```python
import os
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

CJK_FONT = "SourceHanSans"
_NOTO_TTC = os.environ.get("CJK_FONT_PATH", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
pdfmetrics.registerFont(TTFont(CJK_FONT, _NOTO_TTC, subfontIndex=2))  # 0=JP 1=KR 2=SC 3=TC 4=HK

c = canvas.Canvas("hello.pdf", pagesize=letter)
width, height = letter

c.setFont(CJK_FONT, 12)
c.drawString(100, height - 100, "Hello World!")
c.drawString(100, height - 120, "这是用 reportlab 创建的 PDF")
c.line(100, height - 140, 400, height - 140)
c.save()
```

#### 多页报告
```python
import os
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

CJK_FONT = "SourceHanSans"
_NOTO_TTC = os.environ.get("CJK_FONT_PATH", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
pdfmetrics.registerFont(TTFont(CJK_FONT, _NOTO_TTC, subfontIndex=2))  # 0=JP 1=KR 2=SC 3=TC 4=HK

doc = SimpleDocTemplate("report.pdf", pagesize=letter)
styles = getSampleStyleSheet()
# 把所有常用样式切成思源黑体，避免中文落回到 Helvetica 变成方块
for style_name in ("Normal", "BodyText", "Title", "Heading1", "Heading2", "Heading3"):
    styles[style_name].fontName = CJK_FONT

story = []

title = Paragraph("报告标题", styles['Title'])
story.append(title)
story.append(Spacer(1, 12))

body = Paragraph("这是报告正文内容。" * 20, styles['Normal'])
story.append(body)
story.append(PageBreak())

story.append(Paragraph("第二页", styles['Heading1']))
story.append(Paragraph("第二页的正文内容", styles['Normal']))

doc.build(story)
```

#### 上下标处理

内置的 Helvetica / Times-Roman 字体不包含 Unicode 上下标字符（₀₁₂₃₄₅₆₇₈₉、⁰¹²³⁴⁵⁶⁷⁸⁹）的字形，直接写入会渲染为黑色方块。思源黑体覆盖这些码位，一般能正常显示，但为了获得更规范的基线和字号，**推荐统一使用 ReportLab 的 XML 标签**：

```python
import os
from reportlab.platypus import Paragraph
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

CJK_FONT = "SourceHanSans"
_NOTO_TTC = os.environ.get("CJK_FONT_PATH", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")
pdfmetrics.registerFont(TTFont(CJK_FONT, _NOTO_TTC, subfontIndex=2))  # 0=JP 1=KR 2=SC 3=TC 4=HK

styles = getSampleStyleSheet()
styles['Normal'].fontName = CJK_FONT

# 下标：使用 <sub> 标签
chemical = Paragraph("H<sub>2</sub>O", styles['Normal'])

# 上标：使用 <super> 标签
squared = Paragraph("x<super>2</super> + y<super>2</super>", styles['Normal'])
```

对于 Canvas 直接绘制的文字，需手动调整字号和位置来实现上下标效果。

---

## 命令行工具

### pdftotext（poppler-utils）
```bash
# 提取文字
pdftotext input.pdf output.txt

# 保留版面格式
pdftotext -layout input.pdf output.txt

# 提取指定页面范围
pdftotext -f 1 -l 5 input.pdf output.txt  # 第1-5页
```

### qpdf
```bash
# 合并 PDF
qpdf --empty --pages file1.pdf file2.pdf -- merged.pdf

# 拆分页面
qpdf input.pdf --pages . 1-5 -- pages1-5.pdf
qpdf input.pdf --pages . 6-10 -- pages6-10.pdf

# 旋转页面
qpdf input.pdf output.pdf --rotate=+90:1  # 第1页旋转90度

# 解除密码保护
qpdf --password=mypassword --decrypt encrypted.pdf decrypted.pdf
```

### pdftk（如果可用）
```bash
# 合并
pdftk file1.pdf file2.pdf cat output merged.pdf

# 拆分
pdftk input.pdf burst

# 旋转
pdftk input.pdf rotate 1east output rotated.pdf
```

---

## 常见任务

### 扫描件 OCR 识别
```python
# 依赖：pip install pytesseract pdf2image
import pytesseract
from pdf2image import convert_from_path

images = convert_from_path('scanned.pdf')

text = ""
for i, image in enumerate(images):
    text += f"第 {i+1} 页:\n"
    text += pytesseract.image_to_string(image)
    text += "\n\n"

print(text)
```

### 添加水印
```python
from pypdf import PdfReader, PdfWriter

watermark = PdfReader("watermark.pdf").pages[0]

reader = PdfReader("document.pdf")
writer = PdfWriter()

for page in reader.pages:
    page.merge_page(watermark)
    writer.add_page(page)

with open("watermarked.pdf", "wb") as output:
    writer.write(output)
```

### 提取图片
```bash
# 使用 pdfimages（poppler-utils）
pdfimages -j input.pdf output_prefix

# 生成 output_prefix-000.jpg, output_prefix-001.jpg 等文件
```

---

## 速查表

| 任务 | 推荐工具 | 关键用法 |
|------|----------|----------|
| 合并 PDF | pypdf | `writer.add_page(page)` |
| 拆分 PDF | pypdf | 每页输出为独立文件 |
| 提取文字 | pdfplumber | `page.extract_text()` |
| 提取表格 | pdfplumber | `page.extract_tables()` |
| 创建 PDF | reportlab | Canvas 或 Platypus |
| 命令行合并 | qpdf | `qpdf --empty --pages ...` |
| 扫描件识别 | pytesseract | 先转图片再 OCR |
| 填写表单 | pypdf 或 pdf-lib（见[表单填写指南](表单填写.md)） | 见表单填写指南 |

## 依赖

运行本技能的环境已预装以上组件，直接调用即可，无需在本机另行安装或配置

## 延伸阅读

- pypdfium2 高级用法：见[进阶参考](进阶参考.md)
- JavaScript 库（pdf-lib、pdfjs-dist）：见[进阶参考](进f阶参考.md)
- 填写 PDF 表单：按照[表单填写指南](表单填写.md)操作
- 常见问题排查：见[进阶参考](进阶参考.md)
