# 输出与安全诊断

格式选择、jq 过滤、空运行以及超时调优。

## 输出格式

通过 `--format` 设置；当命令的业务参数需要同名兼容时，可改用无歧义的 `--output-format`：

| 值 | 适用场景 |
|---|---|
| `json`  | 大多数命令的默认值。最适合用管道传给 `jq`、脚本或下游工具。 |
| `table` | 人类可读的表格渲染。最适合交互式查看。 |
| `plain` | 最精简的文本输出（每行一个值）。最适合变量替换。 |

示例：

```
tdocs-cli manage list-file --list-type 1 --format table
```

每个命令的默认值由服务端工具描述符声明；`--format` 可覆盖之。

## 使用 --jq 进行 JSON 过滤

在打印前对 JSON 输出应用 jq 表达式。常见用法：

```
tdocs-cli manage list-file --list-type 1 --jq '.files[0].file_id'
tdocs-cli manage list-file --list-type 1 --jq '.files[].name'
tdocs-cli manage list-file --list-type 1 --jq '.files[] | select(.ext == "smartcanvas")'
tdocs-cli manage list-file --list-type 1 --jq '.files[] | {file_id, name, ext}'
```

> `list-file` 返回是对象 `{files:[...], finish, user_space}`，文档在 `.files` 数组里；单个元素字段为 `file_id` / `name` / `ext` / `doc_type` / `doc_url` 等（**不是** `id` / `title` / `type`）。所以 jq 要从 `.files[]` 起步。

`--jq` 建立在 `--format json` 之上。将 `--jq` 与 `--format table` 一起使用没有意义；二选一即可。

## 空运行（Dry Run）

打印解析后的调用信息（命令、服务、调用路径与参数）但不发送。用于在实际变更状态前确认参数解析和映射是否正确；它不等同于完整 HTTP 请求取证。

```
tdocs-cli manage create-file --type 8 --title demo --dry-run
```

> ⚠️ **`--dry-run` 只对单发 API 命令（`manage` / `doc` / `smartcanvas` / `ocr` 等）保证无副作用。** `workflow` 子命令（`import-file` / `export-file` 等）是多步异步编排，`--dry-run` **不拦截**，仍会真实执行并产生在线文档 / 任务（实测 `workflow import-file --dry-run` 会真实建出一份在线副本）。**禁止用 `--dry-run` 诊断任何 `workflow` 命令**；诊断 workflow 参数请改用 `--help` 核对签名。

## 禁止使用 `--debug`

当前 skill 仍禁止 Agent 使用、保存或转发 `--debug` 输出，避免在诊断材料中带出业务 URL 或请求元数据。参数检查使用单发 API 命令的 `--dry-run`；普通错误会附带可安全展示的 `trace_id` 与 `original_code`（服务端提供时），报告问题时优先引用这两个标识。

## 超时

`--timeout` 控制 HTTP 超时时间，单位为秒（默认 30）：

```
tdocs-cli --timeout 120 manage list-file --list-type 1
```

Workflow 命令有额外的轮询超时（独立于 `--timeout`）：

- `--poll-interval-secs` — 轮询间隔。
- `--poll-timeout-secs`  — 总轮询截止时间（`import-file` / `export-file` 默认 600）。

导入/导出大文件时，需同时提高 `--timeout` 和 `--poll-timeout-secs`。

## 安全诊断方案

单发 API 命令可用 `--dry-run` 检查参数组装：

```
tdocs-cli manage create-file --type 8 --title demo --dry-run
```

查看真实响应结构时使用普通输出或 `--jq '.'`，不要打开 debug：

```
tdocs-cli manage list-file --list-type 1 --jq '.'
```

`workflow` 命令禁用 `--dry-run` 诊断，参数只用 `--help` 核对。

## 输出格式与退出码

- 非零退出码表示请求失败（网络、服务端错误或校验失败）。标准错误输出人类可读的诊断信息；标准输出承载 JSON/table/plain 数据（可能为空）。
- `--dry-run` 总是返回退出码 0，除非本地校验在序列化前就拒绝了请求。
- 错误时可配合 `--format json --jq '.error // empty'` 提取服务端报告的错误信息。
- 命令失败时先诊断，不要 `sleep` 后重发同一条命令；`429` / `400007` 等 `troubleshooting.md` 明确认定的速率限制除外，可退避重试（运行时帮助查参数；单发 API 命令可用 `--dry-run` 核对请求，但 `workflow` 命令**禁用** `--dry-run` 诊断）。
