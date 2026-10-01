# 售后与出行服务流程

## 执行约束

1. **直接调用工具**：按各流程标明的 MCP 工具名调用，参数使用合法 JSON 对象；示例中的 ID 和业务数据仅用于说明参数结构。
2. **失败即停**：工具报错或返回含 `error`/失败 `code` 时，立即停止当前流程，向用户说明错误和可行的处理建议；禁止伪造结果或无条件反复调用。
3. **不可逆操作必须确认**：`uni_order_create`、`uni_order_cancel`、`refund_submit`、`reroute_submit`、`submit_invoice`、`manage_invoice`（cancel/update）、`grab_low_create_order`、`grab_low_cancel` 调用前必须向用户展示关键信息并等待明确确认；“嗯”“好”“可以”不算明确确认。
4. **按模板输出**：遵守各步骤输出模板和逻辑规则；接口字段缺失时不得编造。
5. **国内外分支判断**：`orderId` 以 D 开头为国内订单，以 I 开头为国际订单，退票/改期时按前缀走不同参数分支。
6. **禁止伪造参数**：所有接口参数必须来自用户明确提供或上游接口返回的真实值，严禁自行编造、猜测或硬编码 `flightInfoId`、`priceId`、`traceId`、`flightInfo`、`contactPhone` 等值。

---

## 退票流程

用户表达「退票/我要退/退掉这张票」等意图时，进入退票流程。

### 步骤 1：确认退票订单

先通过 `uni_order_query` 获取订单详情，确认订单号和机票 ID。

```text
工具：uni_order_query
参数：{"orderId":"D20260601001"}
```

向用户展示可退票的乘客/机票列表，让用户选择要退哪些票。

### 步骤 2：查询退票费

用户选择退票的机票后，调用 `refund_query_fee` 计算退票费用。

#### 调用方式

```text
# 国内订单自愿退票
工具：refund_query_fee
参数：{"orderId":"D20260601001","ticketIds":["TK001"],"refundType":0}

# 国际订单非自愿退票
工具：refund_query_fee
参数：{"orderId":"I20260610003","ticketIds":["TK999"],"refundType":1}
```

#### 输出模版

```text
退票费用明细：

订单号：[orderId]
退票类型：[自愿退票/非自愿退票]

| 乘客 | 原票价 | 退票手续费 | 预计退款 |
|------|--------|-----------|----------|
| [name] | ¥[ticketPrice] | ¥[refundFee] | ¥[refundAmount] |
| ... | | | |

合计退款：¥[totalRefund]

确认退票吗？请回复「确认退票」。
```

#### 逻辑规则

- 退票类型：0=自愿退票，1=非自愿退票（航班取消/延误等）。
- 必须先展示退票费用，等用户明确确认后才能提交退票。
- 非自愿退票需额外收集退票原因（`refundReasonType`）；国内非自愿还需附件 URL。

### 步骤 3：提交退票

用户明确回复「确认退票」后，调用 `refund_submit` 提交退票申请。

#### 调用方式

```text
# 国内订单自愿退票
工具：refund_submit
参数：{"orderId":"D20260601001","refundType":0,"ticketIds":["TK001"]}

# 国内订单非自愿退票（含原因和附件）
工具：refund_submit
参数：{"orderId":"D20260601001","refundType":1,"ticketIds":["TK001"],"refundReasonType":2,"url":"https://example.com/doc.jpg","refundRemark":"航班取消"}

# 国际订单自愿退票
工具：refund_submit
参数：{"orderId":"I20260610003","refundType":0,"tripInfoList":[{"segmentIds":["SEG001"],"passengerIds":["PAX001"]}],"contacts":{"phone":"13900139000"}}
```

#### 输出模版

```text
退票申请已提交！
订单号：[orderId]
退票类型：[自愿退票/非自愿退票]
预计退款：¥[totalRefund]

退款将按航司规则退回原支付方式，请耐心等待。
```

#### 逻辑规则

