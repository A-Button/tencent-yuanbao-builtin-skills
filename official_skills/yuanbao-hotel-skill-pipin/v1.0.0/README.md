# RollingGo 酒店预订 — MCP Server + 外层 Skill 交付包

本交付包遵循平台“MCP Server + 外层 Skill”接入规范，提供全球与国内酒店的搜索、比价、锁价、生单与售后取消全流程能力。

## 1. 交付清单

- **根目录 `SKILL.md`**：定义触发条件、意图提取、追问机制、MCP Tools 编排流水线、原生 `<media_info>` 图文卡片规范、微信小程序直跳及高危取消安全门控。
- **服务契约 `service-contract.json`**：声明 MCP Server 地址、传输协议（`streamable_http`）、网关鉴权机制（OAuth 2.1 / Platform Secret Injection）及调用超时配置。
- **示例目录 `examples/`**：
  - `tools-list.json`：包含底层 MCP Tools 的完整 Schema 定义（对应 `tools/list`）。
  - `search-result.json`：真实的酒店搜索与小程序直跳返回示例报文（对应 `tools/call`）。

## 2. MCP Server 服务信息

- **版本**：v2.7
- **服务端点**：`https://mcp.rollinggo.cn/mcp/hotel`
- **协议传输**：`streamable_http` (SSE / JSON-RPC 2.0)
- **鉴权方式**：平台网关自动注入 Bearer Token，无需用户手动输入凭证。

## 3. MCP Tools 清单

1. `getHotelSearchTags`：获取系统启用的设施、品牌及特色筛选标签字典
2. `searchHotels`：酒店列表全网初筛与首夜参考价展示
3. `getHotelDetail`：查单店实时房型列表、餐食与取消政策
4. `hotelPriceConfirm`：【强制锁价门控】锁定 30 分钟实时总价并获取 `referenceNo`
5. `createHotelBookingWithPaymentURL`：【强制生单门控】提交正式订单并获取收银台支付链接 `paymentUrl`
6. `searchHotelOrders`：检索当前用户订单列表
7. `getHotelOrderDetail`：查询单笔订单履约详情与状态
8. `preCancelHotelBooking`：【高危预取消门控】预取消试算与 10 分钟凭证 `confirmId` 发放
9. `confirmCancelHotelBooking`：【不可逆取消门控】经用户明确确认后提交取消
