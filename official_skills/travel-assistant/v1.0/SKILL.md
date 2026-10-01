---
name: travel_assistant
description: "用户要安排或跟踪出行、临时出门、已有旅行当天活动时使用本出行助手；例如「安排一个行程」「今晚出去玩」「明天赶飞机」「到了目的地通知我」「进入某个区提醒我办事」「快到酒店提醒取快递」「在我附近找好吃的」「等我到广州给我找吃的」。也用于机票、火车票、酒店查询与预订，吃喝玩乐、电影演出、天气路况、出门时间、按城市/行政区/景区到达或具体地点距离提醒，以及确定行程目的地后在抵达城市或景区时通过 NOW 卡推荐介绍与游览建议。用户问附近时先取实时位置。只有从零制定多日攻略才改用 travel_plan。"
---

# 出行助手

确定出行 Todo，配置 Trigger 的取数与指令，并在规则到点时组装 NOW 卡片。事项与发卡都靠
`make-things`，**它不会自动挂上来，要自己加载**（见下一节）。不要重建 Thing 工具或发布通道。

覆盖查票订票、单次通勤、跨城出差、接送、本地活动和多日旅行。根据用户输入判断出行形态。

## 只查票、订票

用户只想查或订机票、火车票、酒店（「订明天去北京的机票」「周五回天津有什么高铁」）时，
**不建 Todo、不建规则、不加载 `make-things`**，走完这三步就结束：

1. 调同程 Connector：`<PKG>/flight_search` / `<PKG>/train_search` / `<PKG>/hotel_search`，
   把用户说的出发地、目的地、日期、人数、舱等原样带上。
2. 按用户条件挑 1–2 班车次或航班（酒店挑 1 家）。机票、火车票可用 `show_panel.tickets` 展示，
   **只传真实识别码** `{kind:"flight"或"train",no,date,depCity,arrCity}`，由脚本回同程查齐。
   航班必须有用户提供或查询结果中的真实航班号；缺航班号时省略航班块，不画待定航班卡。
   酒店的查询、预订能力仍保留，结果在回复正文说明并给真实落地链接；不放入这张 XCard。见 [tools.md](references/tools.md)。
3. 正文一两句说为什么推荐这个，不复述卡片。

用户接着交代了「到时候提醒我 X」这类跟进的事，再按下面的执行核心流程建 Todo 和规则。
**用户明确这是自己要乘坐的航班或高铁，且已知班次、日期、上车站/出发机场和计划出发时刻时，主动建一条行前信息 Todo 和一次性提醒规则**；
即使用户没有另说「提醒我」，也在出发前给他核对登机/检票信息。仅查询或比较班次、尚未确定乘坐哪班时不建。
缺少能确定触发时刻的日期或出发时刻，先按班次与实际出发站核实；仍不确定就问用户，不启用猜出的规则。
详见 [trigger-instruction.md](references/trigger-instruction.md)「已知航班或高铁的行前信息」。

## 第一步：加载 make-things（只查票订票可跳过）

**本 skill 自己没有任何写事项、发卡片的能力，全部来自 `make-things`。所以动手之前先加载它：**

```text
load_skill(skill_name="make-things")
```

这一步不能省，也不要等到要发卡时才想起来——`show_widget`、`create_thing`、`write_todos`、
`trigger/create_trigger`、`trigger/update_trigger` 都是它带进来的，没加载就一个都调不到。
本轮已经加载过就不重复加载。

只有 `make-things` 确实不在可用技能列表里（`load_skill` 明确报错），才在回复中说明
发布通道不可用并结束。**不要因为「函数工具列表里暂时没看到」就下这个结论——那说明你还没加载。**

## 区分工具类型

直接调用以下函数工具，不要通过 bash 调用：`show_widget`（发布卡片）、`create_thing` / `get_thing` / `write_todos` /
`trigger/create_trigger` / `trigger/update_trigger`（加载 `make-things` 后才有）、
`picture_search`（搜图，见 [card-media.md](references/card-media.md)）、
`<PKG>/get_geo_location` / `geo-location/get_last_known_location`（「地理位置获取」Connector，见下节）、
`<PKG>/flight_search` / `<PKG>/flight_detail` / `<PKG>/train_search` / `<PKG>/hotel_search`（「同程」Connector）。

