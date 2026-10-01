# 购票与低价抢票流程

## 执行约束

1. **直接调用工具**：按各流程标明的 MCP 工具名调用，参数使用合法 JSON 对象；示例中的 ID 和业务数据仅用于说明参数结构。
2. **失败即停**：工具报错或返回含 `error`/失败 `code` 时，立即停止当前流程，向用户说明错误和可行的处理建议；禁止伪造结果或无条件反复调用。
3. **不可逆操作必须确认**：`uni_order_create`、`uni_order_cancel`、`refund_submit`、`reroute_submit`、`submit_invoice`、`manage_invoice`（cancel/update）、`grab_low_create_order`、`grab_low_cancel` 调用前必须向用户展示关键信息并等待明确确认；“嗯”“好”“可以”不算明确确认。
4. **按模板输出**：遵守各步骤输出模板和逻辑规则；接口字段缺失时不得编造。
5. **国内外分支判断**：`orderId` 以 D 开头为国内订单，以 I 开头为国际订单，退票/改期时按前缀走不同参数分支。
6. **禁止伪造参数**：所有接口参数必须来自用户明确提供或上游接口返回的真实值，严禁自行编造、猜测或硬编码 `flightInfoId`、`priceId`、`traceId`、`flightInfo`、`contactPhone` 等值。

---

## 机票查询与购票流程

### 步骤 1：查询航班

用户表达查票/买票意图后，调用 `search_flights` 查询航班列表。

#### 必传参数

⚠️ 以下参数**每次调用必须带上**，不得省略：

```
"onlyDirect":"true"
"sortBy":"totalPrice"
"sortOrder":"asc"
```

用户主动要求中转航班时去掉 `onlyDirect`；用户指定其他排序时按用户要求覆盖 `sortBy`/`sortOrder`。

#### 调用方式

```text
工具：search_flights
参数：{"date":"2026-06-01","departureCityCode":"BJS","arrivalCityCode":"SHA","cabinPreference":"Y","onlyDirect":"true","sortBy":"totalPrice","sortOrder":"asc"}
```


#### 输出模版

```text
[date] [出发城市] → [到达城市] 为您精选出 X 个航班

[国内航班]
| 序号 | 航班号 | 起抵时间 | 机场 | 机型 | 票价 | 推荐理由 |
|------|--------|----------|------|------|------|----------|
| 1 | [flightNo] | [departureTime] → [arrivalTime] | [departureAirportName][departureTerminal]→[arrivalAirportName][arrivalTerminal] · 经停[layoverCity] | [aircraftModel] | [saving 有值时：~~¥originalPrice~~ ¥lowestTotalPrice 💰 已优惠 ¥saving；否则：¥lowestTotalPrice] | 推荐理由 |
| 2 | ... | | | | | |

[国际航班]
| 序号 | 航班号 | 起抵时间 | 机场 | 机型 | 总价 | 推荐理由 |
|------|--------|----------|------|------|------|----------|
| 1 | [flightNo] | [departureTime] → [arrivalTime] | [departureAirportName][departureTerminal]→[arrivalAirportName][arrivalTerminal] · 经停[layoverCity] | [aircraftModel] | [saving 有值时：~~¥originalPrice~~ ¥lowestTotalPrice 💰 已优惠 ¥saving；否则：¥lowestTotalPrice] | 推荐理由 |
| 2 | ... | | | | | |

[总航班 > 5 时] 💡 以上按「用户本次要求 + 价格 + 出发时间 + 时长 + 是否直飞」综合推荐 5 条，如需看全部航班，告诉我即可。

[本次展示的航班中至少一条 saving 有值时] 💡 温馨提示：以上价格为享受优惠后的预估到手价，实际价格受优惠券规则影响（如限本人使用、限航线等），下单前请确认券的使用条件～
```

**示例输出**（供参考，实际按接口返回字段填充）：

```text
2026-05-21 北京 → 上海 为您精选出 2 个航班

| 序号 | 航班号 | 起抵时间 | 机场 | 机型 | 票价 | 推荐理由 |
|------|--------|----------|------|------|------|----------|
| 1 | MU5138 | 07:00 → 09:10 | 大兴→虹桥T2 | 空客320 | ~~¥570~~ ¥560 💰 已优惠 ¥10 | 低价推荐 |
| 2 | MU5100 | 07:00 → 08:55 | 首都T2→浦东T1 · 经停南京 | 空客320 | ¥562 | 飞行时间段 |

💡 以上按「用户本次要求 + 价格 + 出发时间 + 时长 + 是否直飞」综合推荐 5 条，如需看全部航班，告诉我即可
💡 温馨提示：以上价格为享受优惠后的预估到手价，实际价格受优惠券规则影响（如限本人使用、限航线等），下单前请确认券的使用条件～
💡 需要查看某个航班的详细舱位和退改规则？告诉我序号即可。
```

#### 逻辑规则