- 国内退票（D 开头 orderId）：必须传 `ticketIds`；非自愿退票时还须传 `refundReasonType` 和 `url`。
- 国际退票（I 开头 orderId）：必须传 `tripInfoList` 和 `contacts`；非自愿退票时还须传 `refundReasonType`。
- 非自愿退票原因（国内）：0-航班延误，1-航班备降，2-航班取消，3-航司会员退票，4-病退，5-其他。
- 非自愿退票原因（国际）：1-航班延误/取消/备降，2-因伤病无法出行，3-重复购买机票，4-航班拒签，5-航司优惠退，6-其他。
- 用户中途说「算了/不退了/停」立即停止。

---

## 改期流程

用户表达「改期/改签/换个日期」等意图时，进入改期流程。

### 步骤 1：确认改期订单

先通过 `uni_order_query` 获取订单详情，确认订单号和机票 ID。

```text
工具：uni_order_query
参数：{"orderId":"D20260601001"}
```

向用户确认要改期的机票，并收集目标日期。

### 步骤 2：查询改期可选航班

调用 `reroute_query_flight_filter` 查询目标日期的可选航班。

#### 调用方式

```text
# 国内订单自愿改期
工具：reroute_query_flight_filter
参数：{"orderId":"D20260601001","ticketIds":["TK001"],"date":"2026-06-10","rerouteType":0}

# 按时间和价格综合筛选
工具：reroute_query_flight_filter
参数：{"orderId":"D20260601001","ticketIds":["TK001"],"date":"2026-06-10","rerouteType":0,"filterType":3}
```

#### 输出模版

```text
[date] 可改期航班：

| 序号 | 航班 | 出发 → 到达 | 时间 | 舱位 | 差价 |
|------|------|-------------|------|------|------|
| 1 | [flightNo] | [出发机场][departureTime] → [到达机场][arrivalTime] | [duration] | [舱位] | [+¥X / -¥X / 无差价] |
| 2 | ... | | | | |

请选择目标航班序号。
```

#### 逻辑规则

- `tripId` 和 `priceId` 由此接口响应返回，供后续 `reroute_query_fee` 使用。
- 无可选航班时提示用户换日期或换路线。
- `filterType`：0=不筛选（默认），1=按时间距离最近，2=按价格差最少，3=同时按时间和价格筛选。

### 步骤 3：计算改期费用

用户选定目标航班后，调用 `reroute_query_fee` 计算改期费用。

#### 调用方式

```text
工具：reroute_query_fee
参数：{"orderId":"D20260601001","ticketIds":["TK001"],"tripId":"TRIP_001","priceId":"PRICE_NEW_001","date":"2026-06-10","rerouteType":0}
```

#### 输出模版

```text
改期费用明细：

订单号：[orderId]
改期类型：[自愿改期/非自愿改期]
原航班：[原flightNo] [原date] [原departureTime]
新航班：[新flightNo] [新date] [新departureTime]

| 乘客 | 改期手续费 | 票价差额 | 合计需付 |
|------|-----------|----------|----------|
| [name] | ¥[rerouteFee] | ¥[priceDiff] | ¥[total] |
| ... | | | |

合计费用：¥[totalFee]

确认改期吗？请回复「确认改期」。
```

#### 逻辑规则

- 必须先展示改期费用，等用户明确确认后才能提交改期。
- 改期类型：0=自愿改期，1=非自愿改期。
- `tripId`、`priceId` 来自 `reroute_query_flight_filter` 响应，禁止自行编造。

### 步骤 4：提交改期

用户明确回复「确认改期」后，调用 `reroute_submit` 提交改期申请。

#### 调用方式

```text
# 国内订单自愿改期
工具：reroute_submit
参数：{"orderId":"D20260601001","rerouteType":0,"ticketIds":["TK001"],"date":"2026-06-10","flightNo":"MU5100","departureAirportCode":"PEK","arrivalAirportCode":"SHA"}

# 国际订单自愿改期
工具：reroute_submit
参数：{"orderId":"I20260610003","rerouteType":0,"tripInfoList":[{"segmentIds":["SEG001"],"passengerIds":["PAX001"]}],"contacts":{"phone":"13900139000"},"expectTravelList":[{"tripIndex":1,"date":"2026-06-20"}]}
```

