# 场景：创建和导入文档

**快捷命令：**
```bash
# 创建 Markdown 文档（从命令行指定内容）
iwiki-cli create --parent 67890 --title "新文档" --body "# 内容..."

# 创建文档（从文件读取内容）
iwiki-cli create --parent 67890 --title "新文档" --file ./content.md

# 指定空间和文档类型
iwiki-cli create --space 12345 --parent 67890 --title "新文档" --type MD --file ./content.md

# 导入本地 Markdown 文件
iwiki-cli import --parent 4017403457 --file ./doc.md

# 导入 Word 文档
iwiki-cli import --parent 4017403457 --file ./doc.docx --type doc_import

# 导入 ZIP 压缩包
iwiki-cli import --parent 4017403457 --file ./docs.zip

# 导入 HTML 文件（需将 html 及其资源打包为 zip）
iwiki-cli import --parent 4017403457 --file ./page.zip --type ctx_import

# 更新已存在的 HTML 文档（按 docid 查父目录后同名覆盖，仅支持 .html/.htm）
iwiki-cli update-html 4017403457 --file ./page.html
```

## 工作流程

```mermaid
graph LR
    A[用户需求] --> B{操作类型}
    B -->|在线创建| C[确定空间和父目录]
    B -->|导入本地文件| D[准备文件]
    C --> E[create 创建文档]
    D --> F[import 导入文件]
    E --> G[文档创建成功]
    F --> H{导入成功?}
    H -->|是| G
    H -->|否| I[检查文件格式和权限]
```

## 核心工具

### 1. create - 在线创建文档
**用途：** 在 iWiki 中创建新文档
**用法：**
```bash
iwiki-cli create --parent <parentid> --title <title> [options]
```
**参数：**
| 参数 | 缩写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--space` | `-s` | 否 | 0 | 空间 ID（不指定则自动从 parent 文档元数据获取） |
| `--parent` | `-p` | **是** | 0 | 父文档 ID |
| `--title` | `-t` | **是** | "" | 文档标题 |
| `--type` | | 否 | "MD" | 文档类型：MD / DOC / FOLDER / VIKA |
| `--file` | `-f` | 否 | "" | 从文件读取内容 |
| `--body` | `-b` | 否 | "" | 直接指定文档内容 |

**内容类型说明：**
| type | 说明 | 推荐格式 |
|------|------|----------|
| `MD` | Markdown 文档 |  |
| `DOC` | 富文本文档 |  |
| `FOLDER` | 文件夹 | 无需 body |
| `VIKA` | 多维表格 | 特殊格式 |


### 2. import - 导入本地文件
**用途：** 将本地文件直接导入到 iWiki
**支持的文件类型：**
- Markdown 文件（`.md`）
- Word 文档（`.docx`）
- Zip 压缩包（包含 `.md` 和 `.docx`，支持附件）
- HTML 文件（需打包为 `.zip`，指定 `--type ctx_import`）

**用法：**
```bash
# 导入 Markdown 文件
iwiki-cli import --parent 4017403457 --file ./doc.md

# 导入 Word 文档
iwiki-cli import --parent 4017403457 --file ./doc.docx --type doc_import

# 导入为富文本格式
iwiki-cli import --parent 4017403457 --file ./doc.md --type md_import_doc

# 导入 zip 压缩包（包含多个文档和附件）
iwiki-cli import --parent 4017403457 --file ./docs.zip

# 导入 HTML（将 html 及其引用的资源文件打包为 zip）
iwiki-cli import --parent 4017403457 --file ./page.zip --type ctx_import
```

**参数说明：**
| 参数 | 缩写 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `--parent` | `-p` | **是** | 0 | 父文档/目录 ID |
| `--file` | `-f` | **是** | "" | 本地文件路径 |
| `--type` | `-t` | 否 | 自动推断 | 导入类型：md_import / md_import_doc / doc_import / ctx_import |

> `--parent` 与 `--space` 至少需指定一个；若同时指定，**以 `--parent` 为准**，`--space` 将被忽略并给出提示。


### 3. 空间信息查询工具
#### space - 根据空间 Key 查询
**用途：** 获取空间的 ID 和详细信息
**用法：**
```bash
iwiki-cli space devcloud
iwiki-cli space ~myname    # 个人空间
```

**URL 与 Key 的对应关系：**
| URL | Space Key |
|-----|-----------|
| `https://iwiki.woa.com/space/~myname` | `~myname` |
| `https://iwiki.woa.com/space/devcloud` | `devcloud` |

**返回内容：**
```
ID:   12345
Key:  devcloud
名称: 研发云平台
类型: global
描述: ...
```

### 4. 查询用户最近文档（辅助确定空间）
#### whoami - 获取当前登录用户（推荐优先使用）
**何时使用：**
- 用户说"在我的空间下写入"、"我的空间"、"我的首页"
- 需要确定当前用户的个人空间

**用法：**
```bash
# 获取当前用户名
iwiki-cli whoami

# 然后用 ~<username> 作为空间 Key 查询个人空间信息
iwiki-cli space ~<username>
```

