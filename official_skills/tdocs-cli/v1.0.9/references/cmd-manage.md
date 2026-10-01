# cmd-manage — 文件管理

使用 `tdocs-cli manage ...` 管理腾讯文档中的文件：创建、列出、搜索、移动、复制、删除、重命名、查看元数据、控制权限、管理空间、上传下载。

从本地导入文件或导出到本地请使用 workflow 命令（见 `cmd-workflow.md`）。

## 能力分类

| 分类 | 包含的能力 | CLI 命令 |
|---|---|---|
| 创建 | 创建空白文件（允许 doc / mind / flowchart；smartcanvas 仅在用户明确要求时创建；`sheet` 与 `smartsheet` 类型已关闭） | `manage create-file` |
| 列出 | 获取文件列表 | `manage list-file` |
| 搜索 | 按名称搜索文件 | `manage search-file` |
| 搜索 | AI 智能搜索文件 | `manage ai-search-file` |
| 查看 | 查询文件信息（标题、类型、创建时间等） | `manage query-file-info` |
| 查看 | 获取文件内容 | `manage get-content` |
| 元数据变更 | 重命名文档标题 | `manage rename-file-title` |
| 元数据变更 | 移动文档 | `manage move-file` |
| 元数据变更 | 创建文档副本 | `manage copy-file` |
| 删除 | 删除文档（**白名单**：仅可删除本次会话由当前 Agent 创建/导入的文档，详见下文「删除文档白名单」） | `manage delete-file` |
| 权限 | 查询文档权限 | `manage get-privilege` |
| 权限 | 设置文档权限 | `manage set-privilege` |
| 空间管理 | 知识库空间：创建 / 查询列表 / 查询节点（**属 `space` 服务，不在 `manage` 下**） | 见 `cmd-space.md`：`space create-space`、`space query-space-list`、`space query-space-node` |
| 上传 | 申请上传链接 | `manage apply-upload` |
| 上传 | 上传完成通知 | `manage complete-upload` |
| 下载 | 申请下载（导出） | `manage apply-download` |
| 任务查询 | 查询异步任务状态 | `manage query-task` |
| 网页剪藏 | 提交剪藏任务（异步） | `manage scrape-url` |
| 网页剪藏 | 查询剪藏任务进度（异步） | `manage scrape-progress` |

## 代表性示例

```
tdocs-cli manage create-file --type 8 --title demo  # 8 = smartcanvas，仅用户明确要求时使用
tdocs-cli manage list-file --list-type 1 --jq '.files[] | {file_id, name, ext}'
tdocs-cli manage apply-download --file-id '<file_id>'
tdocs-cli manage query-task --task-id <task-id>
```

## 权限与分享

- 用户要求分享、公开访问或协作编辑时，可先用 `manage get-privilege` 了解现状，再用 `manage set-privilege` 设置满足目标的最小权限。
- 公开只读使用 `PUBLIC_READ`；只有用户明确要让他人协作编辑时才使用 `PUBLIC_WRITE`。
- “打不开 / 无权限”本身不代表用户要求扩大权限；没有分享意图时只做只读诊断并说明现状。
- 权限设置不改变删除白名单；用户存量文档仍禁止通过 CLI 删除。

## search-file 搜索文件（参数详解）

`manage search-file` 有 **3 个必填参数**，且均为 object/string 结构，缺一即报 `400001`。务必按下表传全。

| 参数 | 必填 | 类型 | 说明 |
|---|---|---|---|
| `--pattern` | ✅ | string | 匹配内容（搜索词）。**词序敏感**：词的顺序会影响召回，建议用目标文档**标题中的连续原文片段**，不要打乱词序。 |
| `--tag-info` | ✅ | object | 匹配方式，形如 `{"tag_type":1,"from":0,"size":10}`。`tag_type`：`1`=标题匹配（**推荐，无需 VIP**）、`0`=CONTENT 正文匹配（**需 VIP/专业版**，非会员会报 `400001`）；`size`（必填，>0）单次返回条数；`from` 起始条目编号。 |
| `--sort-rules` | ✅ | object | 排序规则，形如 `{"sort_by":0,"asc":false}`。`sort_by` 排序字段、`asc` 是否升序。 |

可选过滤：`--owner-filter` / `--ext-filter` / `--folder-filter` / `--range` / `--space-filter` 等（均为 object，详见 `--help`）。

```bash
# 标题精确搜（推荐，无需 VIP）：用标题原文连续片段，保持词序
tdocs-cli manage search-file \
  --pattern "项目周报" \
  --tag-info '{"tag_type":1,"from":0,"size":10}' \
  --sort-rules '{"sort_by":0,"asc":false}'
```

> 已知限制：正文搜（`tag_type":0`）需 VIP/专业版，非会员请改用 `tag_type":1` 标题搜；若标题搜不到，再用 `manage get-content` 通读定位，不要依赖 `manage ai-search-file`（召回质量不稳定）。

## 读取文档工作流：先拿 `file_id`，再 `get-content`

通读已有腾讯文档的标准顺序：