#### 输出模版

```text
改期申请已提交！
订单号：[orderId]
新航班：[新flightNo] | [出发机场][departureTime] → [到达机场][arrivalTime]
新日期：[date]
费用：¥[totalFee]

改期结果将通过通知告知您，请留意。
```

#### 逻辑规则

- 国内改期（D 开头 orderId）：必须传 `ticketIds`、`date`、`flightNo`、`departureAirportCode`、`arrivalAirportCode`；后三项来自 `reroute_query_fee` 响应。
- 国际改期（I 开头 orderId）：必须传 `tripInfoList`、`contacts`、`expectTravelList`。
- 用户中途说「算了/不改了/停」立即停止。

---

## 值机指引流程

用户表达「值机 / 在线值机 / 办值机 / 选座 / 登机牌」等意图时，进入值机指引流程。

### 异常回滚

- 出现核心异常时立即回滚到既有流程，不再继续值机分支。核心异常包括：工具不存在或被禁用、连续接口超时、返回字段结构与本流程不匹配、时间段判定无法唯一命中。
- 回滚时仅输出普通兜底话术：「暂时无法查询值机指引，建议您先通过航司官方渠道或机场柜台确认。也可以告诉我航班号，我帮您查航班动态。」不得暴露错误栈或内部异常。

### 数据来源与缺字段硬规则

- 值机指引只能使用 `trip_query` / `dynamic_flight_query` / `checkin_window` 三个内部接口返回字段，禁止使用公开数据、航司通用规则、机场通用规则兜底。
- `在线值机截止`、`柜台值机截止`、`登机口`、`柜台位置` 必须按字段独立判断，缺哪个字段就把该项展示为「暂未获取到」，不得用其它字段推算。
- 只有接口返回了明确截止时间，才允许做北京时间换算和格式化展示；字段缺失时不得根据起飞时间推算「起飞前 1 小时」「起飞前 45 分钟」或「约 HH:mm」。
- `checkin_window.data.ckiCloseTime` 缺失时，在线值机截止展示「暂未获取到」。
- `checkin_window.data.checkinDeadline` 缺失时，柜台值机截止展示「暂未获取到」。
- `dynamic_flight_query.data[0].gate` 缺失时，登机口展示「暂未获取到」。
- `dynamic_flight_query.data[0].checkIn.counter` 缺失时，柜台位置展示「暂未获取到」；仅 `depTerm` 存在时不得拼成柜台位置。
- 可保留建议文案「尽快通过航司官方渠道或机场现场确认」，但不得附带任何具体截止时间。

### 步骤 1：意图识别 + 行程锚定

- 用户已给航班号和日期时，直接进入步骤 2。
- 用户未给航班号或日期时，先调用 `trip_query` 查询最近一年待出行行程。

#### 调用方式

```text
工具：trip_query
参数：{"tripDateFrom":"<今天，yyyy-MM-dd>","tripDateTo":"<今天+365天，yyyy-MM-dd>"}
```

#### 逻辑规则

- `tripDateFrom` 取今天，`tripDateTo` 取今天 + 365 天。
- 过滤 + 展示强约束：只保留 `triptype === 'flight'` 的元素，train / hotel / car / other 等其它类型一律不进入后续判断，也不出现在向用户展示的确认或选择列表里。
- 按过滤后的 flight 数量分支；即使接口返回 5 个元素中只有 1 个 flight，也按 1 单处理，其它类型行程视为不存在。
- 查询结果为 0 单时，提示「请告诉我您的航班号与出发日期，或者起降地与出发日期，我来帮您查」，等待用户补充。
- 查询结果为 1 单时，确认式提问：「是想查询 [tripDate]（周X）[deptimeplan] [depcityname]飞[arrcityname]的 [tripNo] 航班吗？」；若 `relatedOrders.length > 1` 或 `tripNo` 含 `+`，末尾补「（中转的 [tripNo]）」。
- 查询结果为多单时，列表让用户选序号：「您近期有 N 个航班行程，想查询哪一个？1️⃣[tripDate]（周X）[deptimeplan] [depcityname]飞[arrcityname][tripNo] 2️⃣...」。
- 中转航班本期取第一段做后续 `dynamic_flight_query` 和 `checkin_window`，确认提问里保留完整 `tripNo`。