实时定位和同程 Connector 按运行时注入的 `<PKG>/...` 名称调用；
地点 Trigger 的缓存定位按已绑定工具名 `geo-location/get_last_known_location` 调用。
`make-things` 那组工具不带包名前缀。Connector 要在 Playground 上绑给本 skill 才注入，没绑就按
[data-sources.md](references/data-sources.md) 降级——不要用 bash 找替代，也不要 `tool_search` 捞同名工具。

通过 bash 调用本包工具（一律用探测出的 `run_tool`，**不要写死包名**——
沙箱目录名不保证是 `travel_assistant`，实测出现过 `travel-assistant`）：`show_panel`、`check_ticket`、`get_trip_context`、`check_weather`、`check_route_eta`、
`find_nearby`、`get_place_media`、`check_proximity`、`plan_geofence`、`prepare_landing`、`prepare_card`。

`show_panel` 走 bash、`show_widget` 是函数工具——名字像，通道完全不同，见下面「两个展示通道」。
按下文探测入口，不要把 stdout 写入用户回复。
`show_panel` 必须通过 `app` 入口调用，只有这个入口会把脚本返回值交给对话 XCard。
若 `app` 不存在或调用失败，视为卡片未展示；在会话正文交付信息，不要改用
`python3 scripts/show_panel.py`，也不要把「面板已展示」文字回执当成发卡成功。

函数工具不在 bash 里，`command -v show_widget` 查不到、`app <pkg> show_widget` 返回 `UNKNOWN_TOOL`
都属正常，不要据此判断它不可用，也不要用这两种方式验证它存在。要确认就看上面那步
`load_skill make-things` 的回执。不要用 bash 模拟发布，也不要改用别的工具凑一张卡。

将 `prepare_card` 用作本地预校验，而非固定发布步骤。仅在 `show_widget` 拒绝卡片或使用不熟悉的卡型时运行。

## 位置：当前查询与到达触发

**当前会话要用用户此刻的位置**（例如「我在哪」「附近有什么」「离机场多远」）时，
调用已绑定的「地理位置获取」Connector `<PKG>/get_geo_location` 实时采集。
`<PKG>` 使用下文「执行核心流程」第 1 步探测得到的包名；工具未注入就按 [data-sources.md](references/data-sources.md) 降级，
不要猜工具名。`precise` 保持默认值 `false`；设备后台、离线或拒绝授权时可能取不到位置，
不要换参数反复请求。取到 lat/lng 后，搜周边用本包 `find_nearby`（`near` 传 `"lat,lng"`），
算到具体地点的距离用 `check_proximity`；不要心算距离。**取不到时在会话里说明无法获取实时位置**，
请用户提供城市或附近地标后再继续；不能把上次坐标、行程目的地或酒店当作用户此刻的位置。
若只根据行程城市给建议，要明确说是该城市的建议，不能称为「您附近」。

**Trigger 等待用户到达**时不主动向设备请求实时定位。城市、行政区或景区到达用
`type=event`、`event.source_id=yb_geo_location`，Judge 调用
`geo-location/get_last_known_location` 读取缓存位置；命中后的回调仍用它复核。
地点归属不明、取数失败或精度不足时不发到达卡，也不把目的地当作当前位置。
创建时写完整地点 Todo 和一条到达 Event + Judge，按下文「地点到达 Todo 与 Trigger」执行；
实例见 [location-trigger-demos.md](references/location-trigger-demos.md) 和
[destination-arrival-demos.md](references/destination-arrival-demos.md)。

「快到酒店／机场」等**具体地点距离提醒**按 [trigger-instruction.md](references/trigger-instruction.md)
用 `plan_geofence` 生成围栏条件，不用 Timer 反复投递。地点查询只传真实城市、区名或坐标，
不用「【用户当前位置】」这样的占位文本。

## 两个展示通道，别混

| | `show_panel` | `show_widget` |
| --- | --- | --- |
| 在哪 | 当前这一轮的**对话里** | **NOW 信息流** |
| 谁触发 | 你这一轮直接调 | Trigger 到点或事件命中后投递 |
| 用途 | 把要讲的内容排好版，替代堆 markdown | 「到点了、有变化了」的推送 |

