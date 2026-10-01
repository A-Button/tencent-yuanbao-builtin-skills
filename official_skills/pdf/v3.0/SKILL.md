# PDF

本技能同时支持两类任务：

1. **从零创建 PDF / 成品文档**：当用户要新做一份 PDF/文档时触发；即使用户上传了 PDF，只要它是参考资料、内容来源或风格参考，也仍然走创建流程。不要凭空排版，先用 `yuanbao-cli download --skill pdf` 获取对应模板，再用 HTML/CSS→PDF 生成。
2. **编辑已有 PDF**：当用户的目标是修改某个已有 PDF 文件本身时触发，包括 PDF 的读取、提取、填写、覆盖标注、OCR、合并、拆分、旋转、水印等。

## 总原则

- **不要覆盖用户原文件**：所有编辑输出都写入新文件，如 `input_edited.pdf`、`input_filled.pdf`、`merged.pdf`。
- **分流优先级最高**：看 PDF 在任务中的角色，而不是只看有没有上传 PDF。
- **PDF 是参考资料/内容来源/风格参考 → 创建流程**：例如“参考这个 PDF 的内容写一份新的 PDF”“根据这个报告生成一版汇报 PDF”“仿照这个 PDF 的结构做一个新文档”。
- **PDF 是被修改对象 → 编辑流程**：例如“把这个 PDF 里的名字改掉”“给这个 PDF 加水印”“合并这几个 PDF”“填写这个 PDF 表单”“删掉第 3 页”。
- **从零创建只走 HTML→PDF**：不得使用 ReportLab/pdf-lib 从零创建示例来生成新文档。
- **已有 PDF 编辑**：可以使用 `pypdf`、`pdfplumber`、`qpdf`、表单脚本、OCR、overlay 等 PDF 处理方法；这些方法仅用于编辑/处理已有 PDF。
- **PDF 不是源文档**：小范围添加文字、勾选、盖章、水印可以叠加；大段改写、重新分页、整体换风格，应先抽取/分析原 PDF，再作为编辑结果输出新文件。


## 路由入口

### A. 从零创建 PDF

适用：用户要“做一份新的 PDF / 文档 / 报告 / 简历 / 合同 / 行程 / 详情页”等。若用户上传 PDF，但表达是“参考、借鉴、根据、仿照、提炼、改写成一份新的 PDF”，则该 PDF 是输入素材，不是编辑对象，也走创建流程。

执行“创建流程”。

### B. 编辑已有 PDF

适用：用户要求直接处理某个已有 PDF 文件本身。判断标准是输出应保留原 PDF 的文件身份或页面基础，只在其上做修改、填写、拆分、合并、旋转、水印、标注、OCR、提取等操作。

如果用户同时上传 PDF 又说“做一份新的 PDF”，不要默认编辑原文件；先把上传 PDF 当作参考材料，走创建流程。只有当用户明确说“改这个 PDF / 编辑这个文件 / 在这个 PDF 上加...”时，才走编辑流程。

先识别编辑类型：

| 用户意图 | 默认方案 |
|---|---|
| 读取文字/元数据 | `pypdf` |
| 提取表格 | `pdfplumber`，必要时导出 CSV/XLSX |
| 合并/拆分/旋转/加密/解密 | `pypdf` 或 `qpdf` |
| 添加水印/盖章/页眉页脚 | 使用 overlay 方法，再用 `pypdf.merge_page()` 合并 |
| 填写可交互 PDF 表单 | 读取 `表单填写.md`，按可填充字段流程执行 |
| 填写不可交互表单/扫描表 | 读取 `表单填写.md`，按结构坐标或视觉坐标叠加文字 |
| OCR 扫描件 | `pdf2image` + `pytesseract` |
| 提取图片 | `pdfimages` 或 Python 渲染工具 |
| 大段改文案/整体改版 | 若目标是改原 PDF → 编辑流程；若目标是参考原 PDF 新做一份 → 创建流程 |

执行“编辑流程”。

---

