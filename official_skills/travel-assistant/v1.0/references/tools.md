# 工具调用方式

本包的工具通过统一 CLI 调用，**不要直接执行 `scripts/` 下的脚本**——绕开 CLI 时不会产生
宿主挂载界面所需的旁路结果，`show_panel` 的面板不会出现，其余工具的返回也拿不到。

**包名一律用 SKILL.md 那段探测打出的 `$PKG`，不要照抄本文里的名字。** 沙箱目录名不保证等于
`travel_assistant`——实测出现过 `travel-assistant`（连字符），照抄就一路 `SKILL_NOT_FOUND`。
下文统一写成 `run_tool <工具> '<json>'`，它就是探测那段里定义的函数。

## 查 schema

不确定某个工具收什么参数时，先查，不要猜：

```bash
run_tool describe '{}'
```

## 工具清单

包名就是 `travel_assistant`。SKILL.md 里那段通配探测是为了应对沙箱目录名与包名不一致的
情况（踩过一次：目录叫 `travel_assistant`、frontmatter 写成别的，探测写死候选名后连续 63 轮
找不到包）。探测成功后 `$PKG` 的值正常就是 `travel_assistant`。

| 工具 | 干什么 |
| --- | --- |
| `run_tool show_panel` | 在对话流展示信息面板，见下 |
| `run_tool check_ticket` | 按已知航班号/车次复查同程静态出发信息，不返回个人座位或检票口 |
| `run_tool get_trip_context` | 读 travel_plan 排好的行程 |
| `run_tool check_weather` | 天气，当天加未来 3 天 |
| `run_tool check_route_eta` | 路况、距离、预留时间 |
| `run_tool find_nearby` | 周边地点搜索 |
| `run_tool get_place_media` | 同程收录景点的真实配图，一次最多 8 个 |
| `run_tool check_proximity` | 当前位置到行程地点的距离、方位与是否进围栏 |
| `run_tool plan_geofence` | 把围栏换成经纬度区间，给围栏规则的 `judge.condition` 用 |
| `run_tool prepare_landing` | 生成卡片落地 tap，七种 kind |
| `run_tool prepare_card` | NOW 卡片预校验，被拒时才用 |

行前 Trigger 命中后，先按 Todo 中保存的身份信息复查班次：

```bash
run_tool check_ticket '{"kind":"train","no":"G1234","date":"2026-09-28","depCity":"深圳","arrCity":"广州","depStation":"深圳北"}'
```

`ok=true` 时只使用回包 `ticket` 中的静态时刻与出发地；`unavailable` 列出的个人座位、检票口、站台、登机口、实时状态**不能从这个工具推断**。
`NOT_FOUND`、`AMBIGUOUS` 或取数失败时不要拿相似车次顶替，按 [trigger-instruction.md](trigger-instruction.md) 的行前失败卡说明用户应查看票据或现场屏幕。

## `show_panel`：对话 XCard

`show_panel` 只负责当前对话中的可视化，不写入 Todo，也不发布 NOW。XCard **只渲染机票、火车票、天气和打车时间**；其他业务工具、地理围栏和 NOW 卡片照常使用。旧入参中的美食、景点、演出、酒店、时间轴、清单与选择不会在 XCard 上显示，回执会提示省略。只有这些内容时直接在回复正文呈现，不调用 `show_panel`。

| XCard 块 | 输入 | 说明 |
| --- | --- | --- |
| `tickets` | 至多 2 条 `kind:"flight"` 或 `kind:"train"`；航班必须给真实 `no`，火车可给 `no` 或 `pick` / `pending:true` | 有真实航班号才渲染航班块；缺号时整块省略。火车车次未定仍可显示城市对和日期。 |
| `weather` | `{city,date}` 或查到的 `{temp,text,range,days,chips}` | 使用 `check_weather` 的真实数据。 |
| `route` | `{mode:"taxi",from,to,city?,leaveBy?}` 或查到的 `duration` | 脚本按驾车路况取打车预计时长；XCard 只显示目的地、预计时长和可选出门时刻。 |

```bash
run_tool show_panel '{"panel":{
  "tickets":[{"kind":"flight","no":"CA4305","date":"2026-09-28","depCity":"深圳","arrCity":"成都"}],
  "weather":{"city":"成都","date":"2026-09-28"},
  "route":{"mode":"taxi","from":"科兴科学园","to":"深圳宝安国际机场","city":"深圳","leaveBy":"06:45"}
}}'
```

火车票可以单独出对话卡。例如班次未定可传
`{"tickets":[{"kind":"train","pending":true,"date":"2026-09-28","depCity":"深圳","arrCity":"广州"}]}`。
美食可用 `find_nearby` 查询真实餐厅，在回复正文说明；距离要按取数回包的锚点说明，不能冒充距用户的位置。地点到达后的美食 NOW 卡仍按到达规则投递。仅有美食推荐时不调用 `show_panel`。

缺少的块直接省略；不能用编造的数据凑齐。没有真实航班号时，机票需求在回复正文说明并按需询问航班号；若卡上还有天气、打车或火车信息，其他块照常展示。纯提醒、景点推荐、多日行程、住宿和用户选择继续走原有业务流程，并在回复正文或适用的 NOW 卡中表达。`show_widget` 的协议见 [now-card-protocol.md](now-card-protocol.md)，不受 XCard 渲染范围调整的影响。