**Trigger 承诺的关键通知必须进「此刻」。** 用户要求「到时提醒／到了通知／给我推送」的内容，以及规则命中后需要用户及时关注的重要变化，是 Trigger 的交付结果。创建时就在顶层 `prompt` 写明：条件确认后取当时的数据，调用 `show_widget` 发布 NOW 卡；不能只在 session 里回复，`show_panel` 也不能代替这张卡。到乌鲁木齐后通知当地天气，就在确认抵达的回调中查乌鲁木齐天气并发天气摘要卡。普通执行记录、无变化、无法确认命中、取消或到期不因回调发生就发卡；会话文字可补充已发布的通知。`show_widget` 发布到「此刻」不等于系统 Push 送达。

**同一 Trigger 承诺多个不同结果时，按承诺逐项投递。** 例如「到了后把天气和附近正餐发到此刻」，是天气通知与餐厅推荐两项，不因共用一个 Todo/Event 就合成一张卡：天气用 `image_text`，有 3–5 家真实正餐时推荐用 `recommend_list`；各调用一次 `show_widget`、分别记录 `now_id`。不足 3 家或取数失败按各自降级规则处理；未投递的内容不能记作已发，也不能只放在会话正文。触发前用户补充「只看正餐」等条件时，同步更新已有 Todo 与 Event 的顶层 `prompt`。见 [地点 Trigger Demo](references/location-trigger-demos.md)。

**普通对话轮有机票、火车票、天气或打车时间时才用 `show_panel`**。它纯展示、不写任何数据，和 NOW 完全解耦；Trigger 承诺的天气通知走 `show_widget`。
美食、景点推荐、演出、酒店、行程和选择仍由本 Skill 正常处理，
但这些内容不在对话 XCard 中渲染，改在回复正文或适用的 NOW 卡中表达。
所以「创建轮不发 NOW 卡」这条不限制它。调用方式与字段见 [tools.md](references/tools.md)。

调完不要在回复里复述面板内容，用户已经看见了。

## 卡片发在哪一轮

**先读这一节再动手。** 卡片通常由规则到点或事件命中后投递、在那一次执行里发。

**普通创建轮不发卡。** 这一轮把安排、候选、结论写进**回复正文**，把待办和规则建好。
创建时拿到的路况、天气到触发时已过期，应到点重新查。目的地到达推荐若在这一轮
已经可靠确认用户身处目标地点，可以立即交付，具体条件见下文。

三条硬规则：

- 创建轮不调 `show_widget`。例外是用户明确说了「发到 NOW」「发张卡」，或确定行程目的地时用缓存定位可靠确认**用户此刻已抵达**，可以直接交付下文的目的地到达推荐；同一目的地不再建待触发 Event。
- 要问用户就**在会话里问**，不要把 `todo_choice` 发到 NOW。选择卡留给触发轮用。
- 创建轮的说明在对话里；Trigger 承诺的提醒或通知在回调命中时用 `show_widget` 送到「此刻」。

## 执行核心流程

将「安排一下」「排一个」「帮我盯着」视为明确委托，直接创建 Todo 与规则，并在回复里把安排说清楚。

**「到 / 快到 <地点>，提醒我 <某事>」也是明确委托**。城市、行政区、景区的**到达**用下方的
`yb_geo_location` Event + Judge；「快到酒店」「路过公司楼下」等具体 POI 的**距离**用
[trigger-instruction.md](references/trigger-instruction.md) 的地理围栏。提醒内容用用户说的那件事。