- **仅直飞降级重试**：若传了 `onlyDirect:"true"` 但查询后无航班返回，自动去掉 `onlyDirect` 参数重新查询一次（即包含中转航班），无需额外确认。展示时标注中转信息。
- **起抵时间合并**：起飞、到达时间合并为 `[departureTime] → [arrivalTime]`；跨日到达在到达时间后追加 `+X日`。
- **国内/国际价格列区分**：国内表头显示「票价」，国际表头显示「总价」。`saving` 有值时展示 `~~¥[originalPrice]~~ ¥[lowestTotalPrice] 💰 已优惠 ¥[saving]`；`saving` 无值时只展示 `¥[lowestTotalPrice]`。
- **经停展示**：航班有经停数据时，在机场信息后用 ` · ` 分隔并展示 `经停[layoverCity]`；无经停数据则不展示。
- 一次最多展示 5 条；超出时先展示综合推荐前 5 条，用户追问后再展示后续航班。
- 综合推荐维度：优先满足用户本次明确要求（舱位/航司/时间），再结合价格、出发时间、时长、是否直飞排序；每条可补 1-2 个推荐理由，如「价格低」「直飞」「时间好」。
- 中转航班标注中转次数和经停城市；跨日标「+X日」。
- **中转航班注意事项** 中转航班需要航班号、航司使用"+"拼接，机场要全部显示。
- 共享航班标注「共享」；展示实际承运航司。
- **温馨提示条件**：仅当本次展示的航班中至少一条 `saving` 有值时，才在列表下方追加「💡 温馨提示：以上价格为享受优惠后的预估到手价，实际价格受优惠券规则影响（如限本人使用、限航线等），下单前请确认券的使用条件～」；全部无 `saving` 时不得展示。随后固定追加：「💡 需要查看某个航班的详细舱位和退改规则？告诉我序号即可。」

---

### 步骤 2：查询舱位详情

用户选定航班后（或需要查看退改规则时），调用 `get_flight_offers` 获取舱位详情。

#### 禁止参数

⚠️ `get_flight_offers` **禁止传 `priceId`**，该参数不属于此接口。

#### 调用方式

```text
工具：get_flight_offers
参数：{"flightInfoId":"FI20260601BJS_SHA_001","traceId":"trace-abc123","cabinPreference":"Y"}
```


#### 输出模版

```text
✈️ [航司名][flightNo] | [出发机场][departureTime] → [到达机场][arrivalTime] | [duration] | 经停[layoverCity]

舱位方案：

| 序号 | 舱位 |票面价|税| 总价 | 余票 | 退改规则 |行李信息 |
|------|------|------|------|----------|----------|----------|-------|
| 1 | [cabinName]([cabinCode]) | [saving 有值时：~~¥originalPrice~~ ¥price；否则：¥price] | ¥[tax] | [saving 有值时：¥totalPrice 💰 已优惠 ¥saving；否则：¥totalPrice] | [seatsLeft] | [ruleSummary] | [baggageSummary] |
| ... | | | | | |||

请选择舱位序号，或告诉我您要订哪个方案。
```

**示例输出**（供参考，实际按接口返回字段填充）：

```text
✈️ 东航MU5138 | 大兴→虹桥T2 07:00 → 09:10 | 02:10 | 经停南京

舱位方案：

| 序号 | 舱位 |票面价|税| 总价 | 余票 | 退改规则 |行李信息 |
|------|------|------|------|----------|----------|----------|-------|
| 1 | 会员专享座(R4) | ~~¥420~~ ¥379 | ¥120 | ¥499 💰 已优惠 ¥41 | 9 | 退改¥294起 | 无免费托运行李 |
| 2 | 商务舱(Z) | ¥1000 | ¥120 | ¥1120 | 4 | 提前改期免退 | 免费托运20KG |

请选择舱位序号，或告诉我您要订哪个方案。

```

#### 逻辑规则

- 展示所有可用舱位方案，按价格升序排列；超过 5 个时只展示价格最低的前 5 个，用户追问时再展示后续。
- **序号列强制显示**：每行必须有序号（1、2、3…），不得省略或合并。
- **舱位列仅显示 `[cabinName]([cabinCode])`**：只允许展示舱位名称和舱位代码，格式固定为 `cabinName(cabinCode)`，不得追加任何其他字段（如折扣、产品标签、营销文案等）。
- **价格优惠展示**：`saving` 有值时，票面价仅展示 `~~¥[originalPrice]~~ ¥[price]`，总价展示 `¥[totalPrice] 💰 已优惠 ¥[saving]`；不得换行。`saving` 无值时分别展示 `¥[price]`、`¥[totalPrice]`，不展示 `originalPrice` 和优惠文案。票面价、税和总价均不得追加 `/人` 或“人”后缀。
- 退改规则用简短摘要（如「起飞前免费退」「退票费 20%」「不可退」），详细规则用户追问时再完整展示。
- 余票当seatsLeft>9显示充足，否则显示具体数字。
- `flightInfoId` 和 `traceId` 均来自 `search_flights` 响应，禁止自行编造。
- **经停展示**：航班有经停数据时，在飞行时长 `[duration]` 后追加 `| 经停[layoverCity]`；无经停数据则不展示。
- 用户选定舱位后记录 `priceId`、`flightInfoId`、`orderSource`，进入步骤 3。