### 步骤 2：查航班基本信息

调用 `dynamic_flight_query` 查询航班基本信息。

#### 调用方式

```text
工具：dynamic_flight_query
参数：{"no":"HU5678","date":"<航班日期，yyyy-MM-dd>"}
```

#### 逻辑规则

- 入参：`no` = 用户提供或行程锚定的航班号，`date` = 航班日期。
- 若 `status !== "success"` 或 `data.length === 0`，失败即停，反馈「暂时查不到该航班信息，请核对航班号与日期」。
- 取 `data[0]`，缓存 `depCode`、`arrCode`、`flightNo`、`localDate`、`depTerm`、`depPlanTime`、`arrPlanTime`、`checkIn.counter`、`gate`、`state`、`subState`。
- 城市名优先使用 `trip_query` 的 `depcityname` / `arrcityname`；若用户直接给航班号未走行程查询，用 `depCode` / `arrCode` 三字码兜底。
- 现场值机柜台只有在 `checkIn.counter` 存在时才展示；`depTerm` 可作为前缀组合，例如 `T1航站楼D区`。`checkIn.counter` 缺失时，柜台位置必须展示「暂未获取到」。

### 步骤 3：查值机窗口

调用 `checkin_window` 查询线上值机、柜台值机和登机口关闭时间。

#### 调用方式

```text
工具：checkin_window
参数：{"depCode":"PEK","arrCode":"CAN","flightDate":"<航班日期，yyyy-MM-dd>","flightNo":"HU5678"}
```

#### 逻辑规则

- 入参 `depCode`、`arrCode` 来自步骤 2，`flightDate` 为航班日期，`flightNo` 为航班号。
- 若 `status !== "success"` 或 `data` 为空，失败即停，反馈「暂时查不到值机时间，建议以航司官方公众号/柜台为准」。
- `checkin_window` 返回的时间点均为起飞机场当地时间，段位判定前必须先按「时区换算规则」计算 `localNow`。
- `ckiOpenTime` / `ckiCloseTime` / `checkinDeadline` / `gateCloseTime` 任一缺失时，不得按通用规则补齐；缺失字段对应展示「暂未获取到」。如果缺失导致无法唯一命中段位，输出字段级未知指引，并建议用户尽快通过航司官方渠道或机场现场确认。

### 步骤 4：按起飞地当地时间输出唯一话术

先按「时区换算规则」把北京时间 `beijingNow` 换算成起飞机场当地时间 `localNow`，再用 `localNow` 与 `ckiOpenTime` / `ckiCloseTime` / `checkinDeadline` / `gateCloseTime` 比较，只能命中并输出一段话术，禁止拼接多段。

禁止直接拿北京时间或服务器当前时间与 `ckiOpenTime` / `ckiCloseTime` / `checkinDeadline` / `gateCloseTime` 比较；国际、港澳台、跨时区航班必须以起飞机场当地时间判定。

段位判断只能使用接口明确返回的时间字段。任一判断所需时间字段缺失时，不得用起飞时间、航司常见规则、机场常见规则、登机口、航班主状态或航班子状态推算；应输出字段级未知指引，不进入需要该字段的段位模板。

| 判定条件 | 命中话术 |
|---------|---------|
| `localNow` < `ckiOpenTime` | 段 1：暂未开放 |
| `ckiOpenTime` <= `localNow` < `ckiCloseTime` | 段 2：已开放 |
| `ckiCloseTime` <= `localNow` <= `checkinDeadline` | 段 3：线上值机已停，现场柜台仍可尝试 |
| `checkinDeadline` < `localNow` < `gateCloseTime`，并且 `checkinDeadline` / `gateCloseTime` 均为接口明确返回值 | 段 4：柜台值机已截止，登机口尚未关闭 |
| `localNow` >= `gateCloseTime`，并且 `gateCloseTime` 为接口明确返回值 | 段 5：已过登机时间 |

