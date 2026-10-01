# Word 文档（DOCX）的创建、编辑与分析

## 概述

`.docx` 文件本质是一个 ZIP 压缩包，内部由一组 XML 文件组成。本 Skill 以
**python-docx（v1.2）+ 内建 `docxlib` 库**为主要工作方式，绝大多数任务都写一段短
Python 脚本来完成：新建、读改、追踪修订、批注、页眉页脚、目录、图片。少数追踪修订
/ 批注的底层 XML 语义仍然出现在本文档「XML 参考」一节，作为对照说明。

## 语言约定

- 回应用户时，使用与用户输入一致的语言；当用户用中文时，输出的文档正文、批注、修订文字一律使用中文。
- 技术术语（OOXML 标签名、属性名、单位、文件名、路径、命令行）保留英文原词，例如 `w:ins`、`paraId`、`DXA`、`docxlib.tracked_changes`。
- 追踪修订（tracked changes）与批注（comments）的 `w:author` 默认使用「元宝」，可通过 helper / CLI 的 `--author` / `author=` 参数覆盖。
- 翻译 PR、合规或技术稿件时，监管称谓和专名使用行业通行译法；不确定时保留中文并括注英文，禁止自行创造看似正式但无来源的译名。

## 快速参考

| 任务 | 实现方式 |
| --- | --- |
| 读取 / 分析内容 | 使用 `pandoc`，或用 python-docx 直接读段落 |
| 新建成品文档 | 先走「创建成品文档：路由优先级」——用户模板 > 系统模板 > `python-docx + docxlib` 自由生成 |
| 编辑现有文档 | `open_docx` → 用 python-docx / `docxlib` 编辑 → `save_docx`（详见下文「编辑现有文档」） |
| 追踪修订 / 批注 | `docxlib.tracked_changes` / `docxlib.comments`，见「XML 参考」章节的对照说明 |
| 体裁 / 默认排版 / 配图 | 体裁类型见 `references/routing-map.md`；默认排版与配图分别见 `references/yuanbao-default-style.md`、`references/illustrations.md` |
| 模板路由 / 云端模板资产 | `references/routing-map.md`；按命中行的 `template_files` 用 `yuanbao-cli download` 下载 |

系统模板分类目录如下：

```text
公文类：上行文、下行文、平行文、会议公文
论文类：学位论文、期刊论文、课程作业、会议论文、文献综述、实验报告
研报类：券商研报、行业研究、可行性研究、尽职调查、白皮书
商务报告类：工作总结述职、周报月报、项目汇报、会议纪要简报
合同法律类：合同协议
信函类：商务函件
简历求职类：中文简历、英文简历
教育教学类：教案教学设计、试卷习题、讲义课程文稿
文学创作类：网络小说
财务报表类：财务报表
旅行计划类：旅行计划
日程计划类：周计划
特殊代码类：技术报告
```

## 参考规范（P1）

| 文件 | 内容 |
| --- | --- |
| [`references/routing-map.md`](references/routing-map.md) | 根据用户需要的题材，提供写作体裁标准和体裁模板的精确路由 |
| [`references/yuanbao-default-style.md`](references/yuanbao-default-style.md) | 中文默认字体、段落、表格、颜色 |
| [`references/illustrations.md`](references/illustrations.md) | 何时配图、来源优先级、落位与版式 |

## 交付闸门（必走，优先于探索）

Harness 有工具调用上限；缺少任一指定 `.docx` 即失败。不要把交付、验证或解释留到最后。

1. **确定目标（前段）**：列出输入、每个输出文件名、必须新增/删除的锚点和保留内容。找不到源稿时才报告附件缺失，禁止凭空重建“基于原稿”的编辑结果。
2. **先形成可交付物（中段）**：每个指定输出都先跑通脚本、`save_docx` 出一个可打开版本；多文件任务逐个完成。保留最后一段工具预算只用于预检、修复和重新写盘，禁止在交付前继续泛读或长篇解释。
3. **定向编辑**：多轮任务必须在上一轮同名文件上 `open_docx` → 用 `docxlib` / python-docx 做最小修改 → 同名 `save_docx`，不得从头重建。替换任务必须同时记录“新锚点必须存在、旧锚点必须不存在、非目标锚点必须保留”。
4. **预检后交付（末段）**：每个输出必须先通过 `validate.py`，再按任务要求运行 `preflight.py`；失败就修复并重新写盘。预检命令和任务模式见「编辑现有文档」中的交付前检查。

### STOP 规则（可判定，必须照做）

**写到磁盘不算交付：产物只有出现在最终回复里、并逐个给出绝对路径，才会被收走。**
工具调用预算耗尽时若还没发出最终回复，磁盘上再完美的成品也一律记零分。

