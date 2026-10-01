# cmd-workflow — 跨命令组合工作流

本文档汇总需要"提交 + 轮询"或"多步组合"的能力。涉及多次 CLI 调用，统一在此查阅。

## 能力分类

| 分类 | 能力 | CLI 命令 |
|---|---|---|
| 导入 | 将本地文件上传到腾讯文档 | `workflow import-file` |
| 导出 | 将腾讯文档导出下载到本地 | `workflow export-file` |
| 网页剪藏 | 把指定 URL 的网页剪藏为腾讯文档 | `manage scrape-url` + `manage scrape-progress` |

---

## workflow import-file

将本地文件上传到腾讯文档。

- 用户提供现成 `.xlsx` / `.xls` / `.pptx` 且无需修改内容时，直接导入；同一本地版本只执行一次 `import-file`。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--file` | ✅ | 本地文件路径，文件名默认作为文档标题 |
| `--poll-interval-secs` |  | 轮询间隔，默认 3 |
| `--poll-timeout-secs`  |  | 轮询超时，默认 600，大文件需调高 |

```
tdocs-cli workflow import-file --file ./report.xlsx
```

> **已知限制（输出）**：`workflow import-file` **不响应 `--jq` / `--format`**，无论是否带这两个标志都只打印固定的完整 JSON（含 `file_id` / `file_name` / `file_url` 三个字段）。因此**不要**指望 `--jq '.file_id'` 直接吐出裸 ID，而应从返回 JSON 中读取 `file_id` 字段值。
>
> **已知限制（取链接）**：返回的 `file_url` / `file_name` 为空**不等于失败**。只用返回的 `file_id` 调一次 `manage query-file-info --file-id '<fid>'`（务必单引号，id 可能含 `$`）补取标题和链接；仍为空则说明限制，不重复导入。

### 导入后的二次编辑

- DOC 继续编辑时复用导入返回的同一 `file_id`。
- 已有在线 Sheet 的明确小改按 `cmd-sheet.md` 执行；复杂 Sheet 或 PPT 需修改时，复用本地源文件或先导出，再用 `xlsx` / `pptx` skill 修改并验收，最后只导入一次新资源。
- 当前 CLI 没有目标 `file_id` / overwrite 参数；交付时明确说明“新版本链接，原链接未覆盖”。

---

## workflow export-file

将腾讯文档导出下载到本地。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--file-id` | ✅ | 云端文档 ID |
| `--dir`     | ✅ | 导出文件写入的本地目录；调用前确保目录已存在 |
| `--poll-interval-secs` |  | 轮询间隔，默认 3 |
| `--poll-timeout-secs`  |  | 轮询超时，默认 600 |

```
tdocs-cli workflow export-file --file-id '<file_id>' --dir ./downloads
```

> **已知限制（文件名编码）**：`export-file` 返回的 `file_name` / `local_path` 可能是 URL 百分号编码（如 `%E7%94%BB%E5%B8%83` = "画布"）。下游若要用文件名展示或再处理，需先做 urldecode 解码，不要直接把编码串当作真实文件名。

---

## 网页剪藏（scrape-url）

异步两步流程：`manage scrape-url` 提交剪藏任务 → `manage scrape-progress` 轮询直到完成。

### 第 1 步：提交剪藏任务

```
tdocs-cli manage scrape-url --url <网页URL>
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--url` | ✅ | 要剪藏的网页 URL（http/https） |

**返回**：`task_id`（异步任务 ID），用 `--jq '.task_id'` 提取。

### 第 2 步：轮询任务进度

```
tdocs-cli manage scrape-progress --task-id <task-id>
```

| 参数 | 必填 | 说明 |
|---|---|---|
| `--task-id` | ✅ | 第 1 步返回的 `task_id` |

每 3–5 秒轮询一次，直到任务终态（成功时返回字段含生成的文档 `file_id`，失败时含错误信息）。

> **取链接时机**：异步任务（`query-task` / `scrape-progress` 等）在 `progress < 100`（未到终态）时，返回的 `url` 可能是 `"https:"` 这样的半成品链接。**必须轮询到终态（progress=100 / 成功状态）再取 `url` / `file_id`**，不要在中途就提取链接。

### 端到端示例

```bash
# 1. 提交并提取 task_id
tid=$(tdocs-cli manage scrape-url --url "https://example.com/article" --jq '.task_id')

# 2. 轮询进度（示例：循环至完成，建议在外层脚本/Agent 中按 3–5s 间隔轮询）
tdocs-cli manage scrape-progress --task-id "$tid"
```

**注意事项**：
- 网页剪藏统一用 `manage scrape-url` + `manage scrape-progress` 组合（**推荐**）。`workflow scrape-url` 目前仍存在，但请优先用 `manage` 下的两步命令。
- 仅传 `--url`，旧版本可能存在的 `--title` / `--parent-id` 等参数已不再支持，以 `--help` 输出为准。

---

## 常见后续操作

- `import-file` 完成后：从固定 JSON 输出读取 `file_id`（该命令不响应 `--jq` / `--format`）。DOC 可复用该 ID 继续编辑；Sheet 仅按 `cmd-sheet.md` 做有限小改，复杂 Sheet / PPT 按上文生成新版本资源；smartsheet 含导入能力均禁用。
- `export-file` 完成后：用 `--jq '.local_path'` 获取导出文件路径。
- `scrape-progress` 终态后：用 `--jq '.file_id'` 拿到剪藏文档 ID。

## 权威来源

```
tdocs-cli workflow --help
tdocs-cli manage scrape-url --help
tdocs-cli manage scrape-progress --help
```