补救段不得用 `ckiOpenTime` / `ckiCloseTime` 作为下界；CA1301 类“18:00 柜台已截止、18:40 登机口关闭前”场景，必须命中段 4。`localNow` 达到或超过 `gateCloseTime` 后，不得再命中段 4。

### 时区换算规则

`checkin_window` 返回的 `ckiOpenTime` / `ckiCloseTime` / `checkinDeadline` / `gateCloseTime` 都是起飞机场当地时间；系统当前时间按北京时间（UTC+8）处理。判定段位前必须先换算：

```text
localNow = beijingNow + (depTimezoneOffset - 8) 小时
```

- `beijingNow` = 系统当前时间（北京时间）。
- `depTimezoneOffset` 优先取 `checkin_window.data.timezone`：数字如 `8` / `9` / `-5` 直接使用；IANA 字符串如 `Asia/Tokyo` 先转成 UTC 偏移数字。
- `timezone` 缺失或为空时，`depTimezoneOffset` 兜底取 `8`。
- 模板里展示的截止时间只有在接口返回明确字段时才允许格式化；需要展示北京时间时，必须基于接口返回时间和 `timezone` 换算。时间字段缺失时只展示「暂未获取到」，不得换算或推算。

示例 1（国内航班，无时差）：广州白云飞北京首都，`beijingNow` = 2026-07-10 07:00，`depTimezoneOffset` = 8，`localNow` = 07:00；若 `ckiOpenTime` = 06:05，则命中段 2。

示例 2（国际航班，东京 UTC+9）：东京成田飞上海浦东，`beijingNow` = 2026-07-10 07:00，`depTimezoneOffset` = 9，`localNow` = 08:00；若 `ckiOpenTime` = 07:00、`ckiCloseTime` = 09:30，则命中段 2。

### 字段映射

| 模板占位符 | 数据来源 | 说明 |
|-----------|---------|-----|
| `[flightNo]` | `dynamic_flight_query.data[0].flightNo` | 航班号 |
| `[airlineName]` | `trip_query.airlinename`（有则用），否则从航班号前 2 位映射 | 航司名 |
| `[depAirportShort]` | `dynamic_flight_query.data[0].depName`（有则用），否则 `trip_query.depcityname` | 出发机场简称 |
| `[arrAirportShort]` | `dynamic_flight_query.data[0].arrName`（有则用），否则 `trip_query.arrcityname` | 到达机场简称 |
| `[depTerm]` | `dynamic_flight_query.data[0].depTerm` | 出发航站楼 |
| `[arrTerm]` | `dynamic_flight_query.data[0].arrTerm` | 到达航站楼 |
| `[depDateFriendly]` | 按 `dynamic_flight_query.data[0].depPlanTime` 日期与当前日期计算 | 0 天=`今天（M月d日）`，1 天=`明天（M月d日）`，2 天=`后天（M月d日）`，其它=`M月d日（周X）` |
| `[depTime]` | `dynamic_flight_query.data[0].depPlanTime` 取 `HH:mm` | 起飞时间 |
| `[arrTime]` | `dynamic_flight_query.data[0].arrPlanTime` 取 `HH:mm` | 到达时间 |
| `[onlineOpenTime]` | `checkin_window.data.ckiOpenTime` | 线上值机开放时间 |
| `[onlineCloseTime]` | `checkin_window.data.ckiCloseTime` | 线上值机截止时间；缺失展示「暂未获取到」 |
| `[counterCloseTime]` | `checkin_window.data.checkinDeadline` | 柜台值机截止时间；缺失展示「暂未获取到」 |
| `[gateCloseTime]` | `checkin_window.data.gateCloseTime` | 登机口关闭时间；缺失展示「暂未获取到」 |
| `[gate]` | `dynamic_flight_query.data[0].gate` | 登机口；缺失展示「暂未获取到」 |
| `[counterLocation]` | `dynamic_flight_query.data[0].depTerm` + `dynamic_flight_query.data[0].checkIn.counter` | 值机柜台；`checkIn.counter` 缺失展示「暂未获取到」 |
| `[checkinUrl]` | `checkin_window.data.entryUrl` | 官方值机入口 URL |
| `[checkinEntryName]` | `checkin_window.data.entryDesc` | 入口名称 |