- **(a) 预检一过，立刻收尾**：所有指定输出都通过 `preflight.py` 的那一刻，本次任务
  的工具调用即结束——下一条消息必须是最终回复，逐行列出每个产物的绝对路径。不要再
  “顺手再看一眼”。
- **(b) 预检通过后禁止渲染目检**：转 PDF、`pdftoppm` 出图、`pdftotext` 翻页找某张表
  落在第几页，都只是**预检失败时**的诊断手段。预检已通过就不许再做——这类循环没有
  退出判据，最典型的死法就是把剩余预算全部烧在这里然后零交付。
- **(c) 单产物修复上限 2 轮**：同一个文件的「预检 → 修复 → 重跑」最多 2 轮。第 2 轮
  仍不过，就按现状交付，并在最终回复里写明残留问题，不要第 3 轮。
- **(d) 预算过半就先保底**：工具调用用掉一半时，不论完成度如何，先把当前版本
  `save_docx` 落盘，确保任何时刻中断都有一份可交付的文件。

### 高频失败任务的必选预检

- **替换/删除型多轮编辑**：`--require` 新文本，`--forbid` 被取消的旧文本；如需修订，加 `--require-revision --revision-author 元宝`。
- **带修订、批注且多文件的任务**：先分别 `save_docx` 所有输出；终稿加 `--require-revision --revision-author 元宝 --min-comments N`，记录表加 `--min-tables 1`。
- **追加排期、预算或效果表**：加 `--min-tables N`，并将预算、列头、场景名和不可变价格逐项作为 `--require`。

体裁的最小结构与消歧见 [`references/routing-map.md`](references/routing-map.md)；新建中文文档默认排版见 [`references/yuanbao-default-style.md`](references/yuanbao-default-style.md)。强格式体裁如有用户提供的官方规范或模板，优先按其执行。

## 内容与数据硬规则

1. **忠于源材料**：编辑、翻译、营销文案、对照表中的事实、数据、条款编号、产品卖点必须来自附件或 prompt；不得额外添加 Safe Harbor、法律免责声明、机构背书、实验细节等无来源内容。
2. **基于原稿最小修改**：prompt 含「在初稿 / 原文档 / 上一版基础上」时，必须 `open_docx` 原文件做最小 diff；找不到原稿时不得重建替代稿。
3. **锚点清单**：动手前把 prompt 中的文件名、数字、专名、条款和必须章节列成清单；`save_docx` 前逐项回查，避免漏掉硬锚点。
4. **数值可复算**：合计必须等于分项之和；ROI、效果预估等衍生指标须在文档中给出计算口径。改一个数时，同步更新摘要、正文、表格和合计行中的所有引用。
5. **术语逐字一致**：术语表、正文、引语中的公司名、产品名和固定译法保持一致；除非首次同时定义全称与缩写，否则不得混用全称、缩写或大小写变体。

### 把 .doc 转为 .docx

旧版 `.doc` 文件必须先转换，才能按本 Skill 的方式编辑：

```bash
python scripts/office/soffice.py --headless --convert-to docx document.doc
```

### 读取内容

```bash
# 提取正文（含 tracked changes）
pandoc --track-changes=all document.docx -o output.md
```

```python
# 或者直接用 python-docx 读段落 / 表格 / 页眉页脚
from docxlib import open_docx
doc = open_docx("document.docx")
for p in doc.paragraphs:
    print(p.text)
```

### 转为图片

```bash
python scripts/office/soffice.py --headless --convert-to pdf document.docx
pdftoppm -jpeg -r 150 document.pdf page
```

### 接受所有 tracked changes

- 若沙箱**有 LibreOffice**：走 macro，一次接受全部并 store：

  ```bash
  python scripts/accept_changes.py input.docx output.docx
  ```

- 若沙箱**没有 LibreOffice**（大多数情况）：直接用 `docxlib`，与上面等价：

  ```python
  from docxlib import open_docx, save_docx, accept_all_tracked
  doc = open_docx("input.docx")
  accept_all_tracked(doc)      # <w:ins> 内容原位提升；<w:del> 整个删除；段落符 del 合并邻段
  save_docx(doc, "output.docx")
  ```

---

## 创建成品文档：路由优先级

新建成品 Word 时按下列优先级匹配，命中即停：

| 优先级 | 触发条件 | 流程 |
| --- | --- | --- |
| **L1 用户模板** | 用户上传模板，或明确给出格式要求/范文 | 严格沿用用户模板或要求 |
| **L1.5 主动确认** | 没有模板，但属于学校、期刊、单位等格式强敏感体裁 | 只问一次是否有官方模板，同时按通用路径推进 |
| **L2 系统模板** | 没有用户模板，体裁精确命中 `references/routing-map.md` 的子类 | 下载该行全部云端资产，再按资产契约处理 |
| **L3 自由生成** | 没有可用模板或体裁不匹配 | 按 `routing-map.md` 的 L3 最小硬规则 + `python-docx + docxlib` 生成 |

