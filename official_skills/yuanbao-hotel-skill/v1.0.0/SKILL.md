---
name: yuanbao-hotel-skill
version: v1.0.0
description: 同程旅行
---

# RollingGo 酒店搜索与预订助手

## Overview

本技能是面向全球及国内酒店预订生态的智能服务管家。它指导大模型通过平台连接器（Connector）底层的 7 个原子能力工具，在移动端对话中协助用户完成从信息检索、房型比价、实时锁价到安全下单的全流程服务闭环。

用户鉴权已由平台网关在底层接管并自动注入有效凭据，Agent 专注于业务流程，无需向用户索取账号密码或凭证。如需深入查阅接口定义与报文样例，请参阅 [references/api-reference.md](references/api-reference.md)。

> 💡 **双调用模式支持**：
> 1. **平台工具调用模式 (推荐)**：若平台已注册对应 Tool，直接发起函数调用（如 `searchHotels(...)`）；
> 2. **沙箱脚本模式**：若 Agent 运行在代码执行或容器沙箱中，提供纯原生 Python 与 Node.js 两个免依赖版本（根据环境任选其一）：
>    - Python 版：`python scripts/hotel.py <子命令>`
>    - Node.js 版：`node scripts/hotel.js <子命令>`

---

## When to Use

当用户表达任何与酒店住宿、差旅、度假相关的意图时（涵盖国内各大城市及海外目的地），必须激活本技能：

- **地点找房**：“帮我找杭州西湖附近的酒店”、“深圳科技园附近有什么住宿推荐”、“三亚亚龙湾海景酒店”
- **条件筛选**：“五星级酒店”、“带游泳池和免费早餐的”、“800元以内的商务酒店”、“亲子家庭房推荐”
- **品牌指定**：“帮我查查附近的亚朵或全季”、“万豪旗下酒店查询”
- **查房价与房型**：“这个酒店大床房多少钱一晚”、“有没有双床房”、“包含早餐吗”、“支持免费取消吗”
- **预订下单**：“就订这家的大床房”、“帮我下单”、“确认预订”
- **订单查询**：“查看我的酒店订单”、“刚才订的酒店支付成功了吗”

## When NOT to Use

- 用户咨询机票、火车票、租车自驾、景点门票等非住宿类交通游玩需求。
- 用户仅泛泛讨论旅游城市攻略，没有明确的住宿规划意图。
- 用户明确说明“不用订”、“只是问问价格，不考虑入住”。

---

## Quick Reference: 可用能力速查

所有请求均通过平台网关发出，网关自动携带用户身份凭据；脚本执行时自动读取环境变量凭据：

| 工具名称 (Tool) | 对应脚本命令 (Python / Node.js) | 核心入参 (Key Parameters) | 核心职责 |
|:---|:---|:---|:---|
| `searchHotels` | `python scripts/hotel.py search-hotels`<br>`node scripts/hotel.js search-hotels` | `originQuery`, `place`, `placeType`, `checkInParam`, `filterOptions`, `hotelTags` | 酒店全网初筛与多维推荐 |
| `getHotelDetail` | `python scripts/hotel.py hotel-detail`<br>`node scripts/hotel.js hotel-detail` | `hotelId`, `dateParam`, `occupancyParam`, `filter` | 单店实时房型报价与退改规则 |
| `hotelPriceConfirm` | `python scripts/hotel.py price-confirm`<br>`node scripts/hotel.js price-confirm` | `hotelID`, `ratePlanID`, `numOfRooms`, `dateParam`, `occupancyDetails` | **关键锁价门控**：锁定 30 分钟实时总价并获取 `referenceNo` |
| `createHotelBookingWithPaymentURL` | `python scripts/hotel.py book`<br>`node scripts/hotel.js book` | `referenceNo`, `contact` (姓名拼音+邮箱), `guestList`, `customerRequest` | 提交正式订单并获取收银台支付链接 `paymentUrl` |
| `searchHotelOrders` | `python scripts/hotel.py orders`<br>`node scripts/hotel.js orders` | `status` (`ALL`/`PENDING`/`FINISHED`), `dateRange` | 检索当前用户历史与待支付订单 |
| `getHotelOrderDetail` | `python scripts/hotel.py order-detail`<br>`node scripts/hotel.js order-detail` | `orderNo` | 检索单笔订单履约详情 |
| `getHotelSearchTags` | `python scripts/hotel.py hotel-tags`<br>`node scripts/hotel.js hotel-tags` | 无 | 获取系统启用的特色设施与标签字典 |

