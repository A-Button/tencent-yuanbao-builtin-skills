# Word 文档（DOCX）的创建、编辑与分析

## 概述

`.docx` 文件本质是一个 ZIP 压缩包，内部由一组 XML 文件组成。

## 语言约定

- 回应用户时，使用与用户输入一致的语言；当用户用中文时，输出的文档正文、批注、修订文字一律使用中文。
- 技术术语（OOXML 标签名、属性名、单位、文件名、路径、命令行）保留英文原词，例如 `w:ins`、`paraId`、`DXA`、`scripts/office/pack.py`。
- 追踪修订（tracked changes）与批注（comments）的 `w:author` 默认使用「元宝」，可通过脚本的 `--author` 参数覆盖。

## 快速参考

| 任务 | 实现方式 |
| --- | --- |
| 读取 / 分析内容 | 使用 `pandoc`，或解包后直接看 XML |
| 新建文档 | 使用 `docx-js`（详见下文「新建文档」） |
| 编辑现有文档 | 解包 → 改 XML → 打包（详见下文「编辑现有文档」） |

### 把 .doc 转为 .docx

旧版 `.doc` 文件必须先转换，才能按本 Skill 的方式编辑：

```bash
python scripts/office/soffice.py --headless --convert-to docx document.doc
```

### 读取内容

```bash
# 提取正文（含 tracked changes）
pandoc --track-changes=all document.docx -o output.md

# 直接访问原始 XML
python scripts/office/unpack.py document.docx unpacked/
```

### 转为图片

```bash
python scripts/office/soffice.py --headless --convert-to pdf document.docx
pdftoppm -jpeg -r 150 document.pdf page
```

### 接受所有 tracked changes

若需要得到一份"所有修订都已接受"的干净文档（依赖 LibreOffice）：

```bash
python scripts/accept_changes.py input.docx output.docx
```

---

## 新建文档

使用 JavaScript 生成 `.docx`，再做校验。安装：`npm install -g docx`

### Setup

```javascript
const { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, ImageRun,
        Header, Footer, AlignmentType, PageOrientation, LevelFormat, ExternalHyperlink,
        InternalHyperlink, Bookmark, FootnoteReferenceRun, PositionalTab,
        PositionalTabAlignment, PositionalTabRelativeTo, PositionalTabLeader,
        TabStopType, TabStopPosition, Column, SectionType,
        TableOfContents, HeadingLevel, BorderStyle, WidthType, ShadingType,
        VerticalAlign, PageNumber, PageBreak } = require('docx');

const doc = new Document({ sections: [{ children: [/* 内容 */] }] });
Packer.toBuffer(doc).then(buffer => fs.writeFileSync("doc.docx", buffer));
```

### 校验

生成文件后先校验；若校验失败，解包 → 修 XML → 再打包。

```bash
python scripts/office/validate.py doc.docx
```

### 页面尺寸

```javascript
// 重要：docx-js 默认是 A4，而不是 US Letter
// 为了输出一致，永远显式设置页面大小
sections: [{
  properties: {
    page: {
      size: {
        width: 12240,   // 8.5 英寸（DXA）
        height: 15840   // 11 英寸（DXA）
      },
      margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } // 1 英寸页边距
    }
  },
  children: [/* 内容 */]
}]
```

**常用纸张尺寸（DXA 单位，1440 DXA = 1 英寸）：**

| 纸张 | 宽度 | 高度 | 内容区宽度（1 英寸页边距） |
| --- | --- | --- | --- |
| US Letter | 12,240 | 15,840 | 9,360 |
| A4（默认） | 11,906 | 16,838 | 9,026 |

**横向（Landscape）**：docx-js 会在内部交换宽高，因此按纵向的值传参，让 docx-js 去做交换：

```javascript
size: {
  width: 12240,   // 把「短边」作为 width 传入
  height: 15840,  // 把「长边」作为 height 传入
  orientation: PageOrientation.LANDSCAPE  // docx-js 会在 XML 里交换
},
// 内容区宽度 = 15840 - 左边距 - 右边距（使用长边）
```

### 样式（覆盖内置标题样式）

正文默认使用 Arial（跨平台兼容性最好）。标题保持黑色，便于阅读。