---

### 步骤 3：获取乘机人列表

用户选定舱位后，**必须先调用** `uni_query_flight_confirm` 获取已有乘机人列表，再完成乘机人选择或新增乘机人补录。此步骤固定传 `withPassengers:true`、`withAuthCode:true`。未完成本步骤，不得进入步骤 4。

#### 调用方式

```text
工具：uni_query_flight_confirm
参数：{"priceId":"PRICE_XYZ","flightInfoId":"FI20260601BJS_SHA_001","orderSource":"domestic","products":[],"withPassengers":true,"withAuthCode":true}
```

#### 输出模版

```text
已有乘机人列表：

| 序号 | 姓名 | 证件类型 | 证件号 | 乘客类型 |
|------|------|----------|--------|----------|
| 1 | [name][myself == 1 时追加【本人】] | [idType] | [idCardMask] | [type] |
| 2 | ... | | | |

请选择乘机人序号（可多选），或输入新乘客信息。
[passengerEditUrl 有值时]如需编辑乘机人，请前往[常用乘机人页面]([passengerEditUrl])。修改后告诉我“刷新一下”。
同时请提供联系人信息：
- 联系人姓名（不输入则默认使用第一位乘机人姓名）
- 联系人手机号（必填用于接收出票和航变等消息通知）
```

#### 逻辑规则

- `priceId`、`flightInfoId`、`orderSource` 均来自步骤 2 `get_flight_offers` 的响应，禁止自行编造。
- 从接口返回的 `passengers[]` 获取已有乘机人列表并展示供用户选择，减少手动输入。
- `passengerEditUrl` 有值时展示“常用乘机人”编辑链接；用户回复“刷新一下”后，使用步骤 3 原参数重新调用 `uni_query_flight_confirm`（`withPassengers:true`、`withAuthCode:true`）获取最新列表。
- 姓名列根据 `myself` 标记本人：`myself == 1` 时显示 `[name]【本人】`，例如 `张三【本人】`；其他值仅显示 `[name]`。标签只用于展示，不得拼入下单参数中的姓名。
- 用户从列表中选择乘机人时，记录对应的 `cdid`，下单时通过 `cdids` 参数传入，无需再传 `passengers` 。
- 用户从列表中选择乘机人，选择之后需要对信息做校验，确保信息的准确性和完整性。
- 用户也可手动输入新乘客信息，此时下单通过 `passengers` 参数传入。
- 可混合使用：部分选已有乘机人（`cdids`）+ 部分手动输入（`passengers`）。
- 若返回为空，跳过选择，直接进入步骤 4 收集乘客信息。
- 证件号展示时脱敏（保留前后各 3 位）。
- **儿童校验**：乘机人中有儿童（CHD）时，必须校验「1 名成人最多携带 2 名儿童」。若成人数量不够，提示用户调整乘机人，例如「当前 X 名成人最多携带 Y 名儿童，您选了 Z 名儿童，请增加成人或减少儿童」。
- 成人、儿童的准确价格统一以步骤 4 返回的 `orderPrice.ticketPrices[]` 为准；不得再用 `get_flight_offers` 的参考儿童价拼接订单总价。
---

### 步骤 4：行程确认

完成步骤 3 的乘机人列表查询，并确定本次出行的全部乘机人后，才可再次调用 `uni_query_flight_confirm` 获取准确价格并展示行程确认。

#### 调用方式

已有乘机人传 `cdids`，新增乘机人传完整 `passengers`，两者可同时传；`withPassengers` 固定为 `false`。

```text
工具：uni_query_flight_confirm
参数：{"priceId":"PRICE_XYZ","flightInfoId":"FI20260601BJS_SHA_001","orderSource":"domestic","cdids":["cdid_001"],"products":[],"withPassengers":false}
```

#### 输出模板

```text
行程确认：

✈️ [flightNo] [airlineName] | [date]（[weekday]）
📍 [departureAirport][departureTerminal] → [arrivalAirport][arrivalTerminal]
🕐 [departureTime] → [arrivalTime]（[duration]） | [cabinName]([cabinCode])

| 乘客 | 类型 | 证件 |
|------|------|------|
| [name][myself == 1 时追加【本人】] | [成人/儿童] | [证件类型] [证件号脱敏] |

价格：
- 支付总价：¥[按 orderPrice.payPrice 与当前选中优惠券计算的展示支付总价]
- 价格明细：
  ([ADT.ticketPrice] 票面价 + ¥[ADT.airportFee + ADT.oilFee] 机建燃油) × [成人数] 成人
  [有儿童时]([CHD.ticketPrice] 票面价 + ¥[CHD.airportFee + CHD.oilFee] 机建燃油) × [儿童数] 儿童
  [逐项展示 orderPrice.discountDetails：]减 ¥[amount] [title]
  [当前选中券为立减券：]减 ¥[amount] [name]（立减券）
  [当前选中券为返现券：]返 ¥[amount] [name]（出行后返现，不抵扣当前支付总价）

产品说明：
- 退改规则：[ruleSummary]
- 行李：[baggageSummary]

联系人：[contactName] [contactPhone]

如需更换其他优惠券，请告诉我；确认下单请回复「确认购买」。
```