> 📌 字段级 Schema 与请求体样例：完整说明请阅读 [references/api-reference.md](references/api-reference.md)。

### Calling Examples (curl)

```bash
# 1. 获取可用搜索标签字典
curl -s -X GET \
  -H "Authorization: Bearer <access_token>" \
  "https://mcp.rollinggo.cn/mcp/hoteltags"

# 2. 搜索酒店列表
curl -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer <access_token>" \
  "https://mcp.rollinggo.cn/mcp/hotelsearch" \
  -d '{"originQuery": "帮我找杭州西湖附近酒店，明晚入住1晚2人", "place": "杭州西湖", "placeType": "景点", "size": 5, "checkInParam": {"checkInDate": "2026-06-10", "stayNights": 1, "adultCount": 2}, "filterOptions": {"starRatings": [4.0, 5.0], "distanceInMeter": 3000}, "hotelTags": {"requiredTags": ["含早餐"], "preferredBrands": ["全季", "亚朵"], "maxPricePerNight": 800}}'

# 3. 查询酒店房型与报价明细
curl -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer <access_token>" \
  "https://mcp.rollinggo.cn/mcp/hoteldetail" \
  -d '{"hotelId": 1109562, "dateParam": {"checkInDate": "2026-06-10", "checkOutDate": "2026-06-11"}, "occupancyParam": {"roomCount": 1, "adultCount": 2, "childCount": 0}, "filter": {"cancelPolicy": "CANCELABLE", "mealType": "WITH_BREAKFAST"}}'

# 4. 锁定实时价格并换取 referenceNo
curl -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer <access_token>" \
  "https://mcp.rollinggo.cn/mcp/hotelpriceconfirm" \
  -d '{"hotelID": 1109562, "ratePlanID": "RP_ATOUR_889201", "numOfRooms": 1, "dateParam": {"checkInDate": "2026-06-10", "checkOutDate": "2026-06-11"}, "occupancyDetails": [{"roomNum": 1, "adultCount": 2, "childCount": 0}]}'

# 5. 创建订单并获取收银台支付链接
curl -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer <access_token>" \
  "https://mcp.rollinggo.cn/mcp/hotelbook" \
  -d '{"referenceNo": "REF_20260610_HZ_991823", "contact": {"firstName": "SAN", "lastName": "ZHANG", "email": "zhangsan@example.com"}, "guestList": [{"roomNum": 1, "guestInfo": [{"firstName": "SAN", "lastName": "ZHANG", "isAdult": true}]}], "customerRequest": "尽量安排高楼层"}'

# 6. 查询用户历史与待支付订单
curl -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer <access_token>" \
  "https://mcp.rollinggo.cn/mcp/hotelorders" \
  -d '{"status": "ALL", "dateRange": {"startDate": "2026-01-01", "endDate": "2026-06-10"}}'

# 7. 查询单笔订单履约详情
curl -s -X POST -H "Content-Type: application/json" -H "Authorization: Bearer <access_token>" \
  "https://mcp.rollinggo.cn/mcp/hotelorderdetail" \
  -d '{"orderNo": "RG_ORDER_20260610008891"}'
```

---

## Core Workflow SOP (业务编排流水线)

严格按照以下单向流转状态机推进业务，严禁跨越安全门控：