```javascript
const doc = new Document({
  styles: {
    default: { document: { run: { font: "Arial", size: 24 } } }, // 12pt 默认
    paragraphStyles: [
      // 重要：必须使用精确的内置 ID 才能覆盖内置样式
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 32, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 240, after: 240 }, outlineLevel: 0 } }, // TOC 需要 outlineLevel
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial" },
        paragraph: { spacing: { before: 180, after: 180 }, outlineLevel: 1 } },
    ]
  },
  sections: [{
    children: [
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("标题")] }),
    ]
  }]
});
```

### 列表（禁止使用 Unicode 项目符号）

```javascript
// ❌ 错误 —— 切勿手动插入项目符号字符
new Paragraph({ children: [new TextRun("• Item")] })        // 错
new Paragraph({ children: [new TextRun("\u2022 Item")] })  // 错

// ✅ 正确 —— 使用 numbering 配置，配合 LevelFormat.BULLET
const doc = new Document({
  numbering: {
    config: [
      { reference: "bullets",
        levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "numbers",
        levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
          style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ]
  },
  sections: [{
    children: [
      new Paragraph({ numbering: { reference: "bullets", level: 0 },
        children: [new TextRun("项目符号条目")] }),
      new Paragraph({ numbering: { reference: "numbers", level: 0 },
        children: [new TextRun("编号条目")] }),
    ]
  }]
});

// ⚠️ 每个 reference 对应一条独立的编号序列
// 相同 reference = 连续编号（1,2,3 → 4,5,6）
// 不同 reference = 重新开始（1,2,3 → 1,2,3）
```

### 表格

**重要：表格需要"双重宽度"** —— 同时在 table 上设 `columnWidths`，在每个 cell 上设 `width`。否则在部分平台上会渲染异常。

```javascript
// 重要：始终显式设置表格宽度，保证渲染一致
// 重要：使用 ShadingType.CLEAR（而非 SOLID），否则可能出现纯黑背景
const border = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const borders = { top: border, bottom: border, left: border, right: border };

new Table({
  width: { size: 9360, type: WidthType.DXA }, // 始终使用 DXA（percent 在 Google Docs 里会坏）
  columnWidths: [4680, 4680], // 必须和 table 宽度相等（DXA：1440 = 1 英寸）
  rows: [
    new TableRow({
      children: [
        new TableCell({
          borders,
          width: { size: 4680, type: WidthType.DXA }, // 每个 cell 也要设
          shading: { fill: "D5E8F0", type: ShadingType.CLEAR }, // 用 CLEAR，不用 SOLID
          margins: { top: 80, bottom: 80, left: 120, right: 120 }, // 单元格内边距（内部占位，不叠加到宽度上）
          children: [new Paragraph({ children: [new TextRun("单元格")] })]
        })
      ]
    })
  ]
})
```

**表格宽度的计算：**

始终使用 `WidthType.DXA` —— `WidthType.PERCENTAGE` 在 Google Docs 中会坏。

```javascript
// 表格宽度 = columnWidths 之和 = 内容区宽度
// US Letter + 1 英寸页边距：12240 - 2880 = 9360 DXA
width: { size: 9360, type: WidthType.DXA },
columnWidths: [7000, 2360]  // 必须和 table 宽度相等
```

**宽度规则：**
- **始终使用 `WidthType.DXA`** —— 切勿使用 `WidthType.PERCENTAGE`（与 Google Docs 不兼容）
- table 宽度必须等于 `columnWidths` 之和
- 每个 cell 的 `width` 必须匹配对应的 `columnWidth`
- cell 的 `margins` 是内部填充，**缩小**内容区、不会扩大 cell 宽度
- 全宽表格：使用内容区宽度（页宽 - 左右页边距）

### 图片

```javascript
// 重要：type 参数是必填的
new Paragraph({
  children: [new ImageRun({
    type: "png", // 必填：png / jpg / jpeg / gif / bmp / svg
    data: fs.readFileSync("image.png"),
    transformation: { width: 200, height: 150 },
    altText: { title: "Title", description: "Desc", name: "Name" } // 三项全部必填
  })]
})
```

### 分页符

```javascript
// 重要：PageBreak 必须放在 Paragraph 里
new Paragraph({ children: [new PageBreak()] })

// 或者使用 pageBreakBefore
new Paragraph({ pageBreakBefore: true, children: [new TextRun("新页")] })
```

### 超链接