#### 逻辑规则

- **强制前置校验**：本次所选舱位必须已成功调用 `uni_query_flight_confirm` 且参数为 `withPassengers:true`、`withAuthCode:true`；未调用、调用失败，或乘机人尚未完成选择/补录时，禁止进行步骤 4 的行程确认，也不得展示行程确认。
- 不得仅依据历史对话中的乘机人信息跳过步骤 3；仍须先查询最新乘机人列表。
- 行程确认请求必须携带本次已确定的乘机人：已有乘机人使用 `cdids`，新增乘机人使用完整 `passengers`；两者都为空时禁止调用。
- 展示前补齐乘机人和联系人；缺什么只问什么。新增乘机人必须传完整未脱敏信息；国际乘机人按接口要求补齐证件字段。
- 乘机人、航班、舱位或附加产品变化时，使用全部最新信息重新调用；旧价格和优惠券结果作废。
- `orderPrice.payPrice` 是创建订单时使用的原始应付金额，也是优惠券展示计算的固定基数；`priceInfo` 仅作参考，禁止拼接总价。
- 初次确认以 `orderPrice.recommendCoupon` 作为当前选中券。若有值，按券类型计算页面“支付总价”：
  - `benefitType=INSTANT_DISCOUNT` 且 `affectsPayablePrice=true`：展示支付总价 = `max(0, orderPrice.payPrice - recommendCoupon.amount)`。
  - `benefitType=CASHBACK` 或 `affectsPayablePrice=false`：展示支付总价 = `orderPrice.payPrice`，并标注“出行后返现，不抵扣当前支付总价”。
  - 其他或类型不明：不得自行扣减，展示支付总价保持 `orderPrice.payPrice`。
  - `recommendCoupon` 无值：展示支付总价保持 `orderPrice.payPrice`，不展示优惠券项。
- 价格明细只取 `ticketPrices[]`、`discountDetails[]` 和当前选中优惠券。
- **价格明细前缀**：`discountDetails[]` 和立减券以“减”开头，返现券以“返”开头；不使用减号等符号。
- 初次不展示 `couponInfo` 列表，只展示 `recommendCoupon`，并提示可更换优惠券。
- 证件号仅展示脱敏值；`【本人】`只用于展示。
- 用户明确回复“确认购买/确认下单/买”后才进入步骤 5；“嗯/好/可以/是的”不算确认。

#### 更换优惠券

用户明确要求查看或更换优惠券时，才展示最近一次确认结果中的 `couponInfo`：

```text
🎟️ 查看优惠券列表

✅ 可用优惠券/红包
| 序号 | 优惠券金额 | 券名称 | 有效期 | 使用规则 |
|------|------------|--------|--------|----------|
| [sequence] | ¥[amount] | [name][当前推荐券时追加「推荐」] | 至[validUntil] | [usageRule] |

🚫 不可用优惠券/红包
| 序号 | 优惠券金额 | 券名称 | 有效期 | 使用规则 | 不可用原因 |
|------|------------|--------|--------|----------|------------|
| [sequence] | ¥[amount] | [name] | 至[validUntil] | [usageRule] | [unavailableReason] |

当前订单已选中：[当前选中优惠券.name；初次取 recommendCoupon，更换后取用户新选券；无券时显示“未使用优惠券”]。
如想更换，请告诉我可用优惠券的序号；如想维持原样，请回复「确认购买」。
```

- 每单只能选择一张 `available=true` 的优惠券；不可用券仅展示原因。
- 其他信息有变化：先重新调用确认接口；仅更换优惠券：不调用接口，始终以最近一次 `orderPrice.payPrice` 为基数计算新的页面“支付总价”：
  - `benefitType=INSTANT_DISCOUNT` 且 `affectsPayablePrice=true`：展示支付总价 = `max(0, orderPrice.payPrice - coupon.amount)`。
  - `benefitType=CASHBACK` 或 `affectsPayablePrice=false`：展示支付总价 = `orderPrice.payPrice`，只在价格明细展示 `¥[amount] [name]（出行后返现，不抵扣当前支付总价）`。
  - `benefitType=UNKNOWN`：不得自行扣减；按 `priceTip`/`description` 展示，无法确认是否影响支付总价时提示用户，展示支付总价固定为原始 `orderPrice.payPrice`。
