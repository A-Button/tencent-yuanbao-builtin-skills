# cmd-manage — 文件管理

使用 `tdocs-cli manage ...` 管理腾讯文档中的文件：创建、列出、搜索、移动、复制、删除、重命名、查看元数据、控制权限、管理空间、上传下载。

从本地导入文件或导出到本地请使用 workflow 命令（见 `cmd-workflow.md`）。

## 能力分类

| 分类 | 包含的能力 | CLI 命令 |
|---|---|---|
| 创建 | 创建空白文件（**仅允许 smartcanvas / doc / mind / flowchart**；`sheet` 与 `smartsheet` 类型已对本 skill 关闭，禁止用 `--file-type sheet` 或 `--file-type smartsheet`） | `manage create-file` |
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
| 空间管理 | 查询知识库空间列表 | `manage query-space-list` |
| 空间管理 | 创建知识库空间 | `manage create-space` |
| 空间管理 | 查询空间节点 | `manage query-space-node` |
| 空间管理 | 创建空间节点 | `manage create-space-node` |
| 空间管理 | 删除空间节点 | `manage delete-space-node` |
| 上传 | 申请上传链接 | `manage apply-upload` |
| 上传 | 上传完成通知 | `manage complete-upload` |
| 下载 | 申请下载（导出） | `manage apply-download` |
| 容量 | 查询用户容量使用空间 | `manage query-capacity` |
| 任务查询 | 查询异步任务状态 | `manage query-task` |
| 网页剪藏 | 提交剪藏任务（异步） | `manage scrape-url` |
| 网页剪藏 | 查询剪藏任务进度（异步） | `manage scrape-progress` |

## 代表性示例

```
tdocs-cli manage create-file --type 8 --title demo  # 8 = smartcanvas（首选）；禁止用 sheet / smartsheet 类型
tdocs-cli manage list-file --jq '.[] | {id, title, type}'
tdocs-cli manage apply-download --file-id <file-id>
tdocs-cli manage query-task --task-id <task-id>
```

## 删除文档白名单（硬性约束）

`manage delete-file` 是**永久删除文档**的高风险操作。本 skill 对其做严格限制：

### 允许删除的范围（白名单）

仅当**同时满足**以下两个条件时，才允许调用 `manage delete-file`：

1. 待删除的 `file_id` 是**本次会话中由当前 Agent 通过以下命令亲手创建/导入**的：
   - `manage create-file`
   - `smartcanvas create-by-mdx`
   - `mind create-by-markdown`
   - `flowchart create-by-mermaid`
   - `workflow import-file`
   - `manage scrape-url` + `scrape-progress` 的产物
   - `ocr images-to-excel` / `ocr images-to-word`
2. 该 `file_id` 在本次会话上下文中**有明确记录**（来自命令的 stdout，可追溯）。

### 禁止删除的范围（黑名单）

以下情况**一律禁止调用** `manage delete-file`，即使用户明确要求"删掉"：

- 用户在请求中**直接提供的 file_id 或文档链接**（视为存量文档）
- 通过 `manage search-file` / `manage ai-search-file` / `manage list-file` / `space query-space-node` 检出的文档
- 用户网盘中已存在、非本次会话产生的任何文档
- 不确定来源的 `file_id`

### 用户要求删除存量文档时的应答

当用户要求删除不在白名单内的文档时，**禁止**调用 `manage delete-file`，应回复：

> 出于安全考虑，我不会通过 CLI 删除你已有的文档。请你在腾讯文档前端（docs.qq.com）打开该文件后自行操作"删除"或"移到回收站"。

### 唯一例外：清理本会话中刚创建的临时文档

如果在本次会话中刚通过 CLI 创建/导入的文档需要回滚，可以删除——但应在调用前向用户说明"我将删除刚才由我创建的文档 `<file_id>`"。

## 常见后续操作

- 创建文件后 → 用 `--jq '.file_id'` 获取 file ID，继续在 sheet / smartcanvas / smartsheet / doc 中操作。
- 导入本地文件 → 转到 `cmd-workflow.md`（`workflow import-file`）。
- 下载到本地 → 转到 `cmd-workflow.md`（`workflow export-file`）。
- 网页剪藏完整流程（`scrape-url` + `scrape-progress` 异步轮询）→ 转到 `cmd-workflow.md`「网页剪藏」章节。

## 权威来源

```
tdocs-cli manage --help
tdocs-cli manage <command> --help
```