```javascript
// 外部链接
new Paragraph({
  children: [new ExternalHyperlink({
    children: [new TextRun({ text: "点击这里", style: "Hyperlink" })],
    link: "https://example.com",
  })]
})

// 内部链接（bookmark + 引用）
// 1. 在目标处建 bookmark
new Paragraph({ heading: HeadingLevel.HEADING_1, children: [
  new Bookmark({ id: "chapter1", children: [new TextRun("第一章")] }),
]})
// 2. 引用该 bookmark
new Paragraph({ children: [new InternalHyperlink({
  children: [new TextRun({ text: "查看第一章", style: "Hyperlink" })],
  anchor: "chapter1",
})]})
```

### 脚注

```javascript
const doc = new Document({
  footnotes: {
    1: { children: [new Paragraph("来源：2024 年年度报告")] },
    2: { children: [new Paragraph("方法论详见附录")] },
  },
  sections: [{
    children: [new Paragraph({
      children: [
        new TextRun("收入增长 15%"),
        new FootnoteReferenceRun(1),
        new TextRun("（基于调整后口径）"),
        new FootnoteReferenceRun(2),
      ],
    })]
  }]
});
```

### 制表位（Tab Stops）

```javascript
// 在同一行上右对齐一段文字（如标题对齐日期）
new Paragraph({
  children: [
    new TextRun("公司名称"),
    new TextRun("\t2025 年 1 月"),
  ],
  tabStops: [{ type: TabStopType.RIGHT, position: TabStopPosition.MAX }],
})

// 带点状引导符（常用于目录）
new Paragraph({
  children: [
    new TextRun("引言"),
    new TextRun({ children: [
      new PositionalTab({
        alignment: PositionalTabAlignment.RIGHT,
        relativeTo: PositionalTabRelativeTo.MARGIN,
        leader: PositionalTabLeader.DOT,
      }),
      "3",
    ]}),
  ],
})
```

### 多栏排版

```javascript
// 等宽分栏
sections: [{
  properties: {
    column: {
      count: 2,          // 栏数
      space: 720,        // 栏间距（DXA，720 = 0.5 英寸）
      equalWidth: true,
      separate: true,    // 栏间竖线
    },
  },
  children: [/* 内容会在栏之间自然流动 */]
}]

// 自定义栏宽（equalWidth 必须为 false）
sections: [{
  properties: {
    column: {
      equalWidth: false,
      children: [
        new Column({ width: 5400, space: 720 }),
        new Column({ width: 3240 }),
      ],
    },
  },
  children: [/* 内容 */]
}]
```

如需强制分栏，可使用 `type: SectionType.NEXT_COLUMN` 新建 section。

### 目录

```javascript
// 重要：目录中的标题必须只使用 HeadingLevel，不要套自定义样式
new TableOfContents("目录", { hyperlink: true, headingStyleRange: "1-3" })
```

### 页眉 / 页脚

```javascript
sections: [{
  properties: {
    page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } // 1440 = 1 英寸
  },
  headers: {
    default: new Header({ children: [new Paragraph({ children: [new TextRun("页眉")] })] })
  },
  footers: {
    default: new Footer({ children: [new Paragraph({
      children: [new TextRun("第 "), new TextRun({ children: [PageNumber.CURRENT] }), new TextRun(" 页")]
    })] })
  },
  children: [/* 内容 */]
}]
```

### docx-js 的重要规则

- **显式设置页面大小** —— docx-js 默认 A4；美式文档请用 US Letter（12240 × 15840 DXA）
- **横向：按纵向值传参** —— docx-js 会在内部交换宽高；把短边作为 `width`、长边作为 `height`，再设 `orientation: PageOrientation.LANDSCAPE`
- **切勿使用 `\n`** —— 使用独立的 Paragraph
- **切勿使用 Unicode 项目符号** —— 使用 `LevelFormat.BULLET` + numbering 配置
- **PageBreak 必须在 Paragraph 内部** —— 独立使用会产生非法 XML
- **ImageRun 必须带 `type`** —— 永远显式指定 png / jpg 等
- **表格 `width` 必须用 DXA** —— 切勿使用 `WidthType.PERCENTAGE`（与 Google Docs 不兼容）
- **表格的"双重宽度"** —— `columnWidths` 数组与每个 cell 的 `width` 都要设，且数值必须匹配
- **表格宽度 = columnWidths 之和** —— 用 DXA 时必须精确相等
- **单元格 margin 必加** —— 使用 `margins: { top: 80, bottom: 80, left: 120, right: 120 }` 获得可读的内边距
- **使用 `ShadingType.CLEAR`** —— 切勿用 SOLID 给表格上色
- **切勿把表格当成分割线** —— cell 有最小高度，会渲染成空白框（在页眉页脚里更明显）；需要分隔线时请给 Paragraph 设 `border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: "2E75B6", space: 1 } }`。两列页脚请用 tab stops（见「制表位」一节），不要用表格
- **目录中的标题只能用 HeadingLevel** —— 标题段落上不要套自定义样式
- **覆盖内置样式** —— 必须使用精确 ID："Heading1"、"Heading2" 等
- **务必设 `outlineLevel`** —— 目录需要这个（H1 = 0，H2 = 1，依此类推）