- 换券后按同一模板完整刷新行程确认，仅替换优惠券项并重新计算页面支付总价；`ticketPrices[]` 和 `discountDetails[]` 必须保持不变，不得把优惠券写入或替换 `discountDetails[]`。
- 单独保存原始 `orderPrice.payPrice`，页面展示金额只作为派生值使用，不得覆盖该原始值；创建订单时读取原始值。
- 记录所选 `couponId`；国内和国际订单均在步骤 5 传入所选优惠券。

---

### 步骤 5：创建订单

⚠️ **只有收到用户明确的下单指令才能调用 `uni_order_create`**。用户必须回复「确认购买/确认下单/买」等明确下单指令；"嗯"/"好"/"可以"/"是的"不算下单指令，此时只能追问确认，不得直接创建订单。

#### 价格与优惠券参数

- `totalPrice` **始终传最近一次 `uni_query_flight_confirm` 返回的原始 `orderPrice.payPrice`**；不得传页面减券后展示的支付总价，也不得因更换优惠券修改此入参。
- 国内和国际订单选择优惠券时均传所选 `couponId`；优惠券是否影响页面展示金额，不影响下单 `totalPrice` 的取值。
- 未选优惠券时不传 `couponId`。
- 乘机人、航班、舱位或附加产品变化后，必须返回步骤 4 重新调用确认接口并更新支付总价，禁止沿用旧值。

#### 调用方式

```text
# 使用 cdids 下单（用户从已有乘机人列表中选择）
工具：uni_order_create
参数：{"priceId":"PRICE_XYZ","flightInfoId":"FI20260601BJS_SHA_001","orderSource":"domestic","contactName":"张三","contactPhoneCode":"86","contactPhone":"13800138000","totalPrice":560,"couponId":"COUPON_001","cdids":["cdid_001"]}

# 使用 passengers 下单（用户手动输入新乘客）
工具：uni_order_create
参数：{"priceId":"PRICE_XYZ","flightInfoId":"FI20260601BJS_SHA_001","orderSource":"domestic","contactName":"张三","contactPhoneCode":"86","contactPhone":"13800138000","totalPrice":580,"passengers":[{"name":"张三","idType":0,"idCard":"110101199001011234","phoneCode":"86","phone":"13800138000","type":"ADT","gender":"M"}]}
```

#### 输出模版

```text
下单成功！
订单号：[data.orderId]
航班：[航司名][flightNo] | [出发机场][departureTime] → [到达机场][arrivalTime]
日期：[date]
舱位：[舱位名称]
乘客：[name], ...
金额：¥[data.payPrice]（不含优惠券）

支付链接：[点击支付]([payUrl])


优惠券/红包请在支付环节使用，点击支付进入收银台即可选择。请及时完成支付，支付成功后正式出票。
```

#### 逻辑规则

- 下单成功后，提醒用户可通过查询订单详情查看支付状态；用户需要时再调用 `uni_order_query`。
- 下单失败按执行约束处理，展示错误原因并给出建议。


---

## 低价抢票流程

> 适用范围：低价抢票仅支持国内机票；国际及港澳台机票不支持低价抢票流程。

### 常见用户场景与参数选择

#### 场景 1：按航班号抢

适用场景：用户已经知道想抢哪一个或哪几个具体航班。

- 使用参数：`flightNos`
- 示例：`MU5137`、`CA1234,MU5101`
- 规则：
  - 用户明确给了航班号时，优先按航班号抢。
  - 已有 `flightNos` 时，通常不再追问起飞时段。
  - 若用户同时给了航班号和航司/时段，以 `flightNos` 为主要约束。

用户友好话术建议：

```text
如果您知道具体航班号，可以按指定航班抢票，例如 MU5137。
```

#### 场景 2：按起飞时段抢

适用场景：用户不知道具体航班号，但对出发时间有要求。

- 使用参数：`depTimeStart`、`depTimeEnd`
- 示例：`08:00` - `10:00`
- 规则：
  - 用户未指定航班号但指定了时间段时，按时段抢票。
  - 用户未指定航班号也未指定时间段时，时段默认 `depTimeStart=00:00`、`depTimeEnd=24:00`（即全天）。
  - 若用户还指定了航司，可额外传 `airlines`。
  - 不得把用户说的航司名称错误映射成 `flightNos`。

用户友好话术建议：

```text
如果您不知道航班号，也可以按起飞时间段抢票；如果有偏好的航司，也可以一起指定。
```

---

### 步骤 1：低价抢票填单

调用 `grab_low_confirm` 查询抢票方案。

#### 调用方式

```text
工具：grab_low_confirm
参数：{"depCode":"北京","arrCode":"上海","depDates":"2026-05-01","targetPrice":500,"cabinClass":"Y","depTimeStart":"00:00","depTimeEnd":"24:00"}
```

#### 输出模版