# 创建流程：模板路由 + HTML→PDF
一句话原理：**先定位模板（选对"哪一套设计"），再用该模板的 Layout 积木拼出 N 页。**
> ⚠️ 核心概念：
> 每个模板提供的是一组 **Layout 积木（版式母版）**，不是"固定 N 张成品页"。
> 文档最终页数**由用户内容决定**——同一个 Layout 可以用 0 次、1 次或多次。
> ❌ 错误理解：模板有 6 个 layout → 就输出 6 页。
> ✅ 正确理解：模板给你 6 种"积木"，你看用户大纲，用这些积木拼出实际需要的页数。

---
## Step 1：识别场景 → 选定模板场景

模板文件都在云端资源中。下载时直接使用 `references/template-catalog.md` 表格里的相对路径；本地文件只可作为开发参考，不是运行时模板来源。

执行创建流程时，先读取 `references/template-catalog.md`，根据用户需求选择：

1. 模板场景；
2. 主 HTML 云端路径；
3. layout 云端路径。

不要在 `SKILL.md` 里猜模板路径，也不要尝试读取本地模板目录。模板 catalog 是唯一的模板索引入口。

关于 layout.md：**通用积木语汇**（几乎每个模板都有，命名可能不同，按各自 layout.md 为准）：

| 积木 | 作用 | 出现在 |
|------|------|--------|
| `Cover` 封面 | 标题 + 副标题 + 元信息（作者/日期/编号）+ 主视觉 | 多数多页模板 |
| `RunHead` 页眉 | 栏目名 + 页码，固定在版心顶部 | 报告 / 财务 / 论文类 |
| `SectionHead` 章节头 | 章节号 + 中文名 + 英文 kicker + 分隔线 | 报告 / 简报 / 讲义 |
| `TextBlock` 正文块 | 段落 / bullet 列表 / 编号列表 | 所有文字型模板 |
| `KeyValue` 键值表 | 左标签 + 右取值（信息登记/元数据） | 简报 / 实验 / 合同 |
| `MetricCard` 指标卡 | 大数字 + 单位 + 标签（+ 环比 delta） | 财务 / 工作报告 |
| `DataTable` 数据表 | 表头（主色底）+ 交替行 + 合计 | 财务 / 合同 / 报告 |
| `Timeline` 时间轴 | 阶段 / 时间点 / 里程碑 | 旅行 / 工作报告 |
| `Clause` 条款块 | 第 X 条 + 标题 + 层级编号正文 | 合同 / 公文 |
| `Callout` 提示卡 | 主色左竖条 + 强调文字 | 讲义 / 报告 |
| `Chart` 图表 | 柱 / 线 / 饼 / 环形 | 财务 / 工作报告 |
| `CodeBlock` 代码块 | 等宽字体 + 主色左边框 + 行号 | 技术报告 / 讲义 |
| `QuestionBlock` 题块 | 题号 + 题干 + 选项 / 作答区 | 试卷 |
| `BackCover` 封底 | 收尾页（反相底 + 落款 / 版权） | 报告 / 旅行 类 |

> 拼装规则：**内容多就复制积木**（多一条条款→复制 `Clause`；多一个指标→复制 `MetricCard`），
> **不足一页别硬撑**，也不要为缩短空白挪动页码等固定元素——用增补正文填充。
依据用户需求判断文档类型，按 `references/template-catalog.md` 选定**模板场景**（精确匹配优先；无精确匹配时用 catalog 中的兜底规则）。

## Step 2：获取并读取模板文件

确定模板场景后，必须用 `yuanbao-cli` 下载 catalog 中列出的主 HTML 和 layout 文件，再读取下载后的文件，提取其**结构与布局特征**。

```bash
yuanbao-cli download --skill pdf "<模板相对路径>" --output-dir "<本次任务的模板缓存目录>"
```

执行规则：

1. 下载目录建议放在当前任务输出目录下，例如 `output/template_refs/<task_id>/`，避免污染 skill 根目录。
2. 主 HTML 和 layout 都要下载；只下载 HTML 会导致模型缺少模板的设计令牌和 Layout 积木说明。
3. 后续只读取下载后的文件作为参考，不要再查找或直接读取本地模板目录。
4. 如果模板下载失败，先报告缺少哪个云端路径，并换用 catalog 中同类目下明确可下载的相近模板；不要凭空自创一套风格。


## Step 3：决定产出格式