用户模板永远优先于系统模板，不得混用两套样式。学位/投稿论文、单位公文、标书、基金申报、指定合同范本等强敏感体裁先简短确认官方模板；用户说没有、无需或继续提供内容时，直接按 L2/L3 推进，不等待、不重复追问。系统模板只在精确子类命中时使用；未命中或结构明显不兼容时走 L3，除非用户明确接受使用相近模板。

### L1：用户模板

- 用户说「按这个模板/格式写」时，把附件作为**只读底稿**，`open_docx` → 填入真实内容 → `save_docx` 到新路径；不要覆盖用户原件。
- 用户只给文字格式要求时，先提取结构与格式清单；冲突时以用户要求为最高优先级。
- 多轮中用户后补模板时，以上一轮产物为内容源，把内容灌入新底稿并输出新文件；不得重写正文或覆盖旧文件。

### L2：系统模板

1. 在 `references/routing-map.md` 中精确匹配子类；只下载命中行列出的 `design-sources/` 文件，不得猜测路径或套用同类近似模板。
2. 对每个文件执行下载，并以实际下载结果为准：

```bash
yuanbao-cli download --skill docx "<template_file>" --output-dir "<task_template_dir>"
```

3. 按实际资产选择执行方式：
   - `design-sources/` 下的具体 `.docx`：`open_docx` → 保留格式替换内容 → `save_docx` 注意只是提取版式或参考结构，不复制案例事实。
   - 没有可用的 `.docx`：按 `routing-map.md` 的 L3 最小硬规则走 L3。
4. 读取 `design-sources/` 下命中体裁的 `.docx` 与 `.layout.md`；前者提供版式与结构，后者补充版式说明。

模板是只读源材料。使用 `design-sources/` 下选定的具体 `.docx` 时，在临时工作目录执行：

```python
import shutil
from docxlib import open_docx, save_docx
shutil.copy("<task_template_dir>/design-sources/<source>.docx", "output.docx")
doc = open_docx("output.docx")
# ... 在 doc 上做替换 / 填充 ...
save_docx(doc, "output.docx")
```

填充要求：

- 如果有占位符（如 `{{title}}`），只替换文字，run 上的字体/字号/粗体（`<w:rPr>`）保持不动；
- 多段正文必须建立独立段落（`doc.add_paragraph` 或 `docxlib.add_paragraph`）；重复条目/表格行复制对应块后再填；
- 不修改模板的页面、页眉页脚、样式和配色，除非 `layout.md` 或用户明确要求；
- 输出中不得残留 `{{...}}`、示例姓名、示例公司或无来源数据；
- 告知用户命中的大类/子类和输出文件。

### L3：无模板兜底

设计来源缺失或体裁不匹配时，不报错停下。按 `routing-map.md` 的 L3 最小硬规则和 `yuanbao-default-style.md`，用 `python-docx + docxlib` 自由生成。

---

## 新建文档（自由生成 / 无模板兜底）

用 Python 起手。`docxlib` **不在 site-packages 里**，它只存在于本 Skill 的
`scripts/` 目录下，所以每个脚本开头都必须先把该目录加进 `sys.path`——否则必报
`ModuleNotFoundError: No module named 'docxlib'`：

```python
import sys
sys.path.insert(0, "/data/skills/docx/scripts")  # 换成本 Skill 实际所在路径

from docxlib import (
    open_docx, save_docx, ensure_yuanbao_defaults,
    add_heading, add_paragraph, add_page_break,
    add_table_double_width, add_picture_with_alttext,
    add_external_hyperlink, add_footer_page_number, add_toc,
    set_page_size, set_page_margins,
)

doc = open_docx()             # 空白起手
ensure_yuanbao_defaults(doc)  # 中文默认字体 + US Letter + 1 英寸边距
add_heading(doc, "项目周报 · 第 42 周", level=1)
add_paragraph(doc, "本周的主要工作与下周计划见下。")
add_footer_page_number(doc.sections[0])
save_docx(doc, "report.docx")
```

命令行运行等价写法：`PYTHONPATH=/data/skills/docx/scripts python3 build.py`。

不确定 Skill 装在哪里时，先定位再用，不要靠猜：

```bash
find / -name docxlib -maxdepth 6 -type d 2>/dev/null | head -1
```