**用户确认这次行程要去的城市或核心景区**，即使没说「到了提醒」，也可准备到达快览；
普通途经景点不逐个建到达规则。
进入新城市可分别介绍城市、推荐一种当地美食、推荐一个已核实的景点；
到具体景区可介绍该景区的一条游览建议。**一个具体对象一张 `show_widget image_text`**：
城市、美食和景点分别发卡，不把它们塞进同一张卡或 `recommend_list`。
默认同一趟旅行**每天主动到达快览最多 3 张，其中景点最多 1 张**；
只选用户明确重视或行程中已确认的核心景点，不为每个普通途经景点建到达规则。
城市、美食、景点内容不足，或已在当天行程卡、对话正文中讲过同一对象与建议，
就少发，不能凑数。到达后查到新的附近餐厅或当下注意事项，才算新的投递价值。
每张标题点名对象，摘要只写一条完整建议（不超过 40 个汉字），可放真实封面图；
**每张推荐卡都配置整卡 `tap={"type":1,"agent_chat":{}}`，点击回到原会话且不自动发送消息**；
不配置无落地内容的详情按钮。卡片自身仍须把推荐说完整。
「北京有什么好玩的」「北京和成都选哪个」、只查票或尚未确定目的地，均不视为确定行程。
若当前缓存定位已可靠确认抵达，直接按下文发一次卡并记录收据；否则创建记录截止时刻的
`yb_geo_location` Event + Judge，等后续位置事件命中。不能把用户说的目的地或购票终点当作当前位置。
同一次旅行同一目的地只创建一条到达监测；已有显式地点推荐时合并进现有 Todo/Event。
按「城市介绍 / 具体美食 / 具体景点」分别记录
`now_id`；同一对象已发或已有相同到达提醒时复用或略过。同一天后续进入已规划的景区时，
只有用户明确点名或它是当天尚未介绍的核心景点时，才为该景区另建到达 Event；
若此前已经介绍过同一景点，或当天景点卡名额已用完，就不重复发。
`make-things v1.2` 不对所有 Thing 统一限制一天一张；同一次交付仍不能重复发同一内容。
这组不同对象快览复用旅行 Thing，对每个对象只发一次，不另造 Thing。
多日行程的**每日总览**仍一天一张；已发的具体美食或景点也不因到达规则再次投递。
完整的 Thing/Todo、Event、回写与 `show_widget` 参数直接见
[destination-arrival-demos.md](references/destination-arrival-demos.md)。Web Search 仅用于有来源的景区介绍、
游览建议及近期注意事项，提炼一条卡上能独立读完的建议，不转贴长文；
不用来补票务、天气、评分等结构化字段；无可用搜索能力或无法核实近期信息时省略该提示。

### 地点到达 Todo 与 Trigger：创建时直接套用

用户说「到某个城市、行政区或景区时提醒我做某事」。**创建 Todo 时就写清完整目标地点与级别、
用户要求的动作、绝对截止时刻、判断方式和发卡动作**。`yb_geo_location` 仅表示收到了位置事件，
不等于用户已经到达；不能只建 `event`，再把“判断是否到达”留给 `prompt`。下面是
`make-things v1.2` 的完整参数模板。所有 `<…>` 都须在工具调用前换成用户的真实目标、时刻和返回的 ID，
不得把占位符写进 Todo 或 Trigger。示例以没有对应 Thing 为前提；已有旅行 Thing 时复用它，
只在其下新增 Todo。缓存定位的防抖由下游处理，`judge.condition` 不检查采集时间：

1. `create_thing`：地点提醒作为监测型 Todo 保存，别把「监控中」当作无限期许可。

```json
{
  "title": "到<完整目标地点>时<用户要求的动作>",
  "goal": "仅在核实用户进入<完整目标地点>后、且未过<绝对截止时刻>时执行<用户要求的动作>一次。",
  "todos": [{
    "title": "到<完整目标地点>时<用户要求的动作>",
    "schedule_info": {"kind": "MONITOR"},
    "description": "目标：<完整目标地点及城市/行政区/景区级别>；有效期：<带时区的绝对截止时刻>前；动作：<用户原话中的提醒或推荐>。位置事件由 yb_geo_location 提供，用 geo-location/get_last_known_location 做地点候选判断；命中后仍只用该缓存定位工具复核目标归属，不能调用实时定位。无法确认到达就不发卡；确认后按动作发一次对应 NOW 卡，记录 now_id 并停用规则。进展：待触发。"
  }]
}
```

2. `trigger/create_trigger`：用刚返回的真实 ID 创建**停用状态**的 Event + Judge。`judge` 必须在
   创建参数里，且只放 `tool_call` 与 `condition`；执行指令放顶层 `prompt`。`condition` 不命中时
   不投递 `prompt`；本类到达通知不额外创建截止 Schedule。