- **默认一律 HTML+CSS → PDF**：还原度最高，可精确复刻模板的配色、字体、栏位、装饰元素。公式用 KaTeX/MathJax，表格用原生 HTML table。

## Step 3.5：图片占位填充策略

`image_generation/generate` 是原子级视觉创作能力，分为文生图（Text2Image，文字→图）与图生图（Image2Image，基于已有图→图）。一次调用只产出 1 张图，需要多张就并行多次调用。
`picture_search`是搜图工具，可以通过调用这个工具完成图片搜索。

按类型选择：

| 取向 | 适用类型 | 取图策略 |
|---|---|---|
| 可信度优先 → 优先搜真实图 | 旅行攻略、工作报告、行业研究、财务/投资、技术报告、新闻科普、真实产品详情页 | 用可检索真实图片；找不到可靠图时留白或用克制图标/色块 |
| 美观度优先 → 优先生成图 | 手帐/艺术、画册、杂志图文、创意海报、贺卡、装饰插画 | 按版面风格、配色、主题生成贴合图片 |



## Step 4：生成 HTML

1. 以参考文件的结构骨架为模板，替换为用户真实内容。
2. 复刻视觉语言：主色、标题排版、分栏、页眉页脚、序号体例。
3. 写 HTML/CSS：按页面类型选择 A4 规则。正文型页面使用 `@page content { size: A4;}`；封面、封底、简历、详情页、海报、手帐等视觉型整页页面使用 `@page fullbleed { size: A4; margin: 0; }`。`body { margin: 0; }`、`-webkit-print-color-adjust: exact`、中文字体 `Noto Sans CJK` 必须保留。
4. 视觉型页面使用“无边距纸面 + 安全内容区”结构：外层 `.fullbleed-page { page: fullbleed; width: 210mm; height: 297mm; position: relative; overflow: hidden; break-after: page; page-break-after: always; break-inside: avoid; page-break-inside: avoid; }` 负责铺满 A4 并强制独占一页；背景图、色块、侧边栏可 `position: absolute; inset: 0;` 全幅铺开；文字主体放入 `.safe-content { position: relative; padding: 18mm 12mm; }`，避免贴边难读。
5. 控制单页高度：封面和每个正文页都必须按 A4 可用高度设计，不能让同一个封面或正文容器因为内容超高被 Chromium 自动切成两页。给封面、整页正文容器和关键卡片设置 `height: 297mm; overflow: hidden; break-inside: avoid; page-break-inside: avoid;`。如果内容超出一页，先少量压缩图片高度、字号、行距、边距或减少装饰元素，仍放不下时按语义拆成新的 `.report-page`，不要依赖浏览器自动分页。
6. 正文页统一容器：每一页的页眉、正文内容和页脚需要包在同一个 `.report-page` 容器内，并对 `.report-page` 做分页控制，例如 `.report-page { width: 210mm; height: 297mm; overflow: hidden; box-sizing: border-box; break-after: page; page-break-after: always; break-inside: avoid; page-break-inside: avoid; }`。`box-sizing: border-box` 保证 padding 不会让总高超过 297mm。不得把 header/footer 写成独立分页元素，也不得让页眉或页脚脱离对应正文单独落到上一页或下一页。
7. 图片防切：所有图片（特别是封面背景图、卡片缩略图）必须加 `break-inside: avoid; page-break-inside: avoid;`。建议全局写一条 `img { break-inside: avoid; page-break-inside: avoid; }`，把图片标记为"不可切分"。

## Step 5：代码质检 Gate

生成 PDF 前必须先用 Chromium 布局结果做代码质检，不以人工目测作为通过条件：

```bash
node scripts/check_render_quality.js --source output/document.html --report output/render-quality.json
```

通过标准：