1. **解析 / 查找 `file_id`**（见下节 `query-file-info`；也可 `search-file` / `list-file`，或复用创建/导入返回值）
2. **`manage get-content --file-id ...`** 一次通读纯文本

用户给了 `docs.qq.com` 链接时，**优先**用 `query-file-info --url`，不要把 URL 直接塞进 `--file-id`（会报 `invalid file_id`）。

## query-file-info 查询文件信息（拿 `file_id` / 补链接）

按 **链接** 或已有 **file_id** 查询文档元信息。有链接反查 ID、导入后补标题/链接时用它。

### 参数（二选一；同时提供时 `--file-id` 优先）

| 参数 | 必填 | 说明 |
|---|---|---|
| `--url` | 二选一 | 文档链接。传入则按 URL 查文件信息；**有链接时优先用这个拿 `file_id`** |
| `--file-id` | 二选一 | 已有文件 ID；与 `--url` 同时提供时忽略 URL，以此值为准 |
| `--need-policy` 等 | 否 | 是否附带权限/用户/空间等扩展信息，详见 `--help` |

### 响应要点

成功时主体在 `.file`：

- `.file.file_id`：后续 `get-content` / 编辑命令要用的 ID
- `.file.name`：标题
- `.file.doc_url` / `.file.tencent_doc_url`：文档链接
- `.file.ext` / `.file.doc_type`：品类

### 调用示例

```bash
# 有链接 → 反查 file_id（推荐）
tdocs-cli manage query-file-info --url 'https://docs.qq.com/doc/xxxx' --jq '.file.file_id'

# 已有 file_id → 补查标题 / 链接（如 import-file 返回 file_url 为空时）
tdocs-cli manage query-file-info --file-id '<file_id>' --jq '.file | {file_id, name, doc_url}'
```

## get-content 获取文件内容

`manage get-content` 是**非分页**通读接口：一次拉取整篇纯文本，适用于 DOC / smartcanvas / mind / flowchart / 网盘文本（`txt`）等。需要"读完整篇再判断 / 验收"时优先用它，而不是分页的 `smartcanvas read`。调用前须先有合法 `file_id`（见上节 `query-file-info`）。

### 参数

| 参数 | 必填 | 说明 |
|---|---|---|
| `--file-id` | ✅ | 文件 ID。字面量用单引号（可能含 `$`）；shell 变量用双引号。 |

无其它业务参数。全局可用 `--format` / `--jq` / `--timeout`（默认 30s）等，详见 `output-and-debug.md`。

### 响应结构

成功时固定返回：

```json
{
  "title": "文档标题",
  "content": "纯文本正文……"
}
```

- `title`：文档标题。
- `content`：整篇纯文本（含换行）。是抽取后的纯文本，**不是**原始 Markdown / MDX / Mermaid 源码；标题层级与样式会扁平化（例如 DOC 的 `##` 可能只剩标题文字；flowchart 多为节点文案拼接）。
- 无分页字段（无 `next_token`）；一次调用即全文。

### 调用示例

```bash
# 通读整篇
tdocs-cli manage get-content --file-id '<file_id>'

# 只要正文纯文本
tdocs-cli manage get-content --file-id '<file_id>' --jq '.content'

# 只要标题
tdocs-cli manage get-content --file-id '<file_id>' --jq '.title'

# 大文档：正文按纯文本落盘，再用 Read 分段读完
tdocs-cli manage get-content --file-id '<file_id>' \
  --jq '.content' --format plain > /tmp/<name>.txt
```

### 约束与错误

- **通读必须读全**：stdout **禁止**套 `| head` / `| tail` / `[:N]` 等截断后当作已读完整篇；大文档按上例将 `.content` 以 plain 文本落盘，再用 `Read` 工具分段读完。
- 缺 `--file-id` → 本地校验：`required flag not provided`。
- 无效 / 无权限的 `file_id` → 常见 `retcode 400010`（内部错误）或权限类错误；按本文件“权限与分享”处理，不要把访问失败自行解释成用户要求扩大权限。
- 单独使用 `--format plain` 仍可能输出 JSON 对象文本；提取纯文本正文时使用 `--jq '.content' --format plain`。

## 删除文档白名单（硬性约束）

`manage delete-file` 是移入回收站或继续清理文档的高风险操作。本 skill 对其做严格限制：

### 允许删除的范围（白名单）

仅当**同时满足**以下两个条件时，才允许调用 `manage delete-file`：

1. 待删除的 `file_id` 是**本次会话中由当前 Agent 通过以下命令亲手创建/导入**的：
   - `manage create-file`
   - `doc create-with-markdown`
   - `smartcanvas create-smartcanvas-by-mdx`
   - `mind create-by-markdown`
   - `flowchart create-by-mermaid`
   - `workflow import-file`
   - `manage scrape-url` + `scrape-progress` 的产物
   - `ocr images-to-excel` / `ocr images-to-word`
2. 该 `file_id` 在本次会话上下文中**有明确记录**（来自命令的 stdout，可追溯）。

### 替换版本必须先上传，再判断是否删除旧版