**工作流程：**
1. 执行 `iwiki-cli whoami` 获取当前登录用户的 `username`（如 `jaxxonli`）
2. 构造空间 Key：`~<username>`（如 `~jaxxonli`）
3. 使用 `iwiki-cli space ~<username>` 获取个人空间的 ID 和详细信息
4. 以该空间作为目标空间进行创建/导入操作

#### recent edit / recent view - 确定用户活跃空间（兜底方案）
**何时使用：**
- 用户说"在我的空间下写入"但未指定空间
- 需要推断用户的常用空间

**用法：**
```bash
# 获取最近编辑文档，从中确定用户活跃空间
iwiki-cli recent edit --page_size 5

# 通过文档 ID 获取元数据，确认所属空间
iwiki-cli metadata <doc_id>
```

**工作流程：**
1. 通过 `recent edit` 获取用户最近编辑的文档列表
2. 取第一篇文档的 `doc_id`，使用 `metadata` 获取其空间信息
3. 以该空间作为目标空间进行创建操作

## 实践示例
### 示例 1：在 iWiki 中创建 Markdown 文档
**用户需求：** "在 devcloud 空间创建一个技术文档"
**执行步骤：**
1. **查询空间信息**
```bash
iwiki-cli space devcloud
```
2. **确定父目录**
```
假设要创建在根目录，parentid = 0
或使用 tree 命令查找特定目录
```
3. **创建文档**
```bash
iwiki-cli create --parent 0 --title "微服务架构设计" --body "# 微服务架构设计

## 概述

本文介绍..."
```

或从文件创建：
```bash
iwiki-cli create --parent 0 --title "微服务架构设计" --file ./architecture.md
```


### 示例 2：导入本地 Markdown 文件
**用户需求：** "将 README.md 导入到父目录 4017403457"
1. **执行导入**
```bash
iwiki-cli import --parent 4017403457 --file ./README.md
```
2. **等待导入完成**
```
命令会自动显示导入状态
```
### 示例 3：批量导入文档（使用 zip）
**用户需求：** "将整个文档目录导入到 iWiki"
**执行步骤：**
1. **准备 zip 文件**
```bash
zip -r docs.zip docs/
```
2. **执行导入**
```bash
iwiki-cli import --parent 4017403457 --file ./docs.zip
```

### 示例 4：处理 Drawio SVG 图片
**用户需求：** "导入包含 drawio 图片的 Markdown 文档"
**执行步骤：**
1. **询问用户确认**
```
"您的文档中包含以下图片：
- architecture.drawio.svg
- flow.svg
- logo.png

哪些是 drawio 类型的图片？是否需要指定尺寸？"
```

2. **用户回复**
```
"architecture.drawio.svg 是 drawio，宽度 800，高度 600
flow.svg 也是 drawio，不需要指定尺寸"
```
3. **修改 Markdown**
```markdown
# 系统设计
普通图片：
![Logo](./images/logo.png)

Drawio 架构图（指定尺寸）：
![架构图](./images/architecture.drawio.svg?type=drawio_svg&width=800&height=600)

Drawio 流程图（无尺寸）：
![流程图](./images/flow.svg?type=drawio_svg)
```

4. **打包并导入**
```bash
# 打包 Markdown 和图片
zip -r doc_with_drawio.zip doc.md images/

# 导入
iwiki-cli import --parent 4017403457 --file ./doc_with_drawio.zip
```

### 示例 5：导入 HTML 文件
**用户需求：** "将本地 HTML 页面导入到 iWiki"
**执行步骤：**
1. **准备文件**
```
将 HTML 文件及其引用的资源（图片、CSS 等）放在同一目录下，然后打包为 zip。
HTML 文件中引用资源使用相对路径。
```
2. **打包为 zip**
```bash
zip -r page.zip index.html images/ css/
```
3. **执行导入**
```bash
iwiki-cli import --parent 4017403457 --file ./page.zip --type ctx_import
```

> **注意：** HTML 导入必须手动指定 `--type ctx_import`，CLI 不会自动推断。文件需要打包为 zip 格式上传。

### 示例 6：更新已存在的 HTML 文档（update-html）
**用户需求：** "我之前已经导入了一篇 HTML 文档，现在想用本地新版本覆盖更新它"

**用法：**
```bash
iwiki-cli update-html <docid> --file <local_file>
```

**执行示例：**
```bash
# 用本地 page.html 覆盖更新文档 4012571776
iwiki-cli update-html 4012571776 --file ./page.html
```

## 注意事项

1. **空间 ID 必须确认：** 创建前必须获取正确的空间 ID（不指定 --space 时会自动从 parent 获取）
2. **临时文件要清理：** 创建的临时 zip 文件要在完成后删除
3. **导入类型自动推断：** 不指定 --type 时，CLI 会根据文件扩展名自动推断
4. **Drawio 图片要确认：** 不要自动判断，必须询问用户
5. **审批文档限制：** 不支持在需要审批的目录下操作
6. **内容非空检查：** body 不能为空字符串