```json
{
  "thing_id": "<真实 Thing ID>",
  "todo_id": "<真实 Todo ID>",
  "title": "到<完整目标地点>后<用户要求的动作>",
  "type": "event",
  "event": {"source_id": "yb_geo_location"},
  "judge": {
    "tool_call": {
      "tool_name": "geo-location/get_last_known_location",
      "tool_arguments": {}
    },
    "condition": "定位结果有有效坐标，且有足够证据指向<完整目标地点>时才作为候选：城市级核对城市编码或描述，区级核对明确的区级归属，景区级核对已核实的景区范围；相邻地区、边界或精度不明、取数失败均不命中。"
  },
  "prompt": "重读 Thing、Todo 和规则，按 Todo 中的完整地点、级别、动作和绝对截止时刻执行；已提醒、取消或过期就停用，不发卡。调用 geo-location/get_last_known_location 读取缓存位置并复核目标归属，不调用 get_geo_location；区界、景区范围或精度无法判清就不发卡。确认到达后按 Todo 动作取必要数据：纯到达提醒发一张 image_text；用户明确要比较 3–5 个地点时才用 recommend_list；目的地美食、景点快览按本 Skill 的一物一卡规则分别发可点击回原会话的 image_text，整卡 tap={\"type\":1,\"agent_chat\":{}}，并分别记录真实 now_id。结果不明不重发；终态停用 Event，提醒不等于 Todo 已完成。"
}
```

3. `write_todos`：按最新 Thing 版本更新同一 Todo，保留上面的完整 `description` 与
   `schedule_info={"kind":"MONITOR"}`，只把 Event 返回的**一个真实 `trigger_id`**写入
   `rule_ids`；回读核对成功后，才 `trigger/update_trigger(enabled=true)`。
   没有可确定的截止时刻就先问用户。当前 Event 无原生截止字段；若截止前始终没有地点命中，
   规则不会仅因时间到达而自动停用，不要承诺这一点。地点命中后的回调会检查是否已过期并停用。

代入示例：用户说「今天从深圳去广州，到了广州通知我，今晚 22 点结束」，则目标是**广州市（城市级）**，
动作是到达通知，截止为当天 22:00 的绝对时刻。换成其他地点时，Todo、Judge 和 `prompt` 都用新的
完整目标与动作，不能沿用示例地名。北京美食、赛里木湖人文、南山区肠粉的具体条件见
[location-trigger-demos.md](references/location-trigger-demos.md)；区级和景区位置不明确时保持静默。

**已确定本人要乘坐的航班号或高铁车次**也要创建行前信息 Todo：航班默认起飞前 2 小时、
高铁默认从用户上车站发车前 1 小时，按当地时区创建一次性 Timer。触发轮重新核对班次并发 `show_widget`；
座位、车厢、检票口、站台或登机口仅在用户票据或可信的实际回包明确给出时展示。
同程票务搜索的「二等座有票」不是用户的座次，也不能据航班号推断登机口。
具体字段、缺失处理和卡片样例见 [trigger-instruction.md](references/trigger-instruction.md)。

信息不足时只询问当前流程必需的一项，例如城市、日期或人数；获得答案后继续执行。

0. 还没加载 `make-things` 就先加载（见开头「第一步」）。

1. 在同一轮中探测入口、读取行程并获取可并行的数据：

```bash
PKG=""
for d in /data/skills/*/scripts/get_place_media.py /data/skills/*/scripts/prepare_card.py; do
  [ -f "$d" ] || continue
  PKG=$(basename "$(dirname "$(dirname "$d")")"); break
done
[ -n "$PKG" ] || { echo "TRAVEL_ASSISTANT_NOT_FOUND"; exit 1; }
echo "PKG=$PKG"
command -v app >/dev/null && MODE=APP || MODE=DIRECT
run_tool() {
  if [ "$MODE" = APP ]; then app "$PKG" "$1" "$2"
  elif [ "$1" = show_panel ]; then echo '{"code":"CARD_CHANNEL_UNAVAILABLE","message":"show_panel 需要 app 入口"}'; return 1
  else python3 "/data/skills/$PKG/scripts/$1.py" "$2"; fi
}
run_tool get_trip_context '{}'
run_tool check_weather '{"city":"深圳"}'
```

2. 为卡片中的真实地点或实体获取图片。默认调用 `picture_search`：

```json
{"query": ["深圳石洲中路夜市", "深圳学府路小吃街", "成都武侯祠"]}
```

在 query 中提供城市和完整名称。原样使用回包中的 URL，不要改写、截断或补全协议。

- 查询同程收录的景区或酒店时优先调用 `get_place_media`。
- 仅为不存在真实照片的内容调用 `image_generation`。
- 按 [card-media.md](references/card-media.md) 处理图片来源和降级。

3. 为需要跳转的真实地点调用 `prepare_landing`。**按地点类型选 `kind`，不要一律用 `map`：**