**若 `import docxlib` 仍失败**（例如解释器版本过旧导致 `SyntaxError`）：不要在
它上面反复试错，**立即改用纯 `python-docx` 实现**并继续交付。`python-docx` 一定
可用；`docxlib` 只是它的便利封装，所有效果都能用原生 API 手写出来（中文
eastAsia 字体、表格双宽度、页码域、纸张尺寸见「XML 参考」与
[`references/yuanbao-default-style.md`](references/yuanbao-default-style.md)）。
判断一次即止，禁止为同一个 import 问题消耗超过 2 次工具调用。

**上面这条 `sys.path` 规则对本 session 内每一次新起的 docxlib 代码同样生效，
不会因为之前已经 import 成功过而免除**：无论是主构建脚本，还是预检通过后临时
写的一段"抽查内容"的 `python -c` 片段，只要出现 `from docxlib import ...` /
`import docxlib`，前两行永远必须是 `import sys` + `sys.path.insert(...)`，且
顺序不能颠倒。反例（顺序写反，必报 `ModuleNotFoundError`）：

```python
from docxlib import open_docx     # ✗ 错误：import 写在 sys.path.insert 之前
import sys
sys.path.insert(0, "/data/skills/docx/scripts")
```

正确顺序永远是先 `sys.path.insert` 再 `import`。踩到这个报错时**直接检查并交换
这两行的顺序**，不要当成 `docxlib` 不可用又去重新走一遍版本探测或改用
`python-docx`——顺序写反和"确实不可用"是两种不同的错，别混。

已内置的示例脚本可作为起点：

```bash
python scripts/new_doc.py output.docx --example report   # minimal | report | memo
```

### 校验

生成文件后先校验；若校验失败，通过 `open_docx` 打开定点修复后再存。

```bash
python scripts/office/validate.py output.docx
```

### 页面尺寸

`ensure_yuanbao_defaults` 已经把主 section 设为 US Letter；如需自定义（比如整篇 A4、
或某一 section 走横向），直接调 `set_page_size`：

```python
# US Letter（默认）：宽 8.5 英寸，高 11 英寸
set_page_size(doc.sections[0], 12240, 15840)  # 单位 DXA（1440 = 1 英寸）

# A4：宽 8.27 英寸，高 11.69 英寸
set_page_size(doc.sections[0], 11906, 16838)

# 横向：landscape=True 会自动把宽高对调、并设 orient=landscape
set_page_size(doc.sections[0], 12240, 15840, landscape=True)

# 只想调页边距：
set_page_margins(doc.sections[0], top=1440, bottom=1440, left=1440, right=1440)
```

**常用纸张尺寸（DXA 单位，1440 DXA = 1 英寸）：**

| 纸张 | 宽度 | 高度 | 内容区宽度（1 英寸页边距） |
| --- | --- | --- | --- |
| US Letter | 12,240 | 15,840 | 9,360 |
| A4 | 11,906 | 16,838 | 9,026 |

### 样式（覆盖内置标题样式）

中文正文与标题默认使用思源黑体；英文与数字使用 Times New Roman，无法使用时才回退 Arial。**正式中文文档的正文不得默认使用 Arial。** 标题保持黑色，便于阅读。

`ensure_yuanbao_defaults` 一次处理好：Normal（12pt）+ Heading 1（16pt bold）+ Heading 2（14pt bold）+ Heading 3（13pt bold）。 需要 override 特定标题（例如 H1 加大）时使用 `ensure_heading_style`：

```python
from docxlib import ensure_heading_style
ensure_heading_style(doc, level=1, size_pt=20, bold=True)  # 覆盖内置 Heading 1
```

自己写段落时用 `apply_font_to_run` 手工挂中文字体（python-docx `run.font.name` 只写 `w:ascii`，中文会走兜底字体）：

```python
from docxlib import apply_font_to_run, EASTASIA, ASCII_HANSI
p = doc.add_paragraph()
run = p.add_run("中文和 English 混排")
apply_font_to_run(run, eastasia=EASTASIA, ascii=ASCII_HANSI, size_pt=12)
```

### 列表（禁止使用 Unicode 项目符号）

```python
# ❌ 错误 —— 切勿手动插入项目符号字符
doc.add_paragraph("• Item")

# ✅ 正确 —— 使用 python-docx 内建 List Bullet / List Number 样式
p1 = doc.add_paragraph("项目符号条目", style="List Bullet")
p2 = doc.add_paragraph("编号条目", style="List Number")
```

`List Bullet` / `List Number` 会共享 numbering 定义；相同样式的连续段落会自动接续编号（1, 2, 3…）。想让编号重启，中间插一段其它样式即可。

### 表格