1. 命令退出码为 `0`，`render-quality.json` 中 `ok` 为 `true`。
2. 每个 A4 页面容器（`.report-page` / `.fullbleed-page` / `.page`）的 `scrollHeight <= clientHeight`、`scrollWidth <= clientWidth`。
3. 正文、表格、卡片、图注、页码、页脚等内容元素都落在所属 A4 页面容器内，并保留页面底部安全区。
4. 文本块之间没有几何重叠；中文内容增多时优先拆页、增页、调整卡片结构或减少装饰密度，不用极小字号硬塞。
5. 带底色的小方块、圆角块、圆形徽章、编号、图标、勾号等小型组件必须使用可计算居中规则：`display:inline-flex` 或 `display:flex`，`align-items:center`，`justify-content:center`，`line-height:1`。若字体视觉中心特殊，可在组件内部加极小的 `transform: translateY(...)` 微调。
6. 所有 `<img>` 必须加载成功，`naturalWidth > 0` 且 `naturalHeight > 0`；本地图片使用相对 HTML 的路径、绝对路径或 base64，不使用模型无法访问的远程临时地址。
7. 普通插图必须声明容器宽高和 `object-fit: cover` / `object-fit: contain`；背景图必须使用可覆盖 A4 的规则，例如 `position:absolute; inset:0; width:100%; height:100%; object-fit:cover`，或 `background-size:cover; background-position:center`。
8. 若命令输出 `FAIL`，先根据 `render-quality.json` 中的 `code`、`selector`、`rect` 修改 HTML/CSS，再重新运行本步骤；通过后再渲染 PDF。

## Step 6：生成 PDF

用 `html_to_pdf` 调用沙盒 Chromium 打印：

```bash
html_to_pdf --source output/document.html --target output/document.pdf
```

HTML 和 PDF 路径都可以是相对路径；`html_to_pdf` 会自动查找 Chromium、创建输出目录，并把 HTML 路径转换为 `file://`。

如需每页页眉页脚，不要用 `.page` 内部元素模拟；必须由 `html_to_pdf` 支持 Chromium `displayHeaderFooter`，或在 CLI 中新增 `--header-template`、`--footer-template`、`--margin-top`、`--margin-bottom` 参数。

---

# 编辑流程：已有 PDF 操作

## Step 0：识别 PDF 类型与任务

先确认输入文件、页数、是否加密、是否可提取文字：

```python
from pypdf import PdfReader
reader = PdfReader("input.pdf")
print(len(reader.pages))
print(reader.is_encrypted)
print(reader.metadata)
print(reader.pages[0].extract_text()[:500])
```

- 可提取文字：优先结构化读取。
- 提取结果为空或乱码：按扫描件/图片型 PDF 处理，必要时 OCR。
- 有密码：先让用户提供密码，或用 `qpdf --password=... --decrypt` 输出解密副本。

## 读取与提取

基础文字提取用 `pypdf`：

```python
from pypdf import PdfReader
reader = PdfReader("document.pdf")
text = "\n".join(page.extract_text() or "" for page in reader.pages)
```

表格提取用 `pdfplumber`：

```python
import pdfplumber
with pdfplumber.open("document.pdf") as pdf:
    for page in pdf.pages:
        tables = page.extract_tables()
```

## 合并、拆分、旋转、加密

优先用 `pypdf`，复杂页面选择用 `qpdf`。

合并：

```python
from pypdf import PdfReader, PdfWriter
writer = PdfWriter()
for pdf_file in ["doc1.pdf", "doc2.pdf"]:
    reader = PdfReader(pdf_file)
    for page in reader.pages:
        writer.add_page(page)
with open("merged.pdf", "wb") as f:
    writer.write(f)
```

拆分：

```python
from pypdf import PdfReader, PdfWriter
reader = PdfReader("input.pdf")
for i, page in enumerate(reader.pages):
    writer = PdfWriter()
    writer.add_page(page)
    with open(f"page_{i+1}.pdf", "wb") as f:
        writer.write(f)
```

旋转：

```python
from pypdf import PdfReader, PdfWriter
reader = PdfReader("input.pdf")
writer = PdfWriter()
page = reader.pages[0]
page.rotate(90)
writer.add_page(page)
with open("rotated.pdf", "wb") as f:
    writer.write(f)
```

## 添加水印、盖章、文字覆盖

推荐做法：按原 `pdf` skill 的方法生成 overlay PDF，再用 `pypdf` 合并到目标页。简单英文/图形可用 FreeText 或基础 overlay；中文可靠显示、盖章、水印等需要嵌入字形时，可用 `scripts/fonts.py` 注册字体后生成 overlay。

