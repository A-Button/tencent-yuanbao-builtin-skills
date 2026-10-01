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

| 参数 | 必填 | 说明 |
|---|---|---|
| `--file` | ✅ | 本地文件路径，文件名默认作为文档标题 |
| `--poll-interval-secs` |  | 轮询间隔，默认 3 |
| `--poll-timeout-secs`  |  | 轮询超时，默认 600，大文件需调高 |

```
tdocs-cli workflow import-file --file ./report.xlsx
```

---

## workflow export-file

将腾讯文档导出下载到本地。

| 参数 | 必填 | 说明 |
|---|---|---|
| `--file-id` | ✅ | 云端文档 ID |
| `--dir`     | ✅ | 导出文件写入的本地目录，不存在时自动创建 |
| `--poll-interval-secs` |  | 轮询间隔，默认 3 |
| `--poll-timeout-secs`  |  | 轮询超时，默认 600 |

```
tdocs-cli workflow export-file --file-id <file-id> --dir ./downloads
```

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

### 端到端示例

```bash
# 1. 提交并提取 task_id
tid=$(tdocs-cli manage scrape-url --url "https://example.com/article" --jq '.task_id')

# 2. 轮询进度（示例：循环至完成，建议在外层脚本/Agent 中按 3–5s 间隔轮询）
tdocs-cli manage scrape-progress --task-id "$tid"
```

**注意事项**：
- `scrape-url` 不再属于 `workflow` 子命令组，已迁移至 `manage` 下。
- 老版本 `workflow scrape-url` 已废弃，请改用 `manage scrape-url` + `manage scrape-progress` 组合。
- 仅传 `--url`，旧版本可能存在的 `--title` / `--parent-id` 等参数已不再支持，以 `--help` 输出为准。

---

## 常见后续操作

- `import-file` 完成后：用 `--jq '.file_id'` 提取文件 ID，可继续在 smartcanvas / doc 中编辑（注意：`sheet` / `slide` 子命令组已对本 skill 关闭，**表格类与 PPT 类文件导入后由用户在前端继续操作**，Agent 不再调用对应子命令；`smartsheet` 多维表格**含导入能力一并下线**，禁止向多维表格类型导入文件）。
- `export-file` 完成后：用 `--jq '.local_path'` 获取导出文件路径。
- `scrape-progress` 终态后：用 `--jq '.file_id'` 拿到剪藏文档 ID。

## 权威来源

```
tdocs-cli workflow --help
tdocs-cli manage scrape-url --help
tdocs-cli manage scrape-progress --help
```