**重要：表格需要"双重宽度"** —— 同时在表格上设 `<w:tblW>`、在每个 cell 上设 `<w:tcW>`。
否则在部分平台（Google Docs / WPS）上会渲染异常。`add_table_double_width` 已经把两者
写好，也把 `tblPr` 的子元素顺序（`tblW → jc → tblBorders → tblLayout → tblLook`）
按 OOXML XSD 要求排好。

```python
from docxlib import add_table_double_width

table = add_table_double_width(
    doc,
    headers=["模块", "本周状态", "备注"],
    rows=[
        ["docxlib", "已合入", "含 6 类单测"],
        ["场景 s01…s08", "冒烟通过", "手动跑 4 条最脆弱路径"],
    ],
    column_widths_dxa=[3000, 3000, 3360],   # 总和 = 9360 = US Letter 1in 页边距内容区
    header_shading="D5E8F0",                 # 表头浅蓝底，传 None 关闭
)
```

**表格宽度规则：**
- 始终用 DXA。切勿用百分比 —— 与 Google Docs 不兼容。
- `column_widths_dxa` 之和 = 表格宽度（helper 自动保证）。
- 全宽表格 = 内容区宽度 = 页宽 − 左右页边距。US Letter + 1 英寸页边距 = 9360 DXA。
- 需要复杂布局（合并单元格、跨列）时，还是用 python-docx 的 `table.cell(i, j).merge(...)`。

### 图片

```python
from docxlib import add_picture_with_alttext

p = doc.add_paragraph()
add_picture_with_alttext(
    p, "image.png",
    width_in=4.0,                # 或 height_in
    alt_title="Q3 收入",         # 三段 altText 全部必填
    alt_desc="Q3 收入按业务分布的柱状图",
    alt_name="q3_revenue",
)
```

python-docx 原生 `run.add_picture` 只写 `docPr/@descr`；`add_picture_with_alttext` 补齐
`name` 和 `title`，符合 SKILL.md 的三段 altText 要求。

### 分页符

```python
from docxlib import add_page_break
add_page_break(doc)         # 在 doc 末尾新建一段并插一个硬分页
add_page_break(paragraph)   # 或者在已有段落末尾插入
```

### 超链接

```python
from docxlib import add_external_hyperlink
p = doc.add_paragraph("欢迎访问 ")
add_external_hyperlink(p, "https://example.com", "example.com")  # 追加到段末
p.add_run(" 了解更多。")
```

内部链接（bookmark → 引用）目前需要下探 lxml；如需，可参考「XML 参考」章节。

### 页眉 / 页脚

python-docx 原生就支持页眉页脚：`section.header.paragraphs[0]`、`section.footer.paragraphs[0]`。
只有页码需要一个 `<w:fldSimple w:instr="PAGE"/>` 字段——用 `add_footer_page_number` 直接给：

```python
from docxlib import add_footer_page_number, apply_font_to_run, EASTASIA, ASCII_HANSI

section = doc.sections[0]
# 页眉：普通文字
header_run = section.header.paragraphs[0].add_run("公司内部资料 · 请勿外传")
apply_font_to_run(header_run, eastasia=EASTASIA, ascii=ASCII_HANSI)

# 页脚：第 X 页
add_footer_page_number(section, prefix="第 ", suffix=" 页")
```

### 目录

```python
from docxlib import add_toc
add_toc(doc, heading_range="1-3", hyperlink=True)
```

目录用 Word 的 TOC 域实现（`<w:instrText> TOC \o "1-3" \h \z </w:instrText>`），首次
打开文档时 Word 会提示更新域，或按 F9 手动刷新。目录能识别的只有内置 `Heading 1..N`
样式；`ensure_yuanbao_defaults` / `ensure_heading_style` 会保证这些样式带
`w:outlineLvl`，TOC 就能找到它们。

### 重要规则回顾

- **中文正文务必显式挂 eastAsia 字体** —— 每个自建的 run 都要走 `apply_font_to_run` 或 `apply_eastasia_font_to_style`；否则 python-docx 只写 `w:ascii`，中文走 Word 兜底。
- **切勿使用 `\n`** —— 使用独立的段落（`add_paragraph` 或 `doc.add_paragraph`）。
- **切勿使用 Unicode 项目符号** —— 使用 `List Bullet` / `List Number` 样式。
- **PageBreak 必须在段落里** —— 独立使用会产生非法 XML；`add_page_break` 会自动处理。
- **图片 alt 三段** —— `title` / `descr` / `name` 都要填；用 `add_picture_with_alttext`。
- **表格 tblW / tcW 双宽度** —— 用 `add_table_double_width` 一次搞定；不要百分比。
- **目录识别 outlineLvl** —— H1 = 0，H2 = 1，H3 = 2；`ensure_heading_style` 已经处理。
- **`ensure_yuanbao_defaults` 会顺手修 `<w:zoom>`** —— python-docx 默认模板里 `<w:zoom w:val="bestFit"/>` 缺 `w:percent`，会挂 XSD 校验；helper 会补 `w:percent="100"`。