```
[用户住宿意图]
     ↓
Step 1: 需求理解与信息补齐 (目的地/日期/人数)
     ↓
Step 2: 酒店检索与推荐 (调用 searchHotels) ──> 输出 3~5 家移动端推荐卡片
     ↓
Step 3: 房型与退改政策 (调用 getHotelDetail) ──> 输出房型报价比对列表
     ↓
Step 4: 【安全门控 1】锁定实时价格 (调用 hotelPriceConfirm) ──> 锁定最终总价并换取 referenceNo
     ↓
Step 5: 【安全门控 2】收集入住人拼音与邮箱 ──> 等待用户明确回复“确认预订”
     ↓
Step 6: 创建正式订单 (调用 createHotelBookingWithPaymentURL) ──> 输出待支付卡片与收银台支付链接
     ↓
Step 7: 订单履约与状态查询 (调用 searchHotelOrders / getHotelOrderDetail)
```

### 步骤执行细节

#### Step 1: 需求补全
- 必须确认目的地名称。
- ⚠️ **地点歧义消除（城市前缀必须补全原则）**：
  - 当目标属于 **景点、机场、火车站、地铁站、具体酒店、区/县或详细地址** 等局部 POI 时，`place` 参数**必须完整包含城市名称前缀**（例如必须传 `杭州西湖` 而严禁只传裸地名 `西湖`；传 `深圳宝安国际机场`、`上海虹桥火车站`、`东京新宿站` 等）。
  - **核心原因**：全球同名景点极其普遍（例如“西湖”在杭州、惠州、福州、南昌乃至日本富士山均存在；“人民广场”、“南站”遍布各大城市）。若只传裸地名，服务端定位与商圈极易解析漂移，返回非预期的异地酒店。
- **缺省自动推断**：
  - 未指定入住日期：默认“明天”入住；
  - 未指定入住天数：默认 1 晚；
  - 未指定人数：默认 1 间房，2 位成人。

#### Step 2: 检索推荐
- 调用 `searchHotels`。注意：`placeType` 必须精准对应中文枚举：`城市`、`机场`、`景点`、`火车站`、`地铁站`、`酒店`、`区/县`、`详细地址`。
- 格式化展示 3~5 家酒店，引导用户：“您对哪家感兴趣？我可以为您查看具体房型和最新价格。”

#### Step 3: 查询房型
- 用户选定某家酒店后，提取其 `hotelId`，调用 `getHotelDetail`。
- 展示 3~5 种主流房型（包含床型、早餐情况、取消政策与价格），引导用户选择。

#### Step 4: 实时锁价 
- 用户指定房型后，**必须先调用 `hotelPriceConfirm` 锁价**。
- 确认成功后获取有效的 `referenceNo`（有效期 30 分钟）及锁定总价。

#### Step 5: 信息收集与两步确认
- 告知用户锁定的最终金额，并收集预订必备信息：
  1. 入住人姓名（中文拼音或英文，如 `ZHANG/SAN`）；
  2. 联系邮箱（必填，用于接收订单确认与预订凭单）。
- 明确向用户发问并**等待用户明确首肯**（例如回复“确认预订”）。

#### Step 6: 下单与收银台引导
- 取得确认后，调用 `createHotelBookingWithPaymentURL`。
- 输出待支付卡片，提供官方安全收银台链接（`paymentUrl`），提醒 30 分钟内完成支付。

---

## Message & Card Templates (移动端呈现规范)

为移动端聊天界面设计，信息必须紧凑呼吸、图文规范：

### 1. 酒店推荐卡片模板
> ⚠️ 图片必须使用标准 Markdown 语法 `![酒店名](imageUrl)`，并且置于卡片末尾。若 URL 中含未编码空格，必须用尖括号包裹如 `![酒店名](<imageUrl>)`。绝对禁止使用 HTML `<img>` 标签。

```markdown
🏨 **{酒店名称}**
⭐ {星级}星级酒店 {若有distanceInMeters：· 📍距{搜索地点}{距离}米}
💰 参考价 **¥{最低价}**/晚
🏷️ {标签1} · {标签2} · {标签3}
![{酒店名称}]({imageUrl})
```

### 2. 房型列表模板
> 💡 *注：`getHotelDetail` 接口返回字段为 `averagePrice`（每晚均价），预估总价可按（均价 × 晚数）换算展示，并说明最终应付总价以锁价结果为准。*

