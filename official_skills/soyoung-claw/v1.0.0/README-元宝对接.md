# 新氧连锁 MCP 服务接入说明（元宝研发版）

本文档面向元宝智能体平台研发对接使用。接入方需要按标准 MCP Streamable HTTP 服务注册和调用。

## 1. 对接信息

| 项目         | 内容                            |
| ------------ | ------------------------------- |
| 服务名称     | `soyoung-claw-mcp`              |
| MCP Endpoint | `https://skill.soyoung.com/mcp` |
| Transport    | MCP Streamable HTTP             |
| Tool 发现    | 标准 MCP `tools/list`           |

接入方通过 `tools/list` 获取 Tool Schema，通过 `tools/call` 调用业务能力；不需要直接调用新氧后端 HTTP 接口。

## 2. 认证约定

项目查询类 Tool 不需要认证：

- `search_clinic_solutions`
- `search_clinic_products`
- `search_clinic_doctors`

门店和预约类 Tool 需要在 MCP HTTP 请求中携带用户 Bearer token：

```http
Authorization: Bearer <claw-token>
```

需要认证的 Tool：

- `search_stores`
- `query_booking_slots`
- `query_bookings`
- `submit_booking`
- `modify_booking`
- `cancel_booking`

注意事项：

- Tool 参数里不要传 `api_key`、`uid`、`tenant_id`。
- 不要让模型或最终用户在对话中输入 token。
- 不要把生产 token 写入仓库、示例文件、Prompt 或日志。

## 3. Tool 清单

| Tool                      | 认证   | 类型 | 用途                                   |
| ------------------------- | ------ | ---- | -------------------------------------- |
| `search_clinic_solutions` | 无     | 查询 | 查询医美品项、原理、适合人群、治疗信息 |
| `search_clinic_products`  | 无     | 查询 | 按城市查询商品、价格、适用门店         |
| `search_clinic_doctors`   | 无     | 查询 | 按城市查询医生、资质、门店和排班       |
| `search_stores`           | Bearer | 查询 | 按城市查询可预约门店                   |
| `query_booking_slots`     | Bearer | 查询 | 查询指定门店日期的可预约时间           |
| `query_bookings`          | Bearer | 查询 | 查询当前认证用户预约                   |
| `submit_booking`          | Bearer | 写入 | 创建预约，必须用户明确确认             |
| `modify_booking`          | Bearer | 写入 | 修改预约，必须用户明确确认             |
| `cancel_booking`          | Bearer | 写入 | 取消预约，必须用户明确确认             |

完整参数 Schema 以运行时 `tools/list` 返回为准，也可以参考包内 `examples/tools-list.json`。每个 Tool 的请求和返回示例见 `examples/tool-call-examples.json`。

## 4. 关键参数约定

- `content`：实体关键词，例如 `肉毒`、`玻尿酸`、`保利店`，不要传整段用户问题。
- `city_name`：城市名称，例如 `北京`。
- `date`：日期，格式 `YYYY-MM-DD`。
- `start_time` / `end_time`：时间，格式 `YYYY-MM-DD HH:MM:SS`。
- `hospital_id`：必须使用 `search_stores` 或商品查询结果返回的真实机构 ID。
- `booking_id`：必须使用 `query_bookings` 返回的真实预约 ID。
- `confirmed`：只有在用户明确确认具体门店、预约 ID、日期和时间后才传 `true`。

## 5. 返回和错误处理

`tools/list` 主要描述 Tool 入参；Tool 返回结构请以本节说明以及 `examples/tool-call-examples.json` 为准。

MCP `tools/call` 的 HTTP 响应外层是 JSON-RPC，业务结果在 `result.structuredContent` 中。`result.content` 是给模型读取的文本内容，通常会包含同一份业务结果的 JSON 字符串；程序侧建议优先读取 `result.structuredContent`。

实际 MCP 响应结构示例：

```json
{
  "jsonrpc": "2.0",
  "id": 3,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{...}"
      }
    ],
    "structuredContent": {
      "ok": true,
      "request_id": "generated-by-adapter",
      "total": 1,
      "products": [],
      "message": null
    },
    "isError": false
  }
}
```

`examples/tool-call-examples.json` 中的 `response` 表示 `result.structuredContent` 里的业务结果。

Tool 返回结果里会包含结构化字段：

```json
{
  "ok": true,
  "request_id": "generated-by-adapter",
  "total": 1,
  "products": [],
  "message": null
}
```

错误结果示例：

```json
{
  "ok": false,
  "request_id": "generated-by-adapter",
  "error": {
    "code": "AUTH_REQUIRED",
    "message": "该 Tool 需要用户认证，请通过 Authorization Bearer token 调用服务。",
    "retryable": false
  }
}
```

接入方不要只根据 HTTP 200 判断业务成功，应检查 Tool 结果中的 `ok` 字段。查询无结果通常是 `ok: true` 且 `total: 0`，不是系统异常。

## 6. 写操作安全要求

预约创建、修改、取消属于写操作。元宝智能体调用写 Tool 前必须向用户复述关键信息，并获得明确确认。

写操作不要自动重试。遇到超时或不确定状态时，应先调用 `query_bookings` 查询当前预约状态，再决定下一步。

## 7. 联调验收

建议按以下用例验收：

1. 不带 Bearer token，可以完成 MCP 连接和 `tools/list`。
2. `tools/list` 返回 9 个 Tool。
3. 不带 Bearer token 调用 `search_clinic_products`，参数 `content=肉毒`、`city_name=北京`，能返回结构化结果。
4. 不带 Bearer token 调用 `search_stores`，应返回结构化 `AUTH_REQUIRED` 错误。
5. 带有效 Bearer token 调用 `search_stores`，能查询城市门店。
6. 写 Tool 在 `confirmed=false` 时不能产生预约写入。
7. 测试环境中完成一次用户明确确认后的预约创建、修改或取消，并能根据 `request_id` 追踪。

## 8. 附件说明

本接入包包含：

| 文件                         | 用途                                     |
| ---------------------------- | ---------------------------------------- |
| `README-元宝对接.md`         | 给元宝研发阅读的精简接入说明             |
| `examples/tools-list.json`   | Tool Schema 示例                         |
| `examples/tool-call-examples.json` | 每个 Tool 的 `tools/call` 请求和返回示例 |