---

## 编辑现有文档

**新工作流三步走：**

### 第 1 步：打开

```python
from docxlib import open_docx
doc = open_docx("document.docx")
```

`open_docx` 就是薄薄的 python-docx 包装。返回的 `doc` 可以正常用 `doc.paragraphs`、`doc.tables`、`doc.sections` 遍历、修改。

### 第 2 步：编辑

绝大多数编辑走 python-docx 原生 API：改 `run.text`、`paragraph.text`（谨慎，因为会清空其它 run 的格式）、`doc.add_paragraph(...)`、`table.cell(i, j).text = ...`。

**只在下列场景需要用 `docxlib`：**

| 场景 | helper | 一站式 CLI |
| --- | --- | --- |
| 追加内容并保留 tracked changes | `insert_tracked` / `replace_run_text_with_tracked` | `docx_edit.py insert-tracked` |
| 删除整段（含段落符） | `delete_paragraph_tracked` | `docx_edit.py delete-paragraph` |
| 拒绝别人的插入 | `reject_insertion` | `docx_edit.py reject-ins` |
| 恢复别人的删除 | `restore_deletion` | `docx_edit.py restore-del` |
| 接受所有修订（沙箱无 LibreOffice） | `accept_all_tracked` | `docx_edit.py accept-all` |
| 添加批注 / 回复批注 | `add_comment` / `reply_comment` | `comment.py` |
| 双宽度表格、中文字体、目录、页眉页脚等 | 见「新建文档」章节 | — |

**默认作者是「元宝」**，除非用户明确要求其它名字。所有 helper 都接受 `author=` kwarg。

**智能引号无须手工转义**：python-docx / lxml 会正确处理 `"`、`'` 等字符，不用像旧版本那样把智能引号预先转成 XML 实体（`&#x201C;` 等）。

### 第 3 步：保存

```python
from docxlib import save_docx
save_docx(doc, "output.docx")
```

**交付前检查（每个输出必做）：**

```bash
python scripts/office/validate.py output.docx --original original.docx

# 替换/删除：新值在、旧值不在，且修改留有修订
python scripts/office/preflight.py output.docx \
  --require "替换后的文本" --forbid "被取消的旧文本" \
  --require-revision --revision-author 元宝

# 多文件修订：终稿和记录表分别预检
python scripts/office/preflight.py final.docx \
  --require "关键数值" --require-revision --revision-author 元宝 --min-comments 4
python scripts/office/preflight.py record.docx --min-tables 1

# 追加预算/效果表：表格、预算、列头和不可变数据缺一不可
python scripts/office/preflight.py output.docx \
  --min-tables 3 --require "18万" --require "ROI" --require "259"
```

`validate.py` 会自带 XSD 与追踪修订一致性校验；`preflight.py` 失败时不得交付；修复
后重新 save 和预检。若用户指定多个输出文件，对每个目标路径重复 save 和预检。若
修改过数值，再核对摘要、正文、表格和合计行使用同一套数字，且分项之和等于合计。

**`validate.py --auto-repair` 会处理：**
- `durableId` ≥ `0x7FFFFFFF`（重新生成合法 ID）
- `<w:t>` 含首尾空白但缺失 `xml:space="preserve"`

**自动修复不会处理：**
- 非法 XML、错误的元素嵌套、缺失的关系、schema 违规

### 常见陷阱

- **改文本时保留格式**：直接改 `run.text` 会保留 rPr（粗体、字号、字体）。改 `paragraph.text` 会只保留第一个 run 的格式并清掉其它 run，谨慎使用。
- **追踪修订必须挂在 `w:p` 下作为 `w:r` 兄弟节点**：`docxlib.tracked_changes` 的所有 helper 都遵循这个规则，不要自己往 `w:r` 内部塞 `<w:ins>` / `<w:del>`。
- **`<w:del>` 内一律用 `<w:delText>`**（不是 `<w:t>`）；`<w:ins>` 内不允许出现 `<w:delText>`。`docxlib` 的 helper 会自动做 tag 转换；自己写 lxml 时要注意。
- **段落级删除必须打 `<w:pPr><w:rPr><w:del/>`** —— 否则接受修订后剩一个空段。用 `delete_paragraph_tracked` 就好。

---

## XML 参考

`docxlib` 的所有 helper 都产出符合下面这些 OOXML 语义的 XML；只有当你需要更精细
控制、或用户明确要求「用 lxml 直接改」时，才需要跳到裸 XML 层。

### schema 合规