即使旧文档的 `file_id` 落在删除白名单内，更新时也**不得先删旧版再创建或导入新版**。用户可能正在查看原链接；先删会让链接立即失效，而新版还可能生成失败。

- **能原位编辑就原位编辑**：复用原 `file_id`，用该类型已开放的增量编辑能力修改，链接保持不变。
- **确需产出新版本时**：先创建或导入新版并确认可访问、可交付；新版文件名追加递增后缀 `V2`、`V3`……（原文件名已是 `V2` 则用 `V3`），正文内容不加版本号。
- **新版确认后再判断旧版价值**：旧版有价值或判断不清时保留，并向用户说明新旧两条链接；只有旧版同样由当前 Agent 在本次会话创建/导入、且确认无保留价值时，才可按白名单清理。

例：原文档《季度总结》产出新版本时先命名为《季度总结V2》并完成验收；原《季度总结》是否保留，在新版可交付后再按上述规则判断。

### 禁止删除的范围（黑名单）

以下情况**一律禁止调用** `manage delete-file`，即使用户明确要求"删掉"：

- 用户在请求中**直接提供的 file_id 或文档链接**（视为存量文档）
- 通过 `manage search-file` / `manage ai-search-file` / `manage list-file` / `space query-space-node` 检出的文档
- 用户网盘中已存在、非本次会话产生的任何文档
- 不确定来源的 `file_id`

### 用户要求删除存量文档时的应答

当用户要求删除不在白名单内的文档时，**禁止**调用 `manage delete-file`，应回复：

> 出于安全考虑，我不会通过 CLI 删除你已有的文档。请你在腾讯文档前端（docs.qq.com）打开该文件后自行操作"删除"或"移到回收站"。

### 清理本会话产物的条件

本次会话由当前 Agent 创建/导入的临时产物、失败产物或已被验收新版替代且确认无价值的旧版，可以清理。调用前必须再次用会话记录精确匹配 `file_id`；来源或价值判断不清时保留。

### 必填参数与调用示例

`manage delete-file` 除 `--file-id` 外，`--delete-type` 与 `--remove-type` **均为必填**，缺任一都会本地校验失败：

| 参数 | 必填 | 说明（取值以 `--help` 为准） |
|---|---|---|
| `--file-id` | ✅ | 待删除文档 ID，单引号包裹（可能含 `$`） |
| `--delete-type` | ✅ | 删除类型，仅对首页文件有效：`1`=全部文档 / `2`=回收站 / `3`=共享 / `4`=历史 |
| `--remove-type` | ✅ | 节点删除类型，仅对空间节点有效：`1`=当前节点 / `2`=全部节点 |

`--delete-type 1` 将首页文档移入回收站，仍可恢复：

```
tdocs-cli manage delete-file --file-id '<file_id>' --delete-type 1 --remove-type 1
```

只有白名单内的测试夹具或明确要求彻底清理的本会话产物，才在移入回收站后继续用 `--delete-type 2` 从回收站删除。对外必须如实区分“已移入回收站”和“已从回收站删除”，不得把前者称为永久删除。

## 改标题：文件名与正文标题是两回事

腾讯文档有两个「标题」，用户说"改标题"时通常两个都想改，至少期望打开文档后最上面那行发生变化：

| 「标题」 | 用户在哪看到 | 用什么改 |
|---|---|---|
| 文件名 | 文件列表、标签页、分享卡片 | `manage rename-file-title` |
| 正文一级标题 | 打开文档后最上面那行 | 按文档类型走对应入口，DOC 见 `cmd-doc.md`（`doc find` 定位后 `doc replace-text`） |

- 用户明确说文件名 / 分享标题时，只改文件名；明确说正文标题 / 一级标题时，只改正文。
- 两处当前相同或明显对应，且用户泛称“文档标题”时，可以同步修改。
- 两处明显不同且上下文不能消歧时，先询问用户，不要擅自同步。
- 用户点名的是文档内的**章节标题**（如"把第三章标题改成 X"）时，只改该章节标题，不要动文件名和正文一级标题。
- 改完向用户说明实际更新的是文件名、正文标题还是两者。

## 常见后续操作

- 创建文件后 → 记录返回的 `file_id`，按真实文档类型转到对应入口：DOC 见 `cmd-doc.md`，smartcanvas 见 `cmd-smartcanvas.md`，思维导图 / 流程图分别见 `cmd-mind.md` / `cmd-flowchart.md`。
- 已有在线 Sheet 的明确小改 → 按 `cmd-sheet.md` 判断有限白名单与调用预算；新建 Sheet 仍转为本地处理。
- 导入本地文件 → 转到 `cmd-workflow.md`（`workflow import-file`）。
- 下载到本地 → 转到 `cmd-workflow.md`（`workflow export-file`）。
- 网页剪藏完整流程（`scrape-url` + `scrape-progress` 异步轮询）→ 转到 `cmd-workflow.md`「网页剪藏」章节。

## 权威来源

```
tdocs-cli manage --help
tdocs-cli manage <command> --help
```
