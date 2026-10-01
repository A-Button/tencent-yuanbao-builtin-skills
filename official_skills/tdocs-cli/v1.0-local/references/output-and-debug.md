# 输出与调试

格式选择、jq 过滤、空运行、verbose / debug 日志级别以及超时调优。

## 输出格式

通过 `--format` 设置：

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

打印解析后的请求（URL、方法、请求头、请求体）但不发送。用于在实际变更状态前确认参数解析和映射是否正确。

```
tdocs-cli manage create-file --type 8 --title demo --dry-run
```

> ⚠️ **`--dry-run` 只对单发 API 命令（`manage` / `doc` / `smartcanvas` / `ocr` 等）保证无副作用。** `workflow` 子命令（`import-file` / `export-file` 等）是多步异步编排，`--dry-run` **不拦截**，仍会真实执行并产生在线文档 / 任务（实测 `workflow import-file --dry-run` 会真实建出一份在线副本）。**禁止用 `--dry-run` 诊断任何 `workflow` 命令**；诊断 workflow 参数请改用 `--help` 核对签名。

## Debug 日志

用 `--debug` 打开调试日志（当前 CLI 仅提供 `--debug` 一个级别，**无 `--verbose`**）：

```
tdocs-cli --debug manage list-file --list-type 1
```

- `--debug`：DEBUG 级别 — 完整的请求和响应详情（URL、请求头、请求体、状态码）。可用时包含 trace ID。

报告问题时使用 `--debug`：捕获完整输出并在 bug 报告中引用 trace ID（不要包含 token）。

## 超时

`--timeout` 控制 HTTP 超时时间，单位为秒（默认 30）：

```
tdocs-cli --timeout 120 manage list-file --list-type 1
```

Workflow 命令有额外的轮询超时（独立于 `--timeout`）：

- `--poll-interval-secs` — 轮询间隔。
- `--poll-timeout-secs`  — 总轮询截止时间（`import-file` / `export-file` 默认 600）。

导入/导出大文件时，需同时提高 `--timeout` 和 `--poll-timeout-secs`。

## 常用调试方案

组合使用四个标志来排查行为异常的命令：

```
tdocs-cli --debug --dry-run \
    manage create-file --type 8 --title demo
```

此命令同时打印完整 DEBUG 日志和解析后的请求但不发送——非常适合检查参数组装。确认请求无误后去掉 `--dry-run`。（注意：`--dry-run` 仅对单发 API 命令保证无副作用，`workflow` 命令请勿用 `--dry-run` 诊断，详见上文。）

查看真实响应时，将 `--dry-run` 替换为 `--jq '.'` 以确认 JSON 结构，再编写后续管道：

```
tdocs-cli --debug manage list-file --list-type 1 --jq '.'
```

## 输出格式与退出码

- 非零退出码表示请求失败（网络、服务端错误或校验失败）。标准错误输出人类可读的诊断信息；标准输出承载 JSON/table/plain 数据（可能为空）。
- `--dry-run` 总是返回退出码 0，除非本地校验在序列化前就拒绝了请求。
- 错误时可配合 `--format json --jq '.error // empty'` 提取服务端报告的错误信息。
- 命令失败时先诊断，不要 `sleep` 后重发同一条命令；明确的 `429` 速率限制除外，可等待后重试（`--help` 查参数；单发 API 命令可用 `--dry-run` 核对请求，但 `workflow` 命令**禁用** `--dry-run` 诊断）；