```text
✈️已生成低价抢票方案（以下价格默认按单个成人展示）：

抢票成功率: [successRate]
行程: [出发地] → [目的地] [日期]
费用明细: 票价 [priceDetail.ticketPrice] 元 + 税费/燃油费 [priceDetail.taxAndOilFee] 元 = 合计 [priceDetail.totalAmount] 元
抢票范围: 航班号 [flightNos 或 未指定] | 起飞时间段 [depTimeStart]-[depTimeEnd 或 全天] | 航司 [airlines 或 未指定]
价格参考: 历史最低价 [lowestPrice] 元 → 容易抢价格 [ryPrice] 元 → 推荐价格 [ygPrice] 元 → 当前最低价 [curPrice] 元

⚠️ 若用户目标价低于历史最低价，无法按该价格抢票，需请用户确认是否按推荐价格 [ygPrice] 元继续。

🛡️ 可选保险:
1. [name]，[price] 元，[title] | [保障详情]([noteurl])

如需继续为您计算准确总价，请补充乘机人信息，并确认以下内容（此阶段无需提供联系人手机号，将在创建订单时收集）：
- 您确认后的目标票价 `ticketPrice`（不能低于历史最低价；若低于则默认采用推荐价格）
- 乘机人信息：姓名、证件号；证件类型默认身份证，如使用护照、回乡证、军官证、港澳通行证、台胞证等其他证件类型，请一并说明
- 是否购买保险
```

#### 逻辑规则

- 城市传中文名时，用"北京""上海"这类城市名，不要传"北京市""上海市"。
- 调用成功后，必须从返回结果中提取 `flightInfo`；若未返回有效 `flightInfo`，停止后续下单流程并向用户说明。

---

### 步骤 2：低价抢票订单总价计算

用户确认乘机人、目标票价等信息后，调用 `grab_low_price_calculate` 计算订单总价。

#### 调用方式

```text
工具：grab_low_price_calculate
参数：{"ticketPrice":2680,"passengers":[{"name":"张三","idCard":"330xxxxxxxxxxxxx","idType":0}],"flightInfo":"ENCRYPTED_FLIGHT_INFO","insureCodes":"TA031#A031_HT_ZA_30"}
```

#### 输出模版

```text
✈️已为您完成低价抢票总价计算：

抢票成功率: [successRate]
订单总价: [totalPrice] 元

👥 乘机人费用明细：
- [passengerName]（[passengerType 中文名]）：目标票价 [ticketPrice] 元 + 税费/燃油费 [taxAndOilFee] 元 + 保险 [insurancePrice] 元 = 小计 [subtotal] 元
- [passengerName]（[passengerType 中文名]）：目标票价 [ticketPrice] 元 + 税费/燃油费 [taxAndOilFee] 元 + 保险 [insurancePrice] 元 = 小计 [subtotal] 元

说明：
- ADT = 成人，CHD = 儿童，INF = 婴儿
- 如未购买保险，保险金额显示为 0 元
- 后续创建订单时，必须使用本次总价计算返回的 `flightInfo`，不要再使用填单阶段返回的 `flightInfo`

如确认无误，可继续创建低价抢票订单。请补充并确认以下信息：
- 联系人手机号（必填）
- 停止抢票时间：默认起飞前 120 分钟停止抢票；如您有特殊需求，也可以告诉我希望提前多久停止抢票
```

#### 逻辑规则

- `flightInfo` 必须使用最近一次 `grab_low_confirm` 返回的 `flightInfo`（即填单阶段返回的透传参数）。
- `ticketPrice` 由用户确认，通常取自步骤 1 返回的价格信息，并允许在可选区间内调整后传入。
- 用户选择保险时，`insureCodes` 传步骤 1 返回保险产品的 `productId`；多个保险用逗号分隔。

---

### 步骤 3：订单信息确认

用户确认总价和手机号后、创建订单前，向用户展示完整订单信息供最终确认。

#### 输出模版

```text
请确认以下订单信息，确认无误后我将为您创建抢票订单：

✈️ 行程信息:
- 出发地: [depCode] → 目的地: [arrCode]
- 出发日期: [depDates]
- 航班号: [flightNos 或 未指定]
- 起飞时段: [depTimeStart]-[depTimeEnd 或 全天]
- 舱位: [cabinClass 中文名]

💰 价格信息:
- 目标票价: [ticketPrice] 元/人
- 订单总价: [totalPrice] 元

👥 乘机人:
- [passengerName]（[passengerType 中文名]）

联系人手机号: [contactPhone]
停止抢票时间: 起飞前 [beforeTime] 分钟
保险: [保险名称 及 价格 或 无]

请明确回复「确认抢票」，我再为您创建订单。如需修改请告知具体修改项。
```

#### 逻辑规则

