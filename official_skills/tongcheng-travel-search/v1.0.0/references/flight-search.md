# 航班搜索路由

## 使用 `flight_search`

当需求是航班搜索，且出发城市、到达城市、出发日期明确或可从上下文无歧义确定时使用。`flight_search` 不支持原生往返查询；往返需求必须拆成去程和返程，并按两个方向分别调用一次 `flight_search`。

- 城市的 `cityName` / `cityCode` 至少传一个；不知道准确三字码时传 `cityName`，不要猜编码。
- 用户未指定机场时不要传 `airportName` / `airportCode`。
- 人数、舱等、航司、时间段、直飞和行李等约束仅在 schema 支持时按原意传递。
- “只看直飞”使用 `filter.onlyDirect=true`；“直飞优先”使用 `DIRECT_FIRST` 升序，不得混淆。
- 用户只提出日期、航线、价格、舱等、航司、时间段、机场、直飞等客观搜索条件时，优先直连，不要因为条件较多就改走 `ai_search`。

直连示例：

| 用户需求 | 路由 | 原因 |
|---|---|---|
| “明天北京到上海的机票” | `flight_search` | 单程，出发地、目的地和日期齐全 |
| “10月1日上海到东京，只看直飞经济舱” | `flight_search` | 单程且筛选条件可由 schema 表达 |
| “9月20日广州到成都，南航，上午出发” | `flight_search` | 单程且航司、时间段明确 |
| “10月1日北京飞成都，5日返回” | 两次 `flight_search` | 分别搜索北京到成都的去程和成都到北京的返程 |

## 使用 `flight_detail` 或 `flight_estimate` 进入验价

- 用户从 `flight_search` 结果中选定国内航班并查询舱位、价格、库存、退改签或行李额：使用 `flight_detail`，原样传递 `flightNo`、出发/到达城市（含机场信息）和 `departDate`。
- 用户选定国际航班：使用 `flight_detail`，原样传递同一条搜索结果中的 `flowId` 和 `tripId`，以及出发/到达城市和 `departDate`。
- 用户在国际航班详情中选定具体产品并要求确认最新价格或验价：使用 `flight_estimate`，通过 `productResource` 传 `flight_detail` 返回的 `flowId`、`tripId`、`productId`、`detailKey`、`resourceId` 和相同乘客人数。

仅选定航班搜索结果时，先调用 `flight_detail`；已经选定详情中的具体产品，且完整验价标识仍在上下文中时，直接调用 `flight_estimate`。

机票使用“搜索 -> 详情 -> 验价”的调用顺序；`flight_estimate` 仅支持国际航班，通过 `productResource` 的四段标识进入。验价返回预估单和后续创单所需数据，验价和乘客适用性校验成功不等于已经支付或出票。

### 国际验价入参（`productResource`）

- `productResource` 必填，其中 `flowId`、`tripId`、`productId`、`detailKey`、`resourceId` 必须原样取自同一条 `flight_detail` 产品结果，禁止自行生成、修改或混用不同产品字段。
- `passengerCount` 必填，并且必须与 `flight_detail` 查询时使用的乘客人数一致；`adultCount` 必须大于 0，`childCount`、`infantCount` 不传默认 0，人数不能为负数，儿童不超过成人数的 2 倍，婴儿不超过成人数，总人数不超过 9 人。
- `flowId` 必须使用 `flight_detail` 返回的值，不要传联系人、完整乘客信息或优惠字段。

## 使用 `ai_search`

以下情况直接使用 `ai_search`：

- 使用模糊评价、主观体验或个性化长尾标准选择航班，例如“飞得舒服”“服务好”“适合容易晕机的人”“带婴儿更省心”；
- 在同一次航班搜索中，需要结合时间、价格、行李、舒适度或服务体验等多个维度进行语义筛选，且需求无法由 `flight_search` 的标准字段直接表达。

AI 搜示例：

| 用户需求 | 路由 | 原因 |
|---|---|---|
| “明天北京到上海，想选飞得舒服、服务好的航班” | `ai_search` | “舒服”“服务好”属于主观体验标准，普通航班筛选无法直接确认 |
| “带一岁宝宝飞三亚，哪个航班更省心” | `ai_search` | 婴儿出行体验属于个性化长尾需求，需要综合判断 |
| “北京到上海，想兼顾价格、行李和乘坐舒适度” | `ai_search` | 属于航班垂类内的非标准需求筛选 |

## 与航班接口配合

- 标准航线和筛选条件直接使用 `flight_search`；成功返回后不要再调用 `ai_search` 重复搜索。
- 长尾、非标准、主观体验等非标准需求直接使用 `ai_search`；如用户随后改为只按标准条件查询，再调用 `flight_search`。
- `ai_search` 返回也包含 `flightNo`、`tripId`、`flowId` 等真实产品标识。用户选定航班后，若返回字段足以满足 `flight_detail` 入参要求（国内需 `flightNo` + 城市 + 机场 + `departDate`；国际需 `flowId` + `tripId` + 城市 + `departDate`），可直接调用 `flight_detail`；字段缺失时再用 `flight_search` 补齐。国际航班继续验价时调用 `flight_estimate`；国内航班不支持验价。
- `flight_search` 报错、超时或为空时先如实说明；若用户需求本身属于 `ai_search` 适用范围（长尾、非标准、主观体验等），可再调用 `ai_search` 兜底，不强制、不默认。

## 边界
- 不要把“舒服”“服务好”等模糊标准擅自等价为某个舱等、机型、航司或价格条件；应交给 `ai_search` 分析，并说明仍需校验实时产品信息。
- 搜索价不是最终可售价格；国际产品需要按顺序执行搜索、详情、验价，国内产品只支持搜索和详情。
- 不能生成或猜测 `flowId`、`tripId`、`detailKey`、`productId`、`resourceId`。
- 机票验价能力不包括代用户完成支付、出票、订单查询或退改签办理。
- `ai_search` 不能替代实时航班库存或航班验价。
- `ai_search` 不处理航班与火车、酒店之间的比较，也不处理多城市行程规划。
- 签证、机场接送、目的地攻略等非航班产品搜索问题不属于本技能范围。
