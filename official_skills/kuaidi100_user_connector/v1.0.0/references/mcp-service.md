# 快递100 MCP服务说明

## 接入方式

- 交付形态：MCP-backed Skill。
- 传输协议：Streamable HTTP，当前采用单次`POST`返回`application/json`的无状态模式。
- MCP路径：`/aiservice/connector/mcp`。完整测试与正式URL由部署方在元宝连接配置中提供，Skill不得自行拼接或覆盖服务地址。
- MCP协议版本：服务端当前支持`2025-06-18`和`2025-03-26`，以`initialize`协商结果为准。
- 必备能力：`initialize`、`notifications/initialized`、`ping`、`tools/list`、`tools/call`。

生产接入必须使用HTTPS。现有HTTP地址只能用于受控测试环境，不得作为正式元宝连接地址。

## 鉴权

元宝通过OAuth保存当前用户的访问令牌，并在每次MCP HTTP请求中注入：

```http
Authorization: Bearer <access_token>
```

Token不得放在URL、Tool参数、Skill正文、日志或对话中。MCP服务解析Token得到当前快递100用户，Agent不得提供或覆盖`userId`、`openId`。

## 请求与响应

请求使用JSON-RPC 2.0：

```http
POST /aiservice/connector/mcp
Content-Type: application/json
Accept: application/json, text/event-stream
Authorization: Bearer <access_token>
```

Tool成功或业务失败均使用MCP Tool Result包络。业务失败通过`isError=true`表达；协议错误通过JSON-RPC`error`表达。

`prepare_shipment_order`成功时，`structuredContent`顶层包含 `url` 和 `qrCode`，`content`中的文本块是同一对象的JSON序列化。该响应不包含MCP `image`内容块，也不直接传输PNG字节；图片由宿主加载 `qrCode` 地址后显示。解析及展示规则见[链接与二维码](link-and-qrcode.md)。

## 错误语义

| 场景 | 表现 | Agent处理 |
| --- | --- | --- |
| Token缺失、无效或过期 | HTTP 401 | 提示重新连接或授权，不自行索取Token |
| Origin不允许 | HTTP 403 | 检查元宝调用来源和服务端允许列表 |
| 协议或请求参数错误 | HTTP 400或Tool `isError=true` | 修正参数后由用户继续 |
| 目标数据不存在 | Tool `isError=true` | 如实说明无数据 |
| 限流 | HTTP 429或Tool失败 | 提示稍后重试，不循环调用 |
| 服务异常 | HTTP 5xx或Tool失败 | 说明服务暂不可用 |
| 超时、断网、结果未知 | 客户端超时 | 只读操作按平台策略处理；预下单及所有地址簿写操作不得自动重试 |

## 超时、限流与可用性

- 元宝连接超时与调用超时由双方在环境配置和联调阶段确认，不在Agent Skill中硬编码。
- 当前服务未在Skill层声明固定限流额度；正式上线前由服务方提供应用、用户或接口维度的限流规则。
- 当前MCP只校验Token对应用户，尚未实现按OAuth scope限制不同Tool；正式OAuth接入前需由服务方补齐或明确由上游授权服务统一限制。
- 只读Tool是否重试由元宝平台策略决定；`prepare_shipment_order`以及地址新增、修改、删除、设置默认地址都是写操作，结果未知时禁止自动重试。
- Tool名称和Schema以运行时`tools/list`为权威来源；破坏性变更需要新版本或兼容迁移期。

## 第三方与元宝责任边界

快递100负责MCP Server、Tool Schema、业务返回、鉴权校验、错误语义和服务稳定性。元宝负责连接配置、OAuth凭据安全管理、`additional_tools.json`、必要的`assets/app.yaml`和UI渲染资源。