- 本步骤不调用接口，仅汇总展示步骤 1、步骤 2 中用户已确认的所有信息。
- ⚠️ **联系人手机号校验**：`contactPhone` 必须是完整的合法手机号（11 位数字），禁止使用含 `*` 的脱敏号码；若用户提供的是脱敏号码，必须追问获取完整号码。
- **严格确认**：只有用户明确回复「确认抢票」且上下文唯一指向创建抢票订单动作时，才进入步骤 4 创建订单；「好 / 可以 / 嗯 / 行 / OK」等模糊回复不算确认，需再次提示用户明确回复「确认抢票」。
- 若用户提出修改，回到对应步骤重新处理后再次展示确认信息。

---

### 步骤 4：创建低价抢票订单

用户确认订单信息后，调用 `grab_low_create_order` 创建抢票订单。

#### 调用方式

```text
工具：grab_low_create_order
参数：{"flightInfo":"ENCRYPTED_FLIGHT_INFO_FROM_CALCULATE","passengers":[{"name":"张三","idCard":"330xxxxxxxxxxxxx","idType":0}],"contactPhone":"13800000000","ticketPrice":2680,"insureCodes":"TA031#A031_HT_ZA_30","beforeTime":-120,"successRate":"85%"}
```

#### 输出模版

```text
✅ 低价抢票订单已创建！

抢票订单号: [orderId]

[若 payurl 为空] ⚠️ 未获取到支付链接，订单创建失败，请稍后重试或前往航班管家App 处理。

支付链接：[点击支付]([payurl])


请及时完成支付。
```

#### 逻辑规则

- `flightInfo` 必须使用最近一次 `grab_low_price_calculate` 返回的 `flightInfo`（即总价计算阶段返回的透传参数）。



---

## 订单查询流程

用户表达「查订单/订单详情/支付状态」等意图时，进入订单查询流程。

### 查询订单列表

用户未指定具体订单号时，先调用 `uni_order_query` 查询订单列表。

#### 调用方式

```text
# 查全部订单
工具：uni_order_query
参数：{}

# 仅查国内订单
工具：uni_order_query
参数：{"orderSource":"domestic"}

# 查指定订单详情
工具：uni_order_query
参数：{"orderId":"D20260601001"}
```

#### 输出模版（列表）

**无订单**：

```text
暂无订单记录。
```

**有订单**：

```text
您的订单列表：

| 序号 | 订单号 | 类型 | 状态 | 航班 | 出发 → 到达 | 日期 | 金额 |
|------|--------|------|------|------|-------------|------|------|
| 1 | [orderId] | [国内/国际] | [状态] | [flightNo] | [出发城市] → [到达城市] | [date] | ¥[payPrice] |
| 2 | ... | | | | | | |

请告诉我您要查看哪个订单的详情？
```

#### 输出模版（详情）

```text
订单详情：
订单号：[orderId]
状态：[orderStatus]
航班：[航司名][flightNo] | [出发机场][departureTime] → [到达机场][arrivalTime] | [duration]
日期：[date]
舱位：[舱位名称]
金额：订单 ¥[payPrice]（不含优惠券）
[coupons 有值时逐项展示]优惠券：[coupons[].benefitType=CASHBACK 或 name 含“返现红包”时：coupons[].name（出行后返现）；否则：coupons[].name] ¥[coupons[].amount]（[coupons[].status]）

乘客：
[name] | [type] | [舱位] | [票状态] | ¥[ticketPrice]
证件：[idType] [idNoMask]

[orderDetailUrl 有值时]订单详情：[点击查看订单详情]([orderDetailUrl])

支付链接：[点击支付]([payUrl])


请及时完成支付。
```

#### 逻辑规则

- ⚠️ 订单详情返回的 `payUrl`/`payurl` 有值时，**必须**给用户展示支付链接，不得遗漏。
- 用户已指定订单号时跳过列表，直接查详情；未指定时展示列表供选择。
- `orderId` 前缀：D=国内，I=国际。
- `coupons[]` 有值时逐项展示优惠券；`benefitType=CASHBACK` 或券名含“返现红包”时，在名称后追加“（出行后返现）”，其他优惠券名称不追加。
- `orderDetailUrl` 有值时展示 `订单详情：[点击查看订单详情]([orderDetailUrl])`；为空或缺失时不展示，禁止编造链接。
- 待支付时展示支付入口。
- 证件号只用脱敏值展示。
- 最多展示 10 条；超出时先展示前 10 条，用户追问后再展示后续。

---

## 取消订单流程

用户表达「取消订单/不要了/取消这张票」等意图时，进入取消订单流程。

### 步骤 1：确认待取消订单

先查询订单详情并向用户二次确认。

```text
工具：uni_order_query
参数：{"orderId":"D20260601001"}
```

#### 输出模版

```text
确认取消这笔订单吗？

订单号：[orderId]
航班：[航司名][flightNo] | [出发机场][departureTime] → [到达机场][arrivalTime]
日期：[date]
乘客：[name], ...
金额：¥[totalPrice]
当前状态：[orderStatus]

⚠️ 取消后订单无法恢复，退款规则以航司政策为准。
请明确回复「确认取消」，我再继续。
```

### 步骤 2：执行取消

