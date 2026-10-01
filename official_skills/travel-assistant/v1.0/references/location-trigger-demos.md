# 地点 Event Trigger：可复用 Demo

用户说「到了某地再做某事」时，先创建或复用对应 Thing/Todo；纯地点监测 Todo 的
`schedule_info` 为 `{ "kind": "MONITOR" }`。使用实际加载的 `make-things v1.2`：
`type=event`、`event.source_id=yb_geo_location`、顶层 `prompt`、可选 `judge`。
本 Skill 已绑定的地理位置 Connector 的 Judge 工具写
`geo-location/get_last_known_location`，`tool_arguments={}`；创建前以运行时注入的完整工具名核对。

以下 JSON 是**创建 Trigger 的参数模板**，不是已创建的规则。用真实 Thing/Todo ID 替换占位符；
在 Todo 中写清用户要的内容、目标地点、有效期和已提醒收据。先建停用 Event Trigger，
把返回的 `trigger_id` 写进 Todo.`rule_ids`，重读核对后再启用；Event 不使用 `bind_and_enable=true`。
同一 Todo、同一地点已有有效规则时更新，不叠加。没有有效期或可靠地点证据时先补齐，
不要启用没有业务有效期的定位提醒。本类到达通知只创建 Event + Judge，不为截止时刻
另建 Schedule。把截止时刻保存在 Todo，Event 命中后的回调先检查是否过期；当前 Event
没有原生截止字段，若始终没有地点命中，规则不会仅因到期而自动停用，不能承诺自动清理。

`get_last_known_location` 返回**缓存**坐标、位置描述、城市编码、`is_cached` 与
`collected_at_ms`。Event payload 不会自动填进 `tool_arguments`。Judge 仅筛选目标地点候选，
不在 `condition` 中检查采集时间或做缓存防抖；这部分由下游处理。
顶层 `prompt` 触发后重读 Todo，再用 `get_last_known_location` 复核地点；后台不调用会向设备请求实时坐标的 `get_geo_location`，再决定是否 `show_widget`。
未确认、定位失败、跨行政区边界或用户已取消时保持静默。只有 `show_widget` 返回真实
`now_id` 才记「已提醒」并停用规则；结果不确定不重发，提醒发出也不等于用户已完成 Todo。

## Demo 1：到北京推荐吃的

北京是**城市级**目标。用户要的是吃什么、去哪吃：命中后按用户**最近一次可核实的缓存位置**调用
`find_nearby`，只推荐真实回包里的一家餐厅，或用有来源的当地美食资料介绍一种食物；
一个对象一张可点击回原会话的 `image_text`，整卡 `tap={"type":1,"agent_chat":{}}`；不能编店名、评分或人均。
如果同一趟旅行已经有「抵达北京快览」Event，就把用户指定的美食要求写进已有 Todo/Trigger，
只保留一条北京市到达规则；先前已发过同一美食对象时不再发。

```json
{
  "thing_id": "<真实 Thing ID>",
  "todo_id": "<真实 Todo ID>",
  "title": "到北京后推荐吃的",
  "type": "event",
  "event": {"source_id": "yb_geo_location"},
  "judge": {
    "tool_call": {"tool_name": "geo-location/get_last_known_location", "tool_arguments": {}},
    "condition": "定位结果有有效坐标，位置描述或城市编码明确为北京市时才作为候选；环京城市或城市不明不命中。"
  },
  "prompt": "重读 Thing、Todo 与规则；已提醒、取消或过期就停用结束。调用 geo-location/get_last_known_location 读取缓存位置，确认仍指向北京市；无法确认就不发卡，不调用实时定位。以本次缓存坐标调用 travel_assistant 的 find_nearby，kind=dining，只选一家真实餐厅，或从可信资料选一种北京食物，发一张点击回原会话的 image_text，整卡 tap={\"type\":1,\"agent_chat\":{}}，标题点名对象、摘要不超过40字；无结果不编造。只在收到 now_id 后记该对象已提醒并停用规则，未决不重发。"
}
```

## Demo 2：到赛里木湖讲人文

赛里木湖是**具体景区**，不能把「到了博乐市」或「到了博州」当作已经到湖边。
创建时先核实目标景区的坐标或边界，并在 Todo 中保存来源；不能用城市中心替代。
人文内容也要先有可信来源，例如景区官方介绍或经核实的行程材料，卡片只放一条简短内容。

```json
{
  "thing_id": "<真实 Thing ID>",
  "todo_id": "<真实 Todo ID>",
  "title": "到赛里木湖后讲一条人文看点",
  "type": "event",
  "event": {"source_id": "yb_geo_location"},
  "judge": {
    "tool_call": {"tool_name": "geo-location/get_last_known_location", "tool_arguments": {}},
    "condition": "定位结果有有效坐标，位置描述明确指向赛里木湖景区，且坐标符合 Todo 中已核实的景区范围时才作候选；只在博乐市或博州、景区归属不明时不命中。"
  },
  "prompt": "重读 Thing、Todo 与景区范围；已提醒、取消或过期就停用结束。调用 geo-location/get_last_known_location 读取缓存位置并按已核实的景区范围复核，不调用实时定位；无法确认在赛里木湖就不发卡。用 Todo 中有来源的人文材料写一条简短提示，发无图 image_text；资料缺失不编造。仅收到 now_id 才记已提醒并停用，未决不重发。"
}
```

## Demo 3：进入深圳南山区提醒吃肠粉

南山区是**行政区**，不是一个 POI 点。不能用「距南山区中心几公里」判断；宝安区与
南山区接壤，误差覆盖区界时一律不提醒。