---

## 编辑现有文档

**严格按下面 3 步依次进行。**

### 第 1 步：解包

```bash
python scripts/office/unpack.py document.docx unpacked/
```

该脚本会解包、美化 XML、合并相邻 run，并把智能引号转为 XML 实体（`&#x201C;` 等），避免编辑过程中被破坏。若想跳过 run 合并，使用 `--merge-runs false`。

### 第 2 步：编辑 XML

在 `unpacked/word/` 下编辑文件。常见写法见下文「XML 参考」。

**追踪修订和批注的默认作者使用「元宝」**，除非用户明确要求其他名字。

**直接使用 Edit 工具做字符串替换，不要写 Python 脚本。** 额外写脚本会引入不必要的复杂度，Edit 工具会清晰地展示要替换的内容。

**重要：新内容请使用智能引号。** 添加含单引号或双引号的文本时，使用 XML 实体以得到排版级的引号：

```xml
<!-- 下列实体可得到专业排版效果 -->
<w:t>Here&#x2019;s a quote: &#x201C;Hello&#x201D;</w:t>
```

| 实体 | 字符 |
| --- | --- |
| `&#x2018;` | '（左单引号） |
| `&#x2019;` | '（右单引号 / 撇号） |
| `&#x201C;` | "（左双引号） |
| `&#x201D;` | "（右双引号） |

**添加批注：** 使用 `comment.py` 替你处理跨多个 XML 文件的样板（文本必须是预先转义的 XML）：

```bash
python scripts/comment.py unpacked/ 0 "带 &amp; 和 &#x2019; 的批注文本"
python scripts/comment.py unpacked/ 1 "回复文本" --parent 0  # 回复批注 0
python scripts/comment.py unpacked/ 0 "正文" --author "自定义作者"  # 指定作者名
```

然后在 `document.xml` 中补上标记（见下文 XML 参考的「批注」一节）。

### 第 3 步：打包

```bash
python scripts/office/pack.py unpacked/ output.docx --original document.docx
```

该脚本会自动做带自动修复的校验、压缩 XML 格式，再打成 DOCX。若想跳过校验使用 `--validate false`。

**自动修复会处理：**
- `durableId` ≥ `0x7FFFFFFF`（重新生成合法 ID）
- `<w:t>` 含首尾空白但缺失 `xml:space="preserve"`

**自动修复不会处理：**
- 非法 XML、错误的元素嵌套、缺失的关系、schema 违规

### 常见陷阱

- **整段替换 `<w:r>` 元素**：添加 tracked changes 时，把整个 `<w:r>...</w:r>` 替换为 `<w:del>...<w:ins>...` 作为**兄弟节点**；不要把修订标签塞进 run 内部。
- **保留 `<w:rPr>` 格式**：把原 run 的 `<w:rPr>` 原样复制到修订 run 中，以保留粗体、字号等。

---

## XML 参考

### schema 合规

- **`<w:pPr>` 子元素顺序**：`<w:pStyle>`、`<w:numPr>`、`<w:spacing>`、`<w:ind>`、`<w:jc>`；`<w:rPr>` 放最后
- **空白**：`<w:t>` 如有首尾空白，必须加 `xml:space="preserve"`
- **RSID**：必须是 8 位十六进制（如 `00AB1234`）

### 追踪修订（tracked changes）

**插入：**

```xml
<w:ins w:id="1" w:author="元宝" w:date="2025-01-01T00:00:00Z">
  <w:r><w:t>插入的文本</w:t></w:r>
</w:ins>
```