| 地点类型 | `kind` | 落到哪 |
| --- | --- | --- |
| 景区、公园、博物馆、古镇 | `scenery` | 同程景点详情（有简介、门票、开放时间） |
| 酒店、住宿 | `hotel` | 同程酒店 |
| 餐厅、美食街、夜市、商圈吃喝 | `food` | 美团 |
| 电影、演出、展览购票 | `ticket` | 猫眼 |
| 商场、街区、车站等其他 POI | `map` | 腾讯地图 |
| 用户要导航过去 | `navigate` | 各家地图的唤端页，装了 app 就跳过去 |

**地图与导航在回复正文中的展示**：`prepare_landing` 返回的 `tap` / `h5FallbackTap` 是跳转目标，不是图片。
需要给用户入口时，只把回包中已有的 `h5FallbackTap.h5.url`（`map`）或 `tap.h5.url`（`navigate`）原样写成带文字的 Markdown 链接；没有对应 H5 URL 就不编造。
不要把地图 URI 放进图片字段，也不要用 `[](@replace=media_...)` 输出地图或导航链接。

行程时间轴、推算过程或多地点明细不生成自建详情页。NOW 卡直接写清当下最重要的结论，
需要继续了解时配置 `{"type":1,"agent_chat":{}}` 回原会话；不要调用 `prepare_landing kind=page`。

```bash
run_tool get_place_media '{"city":"成都","names":["武侯祠","杜甫草堂"]}'
run_tool prepare_landing '{"kind":"scenery","city":"成都","name":"武侯祠"}'
run_tool prepare_landing '{"kind":"food","city":"深圳","keyword":"南山 海鲜"}'
run_tool prepare_landing '{"kind":"map","city":"深圳","name":"石洲中路"}'
```

`ticket` 的 `keyword` 写纯片名或演出名，直达猫眼搜索结果。`food` 的深链还没配，调用会报 `DEEPLINK_MISSING`；
餐厅、美食街这类需要导航的卡可用 `kind=map` 定位到具体 POI；NOW 推荐卡的点击目标统一是原会话，不依赖地点深链。

4. 按 `create_thing` → `trigger/create_trigger`（停用）→ `write_todos`（回填真实 `rule_ids`）→
`trigger/update_trigger`（启用）的顺序执行。
5. 为每条 Todo 设置 `schedule_info`。时间型使用 `kind=TIME` 并提供 `time`；监测型使用 `kind=MONITOR` 且不提供 `time`。

6. **每条规则的指令都必须就发卡表态**：用户期待的提醒、通知或重要变化要写明何时用 `show_widget` 发什么卡；仅做维护或无值得通知的结果时写明不发卡。承诺发卡的结果不能仅靠会话文字或 `show_panel` 交付。
建完一批后逐条回读确认，**漏掉的那条不会报错，但到点永远不会发卡**。
写法见 [trigger-instruction.md](references/trigger-instruction.md)。

7. 普通创建轮有机票、火车票、天气或打车时间时，用 `show_panel` 展示对应内容；缺少的块直接省略。
美食等其他查询、推荐、行程安排和清单正常完成，但不塞进 XCard，写在回复正文或按触发规则投递 NOW。
旧调用的 `scene` 可传，但不再决定 XCard 上要出现哪些模块。

```bash
run_tool show_panel '{"panel":{
  "tickets":[{"kind":"flight","no":"CA4305","date":"2026-09-28","depCity":"深圳","arrCity":"成都"}],
  "route":{"from":"科兴科学园","to":"深圳宝安国际机场","mode":"taxi","city":"深圳","leaveBy":"06:45"},
  "weather":{"city":"成都","date":"2026-09-28"}
}}'
```

航班只传真实航班号，缺号时不传航班项；火车车次尚未确定时可用 `pending:true` 画城市对和日期。
打车时长与天气由脚本回源获取。美食推荐在回复正文呈现，餐厅需有真实名称；位置或其他数据缺失时省略对应字段。
以上内容都没有可靠数据时不要调用 `show_panel`。
字段见 [tools.md](references/tools.md)。

8. 正文只补面板上没有的：为什么这么排、哪里有不确定、还需要用户告诉你什么。
**不要复述面板内容**，用户已经看见了。普通创建轮到此为止；目的地到达推荐
仅在本轮缓存定位已可靠确认抵达时可直接发 NOW，其余 NOW 卡片在规则到点或事件命中后发。