```python
from pypdf import PdfReader, PdfWriter

overlay = PdfReader("overlay.pdf").pages[0]
reader = PdfReader("input.pdf")
writer = PdfWriter()

page = reader.pages[0]
page.merge_page(overlay)
writer.add_page(page)

with open("output.pdf", "wb") as f:
    writer.write(f)
```

叠加时注意 PDF 坐标系：原点在左下角。若坐标来自图片预览，需要按页面尺寸换算。

## 填写 PDF 表单

必须先读 `表单填写.md`，并按它的顺序执行：

1. `python scripts/detect_form_fields.py <file.pdf>` 判断是否有可填充字段。
2. 可填充字段：`parse_form_fields.py` → 创建 `field_values.json` → `populate_form_fields.py`。
3. 不可填充字段：`analyze_pdf_structure.py` 或 `pdf_to_images.py` → 创建 `fields.json` → `validate_bbox.py` → `annotate_pdf_form.py`。
4. 输出后转图片核对位置：`python scripts/pdf_to_images.py <output.pdf> <verify_images/>`。

## OCR 扫描件

扫描件或图片型 PDF 使用：

```python
from pdf2image import convert_from_path
import pytesseract

images = convert_from_path("scanned.pdf")
text = "\n\n".join(pytesseract.image_to_string(img, lang="chi_sim+eng") for img in images)
```

如果没有 OCR 依赖，先说明需要安装 `tesseract`、`pytesseract`、`pdf2image` 和 Poppler。

## 大改 PDF 的处理边界

如果用户要求“把 PDF 里这段改成另一段，并让后面内容自动重排”，不要承诺直接原地编辑。正确方案：

1. 提取原 PDF 的文字、表格和图片；
2. 按用户修改后的内容重新组织结构；
3. 如果用户要的是“编辑这个 PDF”，先以原 PDF 的结构和内容为基准判断能否叠加修改；
4. 如果用户要的是“参考这个 PDF 新做一份”，回到创建流程，用 HTML→PDF 产出新文件。

---

# 工具与参考文件

- `references/template-catalog.md`：创建 PDF 时的唯一模板索引入口；用于选择模板场景、主 HTML 云端路径和 layout 云端路径。
- `yuanbao-cli download --skill pdf "<path>" --output-dir "<dir>"`：创建 PDF 时获取模板 HTML 和 layout 参考文件。
- `scripts/fonts.py`：编辑已有 PDF 时生成中文 overlay 的字体注册。
- `scripts/cjk_styles.py`：编辑已有 PDF 时生成中文 overlay 的排版样式。
- `scripts/flowchart.py`：编辑已有 PDF 时需要流程图 overlay 或调试图时使用。
- `html_to_pdf`：创建 PDF 时用沙盒 Chromium 将 HTML 打印成 PDF。
- `scripts/check_render_quality.js`：创建 PDF 时用 Chromium 布局结果做代码质检，检查页面溢出、元素越界、文本重叠、图片加载、背景覆盖和小型组件居中规则。
- `scripts/pdf_to_images.py`：PDF 转图片用于导出页面预览；当前创建流程的通过条件以 `check_render_quality` 的代码质检结果为准。
- `scripts/analyze_pdf_structure.py`：提取文本、线条、复选框结构。
- `scripts/detect_form_fields.py` / `parse_form_fields.py` / `populate_form_fields.py`：可交互表单字段检测与填写。
- `scripts/annotate_pdf_form.py` / `validate_bbox.py`：不可交互表单的坐标验证与叠加填写。
- `表单填写.md`：填写 PDF 表单时必须读取。
- `进阶参考.md`：需要 pypdfium2、pdf-lib、pdfjs-dist 等高级用法时读取。

## 依赖
- 运行本技能的环境已预装以上组件，直接调用即可，无需在本机另行安装或配置

## 交付

- 产出文件放到用户指定位置或当前工作目录下清晰命名。
- 简要告诉用户：走了创建还是编辑流程；如果创建，使用了哪个模板场景和云端模板路径，并说明 `check_render_quality` 已通过；如果编辑，使用了哪种 PDF 操作；输出了什么文件。