时间格式化规则：仅对接口明确返回的时间点格式化。所有时间点如与航班日期同一天则展示 `HH:mm`，否则前缀「今天/明天 」（例：`明天 08:05`）；「今天/明天」也按 `localNow` 的出发地当地日期判断。

### 话术模板

#### 段 1：暂未开放

```text
✈️ [flightNo] 值机指引
航班：[airlineName] [flightNo]｜[depAirportShort][depTerm] → [arrAirportShort][arrTerm]
时间：[depDateFriendly] 📅 [depTime] 起飞 → [arrTime] 到达

⏳ 在线值机（暂未开放）
开放时间：[onlineOpenTime]
截止时间：[onlineCloseTime]

🟢 现场值机
柜台位置：[counterLocation]
柜台截止：[counterCloseTime]

💡 建议：待在线值机开放后即可网上选座，或提前 3 小时到机场柜台办理。
```

#### 段 2：已开放

```text
✈️ [flightNo] 值机指引
航班：[airlineName] [flightNo]｜[depAirportShort][depTerm] → [arrAirportShort][arrTerm]
时间：[depDateFriendly] 📅 [depTime] 起飞 → [arrTime] 到达

🟢 在线值机（推荐）
已开放，现在就能办！
👉 [checkinEntryName]([checkinUrl])
截止时间：[onlineCloseTime]

🟢 现场值机
柜台位置：[counterLocation]
柜台截止：[counterCloseTime]
登机口：[gate]
登机口关闭：[gateCloseTime]

💡 建议：现在在线值机选好座位，到机场直接过安检；建议提前 90 分钟到机场，登机口信息以航司通知为准。
```

#### 段 3：线上值机已停，现场柜台仍可尝试

```text
✈️ [flightNo] 值机指引
航班：[airlineName] [flightNo]｜[depAirportShort][depTerm] → [arrAirportShort][arrTerm]
时间：[depDateFriendly] 📅 [depTime] 起飞 → [arrTime] 到达

⛔ 在线值机（已停止）
已于 [onlineCloseTime] 停止办理

🚨 现场紧急办理
1️⃣ 立刻前往出发大厅，找 [airlineName] 的"晚到旅客/紧急柜台"，向工作人员说明情况
2️⃣ 恳请在登机牌上加盖"优先安检章"，凭此走紧急通道快速过检
登机口：[gate]
登机口关闭：[gateCloseTime]

⚠️ 登机口即将关闭，请务必抓紧时间！
```

#### 段 4：柜台值机已截止，登机口尚未关闭

```text
✈️ [flightNo] 值机指引
航班：[airlineName] [flightNo]｜[depAirportShort][depTerm] → [arrAirportShort][arrTerm]
时间：[depDateFriendly] 📅 [depTime] 起飞 → [arrTime] 到达

❌ 已无法办理值机
柜台值机已于 [counterCloseTime] 截止，但当前登机口尚未关闭。

🚨 现场紧急补救
1️⃣ 立即寻找 [airlineName] 的"晚到旅客/紧急柜台"
2️⃣ 请求工作人员协助办理，并申请"优先安检章/紧急通道"
登机口：[gate]
登机口关闭：[gateCloseTime]

⚠️ 登机口即将关闭，请务必抓紧时间！
```

#### 段 5：已过登机时间

```text
✈️ [flightNo] 已过登机时间
航班：[airlineName] [flightNo]｜[depAirportShort][depTerm] → [arrAirportShort][arrTerm]
时间：[depDateFriendly] 📅 [depTime] 起飞 → [arrTime] 到达

❌ 已无法办理值机
[flightNo] 已过登机口关闭时间（[gateCloseTime]），本次航班无法再登机。

⛔ 请勿前往柜台或登机口，来不及了。

💡 建议：联系 [airlineName] 官方客服办理改签或退票，尽早安排后续行程。
```