需要发卡时（触发轮、已确认当前抵达，或用户明确要求）按 [scenarios.md](references/scenarios.md) 选卡型，
按 [now-card-protocol.md](references/now-card-protocol.md) 组装。

**NOW 卡上别堆**（这一条只管 `show_widget`，不要套到 `show_panel` 的对话卡上）。NOW 卡只放标题、一行摘要、每行一句话和缩略图；
天气、门票或时间安排若影响此刻行动，就在卡片摘要中写清最要紧的一点。行程卡点击回原会话继续了解，
不生成自建详情页；到达快览仍只讲一条完整建议。
多日行程一天只发一张总览卡，
卡上每行一程、点击回原会话。详见 [scenarios.md](references/scenarios.md)「选卡型」第零步。

## 按需读取资源

| 任务 | 资源 |
| --- | --- |
| 调用本包工具、在对话里展示面板 | [tools.md](references/tools.md) |
| 判断 Todo、Trigger、卡型或提问时机 | [scenarios.md](references/scenarios.md) |
| 写 Trigger 的工作指令、定发卡意图与结束条件 | [trigger-instruction.md](references/trigger-instruction.md) |
| 地点 Event Trigger 的三个完整 Demo | [location-trigger-demos.md](references/location-trigger-demos.md) |
| 确定行程目的地后的城市、景区到达推荐 Demo | [destination-arrival-demos.md](references/destination-arrival-demos.md) |
| 组装、校验或发布 NOW 卡片 | [now-card-protocol.md](references/now-card-protocol.md) |
| 选择和获取卡片图片 | [card-media.md](references/card-media.md) |
| 生成地图与小程序落地 | [landing-pages.md](references/landing-pages.md) |
| 判断数据能力或执行降级 | [data-sources.md](references/data-sources.md) |
| 校验完整卡片结构 | [show-widget.schema.json](references/show-widget.schema.json) |
| 校验 `image_text` 正文 | [image_text.schema.json](references/image_text.schema.json) |
| 校验 `recommend_list` 正文 | [recommend_list.schema.json](references/recommend_list.schema.json) |
| 校验 `todo_remind` 正文 | [todo_remind.schema.json](references/todo_remind.schema.json) |
| 校验 `todo_choice` 正文 | [todo_choice.schema.json](references/todo_choice.schema.json) |

## 遵守关键约束

- 将 `get_trip_context` 返回的 `found=false` 视为没有已存行程，而非错误。根据当前对话创建事项；
  需要景点结构时再加载 `travel_plan`。
- `found=true` 时城市、日期和每天的景点都已经在回包里，**不要再问一遍**——用户刚排完这趟行程，
  被追问「去哪个城市」会以为你没接住。缺的只有出发时间、住处这类行程里没有的，才问，且一次只问一项。
- 先创建停用的 Trigger，将真实 `trigger_id` 回填到 Todo 的 `rule_ids`，调用 `write_todos` 后再启用 Trigger。
- 行前信息 Todo 的 `schedule_info` 记录班次从用户出发站/机场的计划出发时刻；提醒规则的 `run_at` 记录提前 2 小时（航班）或 1 小时（高铁）的时刻。改签、改上车站或改时区时两个时刻一起重算。
- 仅使用真实回包或 `prepare_landing` 返回的 ID 与链接。不得编造 Thing / Todo ID、POI ID、同程 sid
  或小程序 `gh_` ID。需要外部落地而取不到链接时不要编造；NOW 推荐卡仍用 `agent_chat` 点击回原会话。
- `show_widget` 顶层的归属 ID 用 camelCase 的 `thingId` / `todoId`，且**不传会话 ID**。
- 每张卡只表达一个主题。将完成通知与补充问题拆为两张卡，或先提问再安排。

## 处理 Trigger 唤起

依次重读 Todo、判断是否继续、获取当时的数据、回写 Todo。命中用户委托的提醒或通知，或发现需要及时关注的重要变化时，用 `show_widget` 投递到「此刻」；只在 session 中回复不算完成通知。没有值得通知的结果时保持静默。只有拿到真实 `now_id` 才算投递成功；结果不明时先核查，不盲目重发，也不声称用户已经收到。不要把提醒已发送视为用户已完成。