**删除：**

```xml
<w:del w:id="2" w:author="元宝" w:date="2025-01-01T00:00:00Z">
  <w:r><w:delText>被删除的文本</w:delText></w:r>
</w:del>
```

**在 `<w:del>` 内部**：使用 `<w:delText>` 代替 `<w:t>`；使用 `<w:delInstrText>` 代替 `<w:instrText>`。

**最小化编辑**：只标记真正改动的部分：

```xml
<!-- 把「30 天」改为「60 天」 -->
<w:r><w:t>期限为 </w:t></w:r>
<w:del w:id="1" w:author="元宝" w:date="...">
  <w:r><w:delText>30</w:delText></w:r>
</w:del>
<w:ins w:id="2" w:author="元宝" w:date="...">
  <w:r><w:t>60</w:t></w:r>
</w:ins>
<w:r><w:t> 天。</w:t></w:r>
```

**删除整个段落 / 列表项** —— 当清空一个段落的全部内容时，把**段落符本身**也标记为删除，让它与下一个段落合并。方法是在 `<w:pPr><w:rPr>` 中加 `<w:del/>`：

```xml
<w:p>
  <w:pPr>
    <w:numPr>...</w:numPr>  <!-- 如果是列表项，保留 numbering -->
    <w:rPr>
      <w:del w:id="1" w:author="元宝" w:date="2025-01-01T00:00:00Z"/>
    </w:rPr>
  </w:pPr>
  <w:del w:id="2" w:author="元宝" w:date="2025-01-01T00:00:00Z">
    <w:r><w:delText>被整段删除的内容……</w:delText></w:r>
  </w:del>
</w:p>
```

如果不给 `<w:pPr><w:rPr>` 加 `<w:del/>`，接受修订后会留下一个空段落或空列表项。

**拒绝他人的插入** —— 在对方的 `<w:ins>` 内部嵌套一个 `<w:del>`：

```xml
<w:ins w:author="Jane" w:id="5">
  <w:del w:author="元宝" w:id="10">
    <w:r><w:delText>对方插入的文本</w:delText></w:r>
  </w:del>
</w:ins>
```

**恢复他人的删除** —— 在对方 `<w:del>` **之后**新增一个 `<w:ins>`（不要去改对方的 `<w:del>`）：

```xml
<w:del w:author="Jane" w:id="5">
  <w:r><w:delText>被删除的文本</w:delText></w:r>
</w:del>
<w:ins w:author="元宝" w:id="10">
  <w:r><w:t>被删除的文本</w:t></w:r>
</w:ins>
```

### 批注

运行 `comment.py` 之后（见「第 2 步」），在 `document.xml` 中补上标记。对于回复，使用 `--parent` 标志，并把回复的标记嵌套在父批注标记之内。

**重要：`<w:commentRangeStart>` 与 `<w:commentRangeEnd>` 是 `<w:r>` 的兄弟节点，**不能**放在 `<w:r>` 内部。**

```xml
<!-- 批注标记是 w:p 的直接子元素，永远不放进 w:r -->
<w:commentRangeStart w:id="0"/>
<w:del w:id="1" w:author="元宝" w:date="2025-01-01T00:00:00Z">
  <w:r><w:delText>被删除</w:delText></w:r>
</w:del>
<w:r><w:t> 其他文本</w:t></w:r>
<w:commentRangeEnd w:id="0"/>
<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="0"/></w:r>

<!-- 批注 0，内部嵌套回复 1 -->
<w:commentRangeStart w:id="0"/>
  <w:commentRangeStart w:id="1"/>
  <w:r><w:t>text</w:t></w:r>
  <w:commentRangeEnd w:id="1"/>
<w:commentRangeEnd w:id="0"/>
<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="0"/></w:r>
<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr><w:commentReference w:id="1"/></w:r>
```

### 图片

1. 把图片文件放入 `word/media/`
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

---

## 依赖

运行本技能的环境已预装下列组件，按上文命令直接调用即可，无需在本机另行安装或配置：

- **pandoc**：正文提取
- **docx**：`npm install -g docx`（新建文档）
- **LibreOffice**：PDF / DOC / DOCX 转换（`scripts/office/soffice.py` 已为沙箱环境做兼容）
- **Poppler**：`pdftoppm`，PDF 转图片