只有用户明确回复「确认取消 / 取消订单 / 确认」且上下文唯一指向取消动作时，才能调用 `uni_order_cancel`；「好 / 可以 / 嗯」不算确认。

#### 调用方式

```text
工具：uni_order_cancel
参数：{"orderId":"D20260601001"}
```

#### 输出模版

```text
订单已取消。
订单号：[orderId]
```

#### 逻辑规则

- 取消订单必须二次确认；已出票的订单提醒用户走退票流程。
- 取消失败按执行约束处理。
- 用户中途说「算了/不取消了/停」立即停止。

---

## 低价抢票订单流程

用户表达「查订单/订单详情/支付状态/抢到了吗/取消抢票/不抢了」等意图时，进入低价抢票订单流程。

### 步骤 1：低价抢票订单列表查询

用户未指定具体订单号时，先调用 `grab_low_order_list` 查询订单列表。

#### 调用方式

```text
工具：grab_low_order_list
参数：{"page":1,"num":10}
```

#### 输出模版

```text
您的抢票订单列表：

| 序号 | 订单号 | 航班号 | 行程 | 出发日期 | 预算 | 乘机人 | 状态 | 创建时间 |
|------|--------|--------|------|----------|----------|--------|------|----------|
| 1 | [orderId] | [flightNo] | [depName]→[arrName] | [depDate] | [ticketPrice] 元 | [passengers[].name] | [status] | [createTime] |
| ... | | | | | | | | |

请告诉我您要查看哪个订单的详情？
```

#### 逻辑规则

- `status` 接口直接返回中文名（如"待支付"），原样展示。
- 用户已指定订单号时跳过列表，直接查详情；未指定时展示列表供选择。
- 默认 `page=1`、`num=10`；列表为空时提示「暂无抢票订单记录」。
- 最多展示 10 条；超出时先展示前 10 条，用户追问后再展示后续。

---

### 步骤 2：查询低价抢票订单详情

优先使用本轮 `grab_low_create_order` 返回的 `orderId`；没有订单号时先调用 `grab_low_order_list` 让用户选择。

#### 调用方式

```text
工具：grab_low_order_detail
参数：{"orderId":"GRAB202605010001"}
```

#### 输出模版

```text
抢票订单详情：

状态: [statusDesc]
订单号: [orderId]
计划行程: [grabTask.trip]
预算：[ticketTotalPrice]
指定日期: [grabTask.flightDate]
抢票时段/指定航班: [grabTask.depTime]
出发到达：[grabTask.depName]-[grabTask.arrName]
抢票舱位：[grabTask.cabin]
抢票截止时间：[grabTask.beforeTime]

乘机人:
- [passengers[].name] | [passengers[].cardName] [passengers[].cardNo 脱敏]
联系人: [contactPhone]

费用明细:
- [priceList[].type 中文名]: 票价 [priceList[].ticketPrice] 元 + 税费 [priceList[].tax] 元 + 燃油 [priceList[].oilFee] 元 = [priceList[].totalPrice] 元/人
- 订单总价: [orderPrice] 元

支付链接：[点击支付]([payurl])

```

#### 逻辑规则

- ⚠️ 订单详情返回的 `payUrl`/`payurl` 有值时，**必须**给用户展示支付链接，不得遗漏。
- `statusDesc` 为状态中文描述（如"待支付"），直接展示；展示支付入口仅限 `status == 11`（待支付）且 `payurl` 有值时。
- 乘机人逐行展示，`cardNo` 必须脱敏：保留前 4 位和后 3 位，中间用 `*` 替代，如 `2312*********031`。
- 缺失字段省略，不编造。

---

### 步骤 3：取消抢票订单

用户表达「取消抢票/停止抢票/不抢了」时，先查订单详情并二次确认，确认后调用 `grab_low_cancel`。

#### 确认待取消订单

```text
工具：grab_low_order_detail
参数：{"orderId":"GRAB202605010001"}
```

向用户展示抢票订单关键信息：

```text
⚠️ 确认取消以下抢票订单？

订单号: [orderId]
行程: [grabTask.trip] | [grabTask.flightDate] | [grabTask.depTime]
乘机人: [passengers[].name]
费用: [orderPrice] 元
状态: [statusDesc]

请明确回复「确认取消抢票」，我再继续。
```

#### 确认后取消

只有用户明确回复「确认取消抢票 / 取消抢票 / 确认」且上下文唯一指向取消抢票动作时，才能调用 `grab_low_cancel`；「好 / 可以 / 嗯」不算确认。

```text
工具：grab_low_cancel
参数：{"orderId":"GRAB202605010001"}
```

##### 输出模版

```text
抢票已取消。
订单号: [orderId]
[alterMsg 非空时] ⚠️ [alterMsg]
```

#### 逻辑规则

- `alterMsg` 非空时必须弹窗提示用户，原样展示内容。
- 取消失败按执行约束处理；用户中途说「算了/不取消了/停」立即停止。

---