- **`<w:pPr>` 子元素顺序**：`<w:pStyle>` → `<w:numPr>` → `<w:spacing>` → `<w:ind>` → `<w:jc>` → `<w:outlineLvl>` → `<w:rPr>` 放最后。
- **`<w:tblPr>` 子元素顺序**：`<w:tblStyle>` → `<w:tblW>` → `<w:jc>` → `<w:tblBorders>` → `<w:tblLayout>` → `<w:tblLook>`（更完整表见 XSD）。
- **空白**：`<w:t>` 如有首尾空白，必须加 `xml:space="preserve"`；`docxlib.ooxml.set_text_with_preserve` 会自动处理。
- **RSID**：`w14:paraId` 必须是 8 位十六进制（如 `00AB1234`），且 `< 0x80000000`。`w16cid:durableId` 必须 `< 0x7FFFFFFF`。`docxlib.ooxml.hex_id_8` 会生成合规值。

### 追踪修订（tracked changes）

#### 插入

```python
# helper
from docxlib import insert_tracked
insert_tracked(paragraph, "追加的文本", author="元宝")
```

对应 XML：

```xml
<w:ins w:id="1" w:author="元宝" w:date="2025-01-01T00:00:00Z">
  <w:r><w:t>追加的文本</w:t></w:r>
</w:ins>
```

#### 删除

```python
from docxlib import delete_tracked
delete_tracked(paragraph, "被删除的文本", author="元宝")
```

对应 XML：

```xml
<w:del w:id="2" w:author="元宝" w:date="2025-01-01T00:00:00Z">
  <w:r><w:delText>被删除的文本</w:delText></w:r>
</w:del>
```

**在 `<w:del>` 内部**：使用 `<w:delText>` 代替 `<w:t>`；使用 `<w:delInstrText>` 代替 `<w:instrText>`。`docxlib` 的 helper 自动完成。

#### 最小化编辑（替换 run 文本）

```python
from docxlib import replace_run_text_with_tracked
# 把某个 run 的文本替换为新文本，保留原 rPr（粗体、字号等）
replace_run_text_with_tracked(run, "60", author="元宝")
```

对应 XML（原来 run 的文本是 "30"）：

```xml
<w:r><w:t>期限为 </w:t></w:r>
<w:del w:id="1" w:author="元宝" w:date="...">
  <w:r><w:delText>30</w:delText></w:r>
</w:del>
<w:ins w:id="2" w:author="元宝" w:date="...">
  <w:r><w:t>60</w:t></w:r>
</w:ins>
<w:r><w:t> 天。</w:t></w:r>
```

#### 删除整个段落 / 列表项

```python
from docxlib import delete_paragraph_tracked
delete_paragraph_tracked(paragraph, author="元宝")
```

会在 `<w:pPr><w:rPr>` 里加一个 `<w:del/>`，同时把段落里每个 `<w:r>` 兜进 `<w:del>`。
接受修订后，该段落与下一段合并（不留空段）。对应 XML 结构：

```xml
<w:p>
  <w:pPr>
    <w:numPr>...</w:numPr>  <!-- 如果是列表项，保留 numbering -->
    <w:rPr>
      <w:del w:id="1" w:author="元宝" w:date="..."/>
    </w:rPr>
  </w:pPr>
  <w:del w:id="2" w:author="元宝" w:date="...">
    <w:r><w:delText>被整段删除的内容……</w:delText></w:r>
  </w:del>
</w:p>
```

#### 拒绝他人的插入

```python
from docxlib import find_ins_by_author, reject_insertion
for ins in find_ins_by_author(doc, "Jane"):
    reject_insertion(ins, author="元宝")
```

对应 XML（Jane 的 `<w:ins>` 保留原样，内部 `<w:r>` 被我方 `<w:del>` 兜住）：

```xml
<w:ins w:author="Jane" w:id="5">
  <w:del w:author="元宝" w:id="10">
    <w:r><w:delText>对方插入的文本</w:delText></w:r>
  </w:del>
</w:ins>
```

#### 恢复他人的删除

```python
from docxlib import find_del_by_author, restore_deletion
for de in find_del_by_author(doc, "Jane"):
    restore_deletion(de, author="元宝")
```

对应 XML（在 Jane 的 `<w:del>` 之后新增兄弟 `<w:ins>`；不动 Jane 的 `<w:del>`）：

```xml
<w:del w:author="Jane" w:id="5">
  <w:r><w:delText>被删除的文本</w:delText></w:r>
</w:del>
<w:ins w:author="元宝" w:id="10">
  <w:r><w:t>被删除的文本</w:t></w:r>
</w:ins>
```

### 批注