### 逻辑规则

- 每段严格按上面结构逐字输出，emoji 位置、分组行、空行不得改。
- 分组间以一个空行分隔。
- 线上值机链接展示为「👉 [checkinEntryName]([checkinUrl])」超链接，指向 `entryUrl`。
- 段 1 不展示 `entryUrl`；段 5 不展示时间分组、现场值机分组、登机口信息和柜台信息。
- 段 4 必须展示登机口关闭时间；若 `gateCloseTime` 缺失，不命中段 4，不得用登机口、航班主状态或航班子状态证明仍在登机，必须输出字段级未知指引或兜底处理。
- 段 4 禁止输出「请勿前往柜台或登机口」「请勿再前往柜台」「来不及了」，禁止只建议改签/退票。
- 改签/退票只允许出现在段 5。
- 国际/港澳台不做特殊分支；如 `checkin_window` 缺 `ckiOpenTime` / `ckiCloseTime`，按字段展示「暂未获取到」，并提示「建议尽快通过航司官方渠道或机场现场确认」。
- DL607 等接口缺字段场景必须输出「暂未获取到」，不得出现「约 18:00」「约 18:15」「起飞前 1 小时」「起飞前 45 分钟」等编造值。
- 任一工具调用失败时，必须先服从「异常回滚」里的核心异常回滚规则；不重试、不伪造字段。

### 禁止词清单

AI 生成值机话术时必须过滤以下词，不得在模板外自行补充承诺或补救动作。

**全局禁用（任何一段都不许出现）**

| 禁用词 | 替换说法 | 原因 |
|--------|----------|------|
| 免费改签 | 办理改签 | 是否免费取决于航司规则和舱位，不能承诺 |
| 免费退票 | 办理退票 | 是否免费取决于航司规则和舱位，不能承诺 |
| 全额退票 | 办理退票 | 是否全额取决于航司规则和舱位，不能承诺 |
| 保证赔付 / 一定赔 | 咨询航司理赔政策 | 涉及金额承诺，不能确定答复 |

**段 4 专属禁用**

| 禁用词 | 说明 |
|--------|------|
| 请勿再前往柜台 / 请勿前往柜台 | 禁止在补救窗口阻止用户找紧急柜台 |
| 来不及了 | 禁止否定仍可能存在的登机补救窗口 |
| 改签 / 退票 | 禁止在仍可现场补救时只给退改方向 |

**段 5 专属禁用（固定禁令行除外）**

| 禁用词 | 说明 |
|--------|------|
| 柜台 | 禁止引导用户继续现场补救 |
| 登机口 | 禁止暗示仍可登机或赶登机 |
| 前往 / 过去 | 禁止引导用户继续赶现场 |
| 赶紧 / 紧急 | 禁止制造仍有补救窗口的误导 |
| 晚到旅客 | 禁止拼接段 3 补救话术 |
| 优先安检章 | 禁止拼接段 3 补救话术 |

---

## 报销开票流程

用户表达「报销/开发票/开票」等意图时，进入报销开票流程。

### 步骤 1：查询可报销订单

调用 `query_invoiceable` 查询可开票的订单列表。

#### 调用方式

```text
# 查全部可报销订单
工具：query_invoiceable
参数：{}

# 查指定订单可报销详情
工具：query_invoiceable
参数：{"orderId":"D20260601001"}
```

#### 输出模版

**无可报销订单**：

```text
暂无可报销的订单。
```

**有可报销订单**：

```text
可报销订单：

| 序号 | 订单号 | 航班 | 日期 | 可报销金额 |
|------|--------|------|------|-----------|
| 1 | [orderId] | [flightNo] | [date] | ¥[amount] |
| 2 | ... | | | |

请告诉我要对哪个订单开票，以及开票信息：
- 发票抬头（个人姓名或公司名称）
- 接收邮箱
- 企业开票需提供纳税人识别号
```

### 步骤 2：确认开票信息并提交

收集开票信息后，向用户确认并调用 `submit_invoice`。

#### 需收集信息