```json
{
  "thing_id": "<真实 Thing ID>",
  "todo_id": "<真实 Todo ID>",
  "title": "进入深圳南山区后提醒吃肠粉",
  "type": "event",
  "event": {"source_id": "yb_geo_location"},
  "judge": {
    "tool_call": {"tool_name": "geo-location/get_last_known_location", "tool_arguments": {}},
    "condition": "定位结果有有效坐标，位置描述明确指向深圳市南山区时才作候选；宝安区或区名不明不命中；取数失败属于错误，不能当作到达。"
  },
  "prompt": "重读 Thing、Todo 和规则；已提醒、暂停、取消或过期就停用结束。调用 geo-location/get_last_known_location 读取缓存位置并核验行政区与可用精度信息，不调用实时定位；只有确认位于深圳市南山区且能排除区界误判时，才用 show_widget 发无图 image_text 提醒吃肠粉。宝安、区界不明或取数失败不发卡。仅收到 now_id 才记已提醒并停用规则；未决不重发，Todo 不自动标完成。"
}
```

## Demo 4：到漾日湾畔后推天气和附近正餐

用户说「到了漾日湾畔，把未来两小时天气和附近吃的发到此刻」，随后补充「只看正餐」。
这是**一条到达 Event、两项 NOW 交付**：创建 Todo 时分别写明「天气卡待发、正餐卡待发」；
补充条件到来时更新原 Todo 和 Event 顶层 `prompt`，不要只在会话里答应，也不要另建地点 Event。
下面仅示范 Event 的发卡指令；目标位置和截止时刻仍按前述流程核实并写入 Todo。

```json
{
  "thing_id": "<真实 Thing ID>",
  "todo_id": "<真实 Todo ID>",
  "title": "到漾日湾畔后发天气和附近正餐",
  "type": "event",
  "event": {"source_id": "yb_geo_location"},
  "judge": {
    "tool_call": {"tool_name": "geo-location/get_last_known_location", "tool_arguments": {}},
    "condition": "缓存定位有有效坐标，且能可靠确认位于 Todo 中核实的漾日湾畔目标范围时才作为候选；边界或精度不明不命中。"
  },
  "prompt": "重读 Thing、Todo 和规则；取消、过期或无法复核抵达时不发卡，不调用实时定位。确认到达后，按最新的‘只看正餐’要求逐项交付：①查当时及未来两小时天气，若天气收据为空，用 show_widget 发一张 image_text 天气卡，拿到真实 now_id 后重读 Thing 并回写天气收据；②以本次缓存坐标调用 find_nearby kind=dining，筛出 3–5 家真实正餐，若正餐收据为空，用 show_widget 另发一张 recommend_list 正餐卡，拿到真实 now_id 后重读 Thing 并回写正餐收据。条目不足或取数失败按本 Skill 降级，不编造；已发的那项不重发，未发的那项不记为已发，结果未决先核查。两项处理并核对收据后再停用本 Event；会话文字不代替任何一张卡。"
}
```

天气卡的 `card_type` 为 `image_text`、`data={}`；正餐卡有 3–5 家真实结果时，
`card_type` 为 `recommend_list`、`data.items` 每行一家，配置 `items[].tap` 回原会话，
不配整卡 `tap`。两张卡各有独立 `now_id`；只发天气就写「天气已发、正餐待发」，不能写「天气与餐厅已发」。
若正餐数据不足或查询失败，按 [scenarios.md](scenarios.md) 和 [data-sources.md](data-sources.md)
单独降级，不拿旧查询结果凑数。

**当前能力边界**：已绑定的缓存定位工具公开描述没有保证结构化区名、定位精度或景区边界。
这些 demo 采用「无法核实就不发」的口径，能避免误报，但可能漏报。
如需稳定覆盖整个南山区或赛里木湖景区，还要接入可信的行政区/景区范围与精度核验能力；
只改 `tool_name` 不能补出这些数据。

## 在 Skill Playground 里体验

下面的话由测试用户输入；模型应按上面的对应 Demo 建 Todo 与 Event Trigger，**创建轮不发 NOW 卡**。
要验证命中与发卡，还需测试环境投递 `yb_geo_location` 事件并提供对应设备定位；
单纯说「我已经到了」不能当成真实定位事件。

| 测试 Prompt | 应观察到的行为 |
| --- | --- |
| 「这次去北京，到了北京市就按我当时的位置推荐附近好吃的，只提醒一次，返程当天结束。」 | 创建城市级 Event 规则；不把天津、廊坊当作到北京；即使 Judge 命中，发卡前仍需用缓存位置复核并取真实餐厅，不补编评分。缺返程日期时先补齐。 |
| 「到了赛里木湖景区，给我讲一条有出处的人文看点，只发一次，这次旅行结束就停止。」 | 先核实景区范围与人文资料；Event 命中后确认人在景区再发简短卡；只到博乐市不发。缺行程结束日期时先补齐。 |
| 「今天从宝安去南山，进入深圳南山区时提醒我吃肠粉，今晚 22 点后就不用提醒了。」 | 创建行政区 Event 规则；宝安区和南宝交界无法核实时不发；只有南山区得到可靠复核后发一次卡并停用。 |
| 「今天到漾日湾畔后，把未来两小时天气和附近吃的发到此刻，今晚 18 点结束。」随后说「只看正餐」。 | 更新原 Todo/Event 的正餐筛选；到达回调分别发天气 `image_text` 与正餐 `recommend_list`（有 3–5 家真实结果时），各记一个 `now_id`；只发一张不能声称两项都已投递。 |