```python
# helper
from docxlib import add_comment, reply_comment
cid = add_comment(doc, doc.paragraphs[0], "请确认标题需要加周次", author="元宝")
reply_comment(doc, cid, "已同步", author="元宝")

# 也可以走 CLI（做完开箱即用，不需要再手补 range 标记）
# python scripts/comment.py input.docx output.docx 0 "批注内容" --anchor-para 0
# python scripts/comment.py input.docx output.docx 1 "回复内容" --parent 0
```

`add_comment` / `reply_comment` 首次调用时会 provision 四个 part：
`word/comments.xml`（正文）、`word/commentsExtended.xml`（回复链 `paraIdParent`）、
`word/commentsIds.xml`、`word/commentsExtensible.xml`；并自动登记
`[Content_Types].xml` 与 `word/_rels/document.xml.rels`。

**重要（也是最容易出错的一条）**：`<w:commentRangeStart>` 与 `<w:commentRangeEnd>` 必须
是 `<w:p>` 的直接子元素，**不能**放在 `<w:r>` 内部。helper 已经严格遵守；如自己
写 lxml 请务必如此，否则 Word 打不开或 range 覆盖漂移。

**批注不是普通正文**：用户要求 Word 批注时，必须生成 `comments.xml` 和对应 range 标记；表格中的「风险说明」文字不能替代批注。

**锚定验收**：`commentRangeStart` / `commentRangeEnd` 必须紧贴被修改或被评论的字词，不得框到相邻单元格或无关段落。`add_comment` 传 `run` 而不是 `paragraph` 可以精确到 run 级别。

对应 XML 骨架（一条批注）：

```xml
<w:commentRangeStart w:id="0"/>
<w:r><w:t>被批注的文本</w:t></w:r>
<w:commentRangeEnd w:id="0"/>
<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="0"/></w:r>
```

批注 0 内嵌一条回复 1：

```xml
<w:commentRangeStart w:id="0"/>
  <w:commentRangeStart w:id="1"/>
  <w:r><w:t>被批注的文本</w:t></w:r>
  <w:commentRangeEnd w:id="1"/>
<w:commentRangeEnd w:id="0"/>
<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="0"/></w:r>
<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="1"/></w:r>
```

### 图片

如需下探到 XML 层放置图片：

1. 把图片文件放入 `word/media/`（更常见做法：让 `paragraph.add_run().add_picture(path)` 自动处理）
2. 在 `word/_rels/document.xml.rels` 中添加关系：

```xml
<Relationship Id="rId5" Type=".../image" Target="media/image1.png"/>
```

3. 在 `[Content_Types].xml` 中添加内容类型：

```xml
<Default Extension="png" ContentType="image/png"/>
```

4. 在 `document.xml` 中引用：

```xml
<w:drawing>
  <wp:inline>
    <wp:extent cx="914400" cy="914400"/>  <!-- EMU：914400 = 1 英寸 -->
    <a:graphic>
      <a:graphicData uri=".../picture">
        <pic:pic>
          <pic:blipFill><a:blip r:embed="rId5"/></pic:blipFill>
        </pic:pic>
      </a:graphicData>
    </a:graphic>
  </wp:inline>
</w:drawing>
```

绝大多数场景不需要走这条路径；`add_picture_with_alttext` 已经把这些自动接好。

---

## 依赖

运行本技能的环境已预装下列组件，按上文命令直接调用即可，无需在本机另行安装或配置：

- **docxlib**：本 Skill 自带，**不是 pip 包、不在 site-packages**。位置为本 Skill 的 `scripts/docxlib/`（沙箱内通常是 `/data/skills/docx/scripts/`），使用前必须 `sys.path.insert(0, "<skill_dir>/scripts")` 或设 `PYTHONPATH`。要求 **Python ≥ 3.10**；import 失败时不要纠缠，直接降级到纯 `python-docx`（见「新建文档」一节）。
- **python-docx**：`~=1.2`（Python 库，本 Skill 的核心工作方式；`docxlib` 不可用时的兜底方案）
- **lxml**：python-docx 的传递依赖；`docxlib` 也直接用来做 tracked changes / comments 的底层 XML 编辑
- **pandoc**：正文提取
- **LibreOffice**：PDF / DOC / DOCX 转换（`scripts/office/soffice.py` 已为沙箱环境做兼容）。沙箱里没有 LibreOffice 时，`accept_changes.py` 不可用，改走 `docxlib.accept_all_tracked`。
- **Poppler**：`pdftoppm`，PDF 转图片

修改本 Skill 的脚本后，务必确认它们能在**最低支持版本**上解析（沙箱运行时可能比开发机旧）：

```bash
python3 -m pytest verify/docx/unit/test_docxlib/test_python_version_compat.py -q
```
