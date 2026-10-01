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
tdocs-cli manage list-file --format table
```

每个命令的默认值由服务端工具描述符声明；`--format` 可覆盖之。

## 使用 --jq 进行 JSON 过滤

在打印前对 JSON 输出应用 jq 表达式。常见用法：

```
tdocs-cli manage create-file --file-type smartcanvas --title demo --jq '.url'
tdocs-cli manage list-file --jq '.[].title'
tdocs-cli manage list-file --jq '.[] | select(.type == "smartcanvas")'
tdocs-cli manage list-file --jq '.[] | {id, title, type}'
```

`--jq` 建立在 `--format json` 之上。将 `--jq` 与 `--format table` 一起使用没有意义；二选一即可。

## 空运行（Dry Run）

打印解析后的请求（URL、方法、请求头、请求体）但不发送。用于在实际变更状态前确认参数解析和映射是否正确。

```
tdocs-cli manage create-file --file-type smartcanvas --title demo --dry-run
```

对于 workflow 命令，`--dry-run` 会打印计划的步骤序列和参数，但不运行 `.star` 脚本。

## Verbose 与 Debug 日志

两个日志级别，逐级递增：

```
tdocs-cli --verbose manage create-file --file-type smartcanvas --title demo
tdocs-cli --debug manage create-file --file-type smartcanvas --title demo
```

- `--verbose`：INFO 级别 — 高层调用事件。
- `--debug`：DEBUG 级别 — 包含 INFO 以及完整的请求和响应详情（URL、请求头、请求体、状态码）。可用时包含 trace ID。

报告问题时使用 `--debug`：捕获完整输出并在 bug 报告中引用 trace ID（不要包含 token）。

## 超时

`--timeout` 控制 HTTP 超时时间，单位为秒（默认 30）：

```
tdocs-cli --timeout 120 manage list-file
```

Workflow 命令有额外的轮询超时（独立于 `--timeout`）：

- `--poll-interval-secs` — 轮询间隔。
- `--poll-timeout-secs`  — 总轮询截止时间（`import-file` / `export-file` 默认 600）。

导入/导出大文件时，需同时提高 `--timeout` 和 `--poll-timeout-secs`。

## 常用调试方案

组合使用四个标志来排查行为异常的命令：

```
tdocs-cli --debug --dry-run \
    manage create-file --file-type smartcanvas --title demo
```

此命令同时打印完整 DEBUG 日志和解析后的请求但不发送——非常适合检查参数组装。确认请求无误后去掉 `--dry-run`。

查看真实响应时，将 `--dry-run` 替换为 `--jq '.'` 以确认 JSON 结构，再编写后续管道：

```
tdocs-cli --debug manage list-file --jq '.'
```

## 输出格式与退出码

- 非零退出码表示请求失败（网络、服务端错误或校验失败）。标准错误输出人类可读的诊断信息；标准输出承载 JSON/table/plain 数据（可能为空）。
- `--dry-run` 总是返回退出码 0，除非本地校验在序列化前就拒绝了请求。
- 错误时可配合 `--format json --jq '.error // empty'` 提取服务端报告的错误信息。