- `email`：接收发票的邮箱
- `title`：发票抬头
- `invoiceTitleType`：0=个人，1=企业，2=机关/事业单位/军队
- `identityId`：纳税人识别号（企业类型必填）

#### 确认模版

```text
开票信息确认：

订单号：[orderId]
发票抬头：[title]
抬头类型：[个人/企业/机关事业单位]
[企业时] 纳税人识别号：[identityId]
接收邮箱：[email]
开票金额：¥[amount]

确认开票吗？请回复「确认开票」。
```

#### 调用方式

```text
# 个人发票
工具：submit_invoice
参数：{"orderId":"D20260601001","voucherOrderInfo":"VOUCHER_INFO_001","email":"zhangsan@example.com","title":"张三","invoiceTitleType":0}

# 企业发票
工具：submit_invoice
参数：{"orderId":"D20260601001","voucherOrderInfo":"VOUCHER_INFO_001","email":"finance@company.com","title":"某某科技有限公司","invoiceTitleType":1,"identityId":"91110101MA0123456X"}
```

#### 输出模版

```text
开票申请已提交！
订单号：[orderId]
发票抬头：[title]
接收邮箱：[email]

发票将发送至您的邮箱，请注意查收。
```

#### 逻辑规则

- `voucherOrderInfo` 来自 `query_invoiceable` 响应，必须先查询再提交。
- `invoiceTitleType` 为 1（企业）时，`identityId` 必填。
- 必须向用户确认开票信息后再执行。

---

## 凭证管理流程

用户表达「查发票/发票状态/修改发票/重发发票/取消发票」等意图时，进入凭证管理流程。

### 步骤 1：查询已开票凭证

调用 `query_invoices` 获取已提交凭证信息。

#### 调用方式

```text
# 查全部凭证历史
工具：query_invoices
参数：{}

# 查指定包裹详情
工具：query_invoices
参数：{"postId":"P20260601001"}

# 查指定订单凭证历史
工具：query_invoices
参数：{"orderId":"D20260601001"}
```

#### 输出模版

```text
已开票记录：

| 序号 | 包裹号 | 订单号 | 发票抬头 | 状态 | 邮箱 |
|------|--------|--------|----------|------|------|
| 1 | [postId] | [orderId] | [title] | [status] | [email] |
| 2 | ... | | | | |

可操作：重发到新邮箱 / 修改抬头 / 取消凭证。告诉我需要什么操作。
```

### 步骤 2：执行凭证操作

根据用户意图调用 `manage_invoice`，执行前二次确认（cancel/update 为不可逆操作）。

#### 调用方式

```text
# 取消凭证
工具：manage_invoice
参数：{"action":"cancel","postId":"P20260601001","orderId":"D20260601001"}

# 重发到新邮箱
工具：manage_invoice
参数：{"action":"resend","postId":"P20260601001","orderId":"D20260601001","email":"newmail@example.com"}

# 修改发票抬头
工具：manage_invoice
参数：{"action":"update","postId":"P20260601001","orderId":"D20260601001","title":"新抬头","invoiceTitleType":1,"identityId":"91110101MA0123456X"}
```

#### 确认模版（cancel/update）

```text
确认[取消/修改]凭证吗？

包裹号：[postId]
订单号：[orderId]
[update 时展示修改内容]

⚠️ 此操作不可撤销。请明确回复「确认」。
```

#### 输出模版

**取消成功**：

```text
凭证已取消。
包裹号：[postId]
```

**重发成功**：

```text
凭证已重发。
包裹号：[postId]
发送至：[email]
```

**修改成功**：

```text
凭证信息已修改。
包裹号：[postId]
新抬头：[title]
```

#### 逻辑规则

- `postId` 来自 `query_invoices` 响应（P 开头包裹号），禁止自行编造。
- cancel/update 为不可逆操作，必须二次确认。
- resend 时 `email` 必填。
- update 时 `email`/`title`/`invoiceTitleType`/`identityId` 至少填一个。
- update 且 `invoiceTitleType` 为 1（企业）时，`identityId` 必填。
- 用户中途说「算了/不改了/停」立即停止。

---