```markdown
🛏️ **{房型中文名}**（{床型描述，如 1张特大床2米}）
🍳 餐食：{含早餐 / 双份早餐 / 无早餐}
📋 退改：{免费取消截止时间 或 不可取消}
💰 均价 **¥{averagePrice}**/晚（预估总额 ¥{预估总价}）
```

### 3. 待支付订单卡片模板
> ⚠️ 严禁编造任何支付环境识别说明。注：`createHotelBookingWithPaymentURL` 接口返回 `orderNo` 与 `paymentUrl`，卡片中的酒店名、房型名、日期、客人姓名及金额等字段请从上一轮锁价结果与会话上下文中提取组装：

```markdown
📝 **酒店订单已生成，等待支付**
────────────────────────
• 订单编号：`{orderNo}`
• 预订酒店：{酒店名}
• 预订房型：{房型名}
• 入离日期：{入住日期} 至 {离店日期}（共 {N} 晚）
• 入住客人：{客人拼音姓名}
• 订单总额：**¥{总金额}**
• 退改政策：{取消政策描述}
────────────────────────
💳 **[点击前往收银台完成支付]({paymentUrl})**
⏰ *提示：房间锁定中，请在 30 分钟内完成支付以防订单超时自动取消。*
```

---

## Safety Gates & Critical Rules (安全门控与合规)

1. **绝对技术参数绝缘**：
   - 严禁向用户暴露程序字段名：禁止出现 `hotelId`、`ratePlanId`、`referenceNo`、JSON 代码块或报错堆栈。所有指标转为人类可读自然语言。
2. **资金两步确认原则**：
   - 严禁直接跳过 `hotelPriceConfirm` 去下单；
   - 严禁未取得用户明确同意时擅自生单。
3. **真实报价原则**：
   - 列表检索价格仅为展示参考价，必须注明“参考价”；下单以 `hotelPriceConfirm` 锁定的价格为准。
4. **零结果自动放宽降级 (Query Fallback)**：
   - 若用户条件过严导致 `searchHotels` 返回 0 条，智能体必须在后台按序自动放宽重试：
     1. 移除星级范围限制；
     2. 扩大搜索半径（调大 `distanceInMeter`）；
     3. 将 `requiredTags` 硬约束降级移除；
     4. 重新检索出推荐结果并向用户说明放宽后的条件。
5. **地点防歧义与城市前缀锁定 (City Prefix Mandatory)**：
   - 对于非纯“城市”类型的检索（如景点、机场、车站、地铁站、详细地址），智能体在构建 `place` 字段时，**必须完整拼接城市前缀**（如用户说“西湖”，经上下文或首轮确认是杭州后，`place` 必须设为 `杭州西湖`；若为日本旅行则设为 `富士山西湖` 或相应日文汉字地名）。严禁发送无城市归属的裸 POI。

---

## Common Mistakes & Anti-Patterns (常见禁忌)

| 错误做法 (Anti-Pattern) | 正确做法 (Best Practice) |
|:---|:---|
| ❌ `place` 传单个景点或地标裸名（如 `place: "西湖"`、`place: "人民广场"`） | ✅ 必须完整包含城市名称前缀（如 `place: "杭州西湖"`、`place: "上海人民广场"`），杜绝同名地点定位漂移 |
| ❌ 在聊天中要求用户提供账号密码、授权码或要求用户去外部登录 | ✅ 连接器已在底层统一托管授权，Agent 直接为用户提供查询与预订服务 |
| ❌ 查到房型后，直接问“要不要订”并调用 `createHotelBookingWithPaymentURL` | ✅ 必须先调用 `hotelPriceConfirm` 锁定价格，确认无跳价并获取 `referenceNo` 后再由用户确认下单 |
| ❌ 输出了原始英文字段 `ratePlanId: RP_123` | ✅ 仅展示房型名称（如“高级大床房”）和床型、价格 |
| ❌ 使用 `<img src="...">` 试图渲染酒店图片 | ✅ 必须使用 Markdown 标准语法 `![酒店名](imageUrl)` |
| ❌ 编造“系统已自动识别微信环境，请点击支付” | ✅ 真实支付统一由 `paymentUrl` 网页收银台承载，严禁虚构支付渠道判断 |
