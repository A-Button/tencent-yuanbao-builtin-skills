# 数据源与降级

使用本 skill 工具获取数据。使用 `make-things` 的 `show_widget` 发布卡片；不要将查询结果直接作为卡片。

根据 SKILL.md 的探测结果调用 `app $PKG <tool>` 或
`python3 /data/skills/$PKG/scripts/<tool>.py`；两种入口返回相同结构。

## 本 skill 工具

| 工具 | 背后接口 | 能拿到 | 拿不到 |
| --- | --- | --- | --- |
| `check_weather` | 腾讯天气 | 实况；当天 + 未来 3 天；是否适合户外 | 第 4 天及以后 |
| `check_route_eta` | 腾讯驾车 | 距离、含路况分钟数、打车预估、限行 | 拥堵等级原文 |
| `check_ticket` | 同程静态班次 | 按航班号/车次、日期、线路及上车站复查计划时刻与出发地 | 个人座位、检票口、站台、登机口、实时运行状态 |
| `find_nearby` | 腾讯地点搜索 | 名称、地址、坐标、分类 | 评分、人均、图片、预订 |
| `get_trip_context` | travel_plan `trip.json` | 按天站点、城市、坐标 | 用户实时位置 |
| `prepare_card` | 本地校验 | `show_widget` 入参是否合法 | 不会真正写入 NOW |
| `check_proximity` | 本地算距离 | 当前位置到行程 POI 的距离、方位、是否进围栏 | 位置本身（由 Connector 提供） |

同程只读入口（不写行程）：

```bash
python3 <travel_plan>/scripts/api.py '{"type":"spot","cityName":"成都","keyword":"武侯祠"}'
python3 <travel_plan>/scripts/api.py '{"type":"hotel","city":"香格里拉"}'
python3 <travel_plan>/scripts/api.py '{"type":"flight","depCityName":"深圳","arrCityName":"成都","depDate":"2026-09-28"}'
```

`flight` / `train` 是按城市对 + 日期搜班次，不是按航班号查状态。

## Connector 工具（要在 Playground 上绑定）

不在包里声明，**要给本 skill 绑了才会注入**。没绑就当它不存在，按下面降级。

### 「地理位置获取」（内部名 `geo-location`）

当前会话需要用户此刻位置时（当前位置、附近、到某地的距离），用 `<PKG>/get_geo_location` 实时采集，需用户授权。
地点 Trigger 的 Judge 使用已绑定 Connector 的完整工具名
`geo-location/get_last_known_location`，`tool_arguments={}`；它只读最近一次成功采集的缓存，
返回 `is_cached=true` 和 `collected_at_ms`。正式创建前以运行时注入的工具定义核对完整名称。

`precise` 默认 `false` = 广播到用户所有在线设备、等最先响应的那台。
设备在后台或离线就一直等到超时（约 60 秒）。
拿不到时在当前会话说明无法获取实时位置，请用户提供城市或附近地标；不猜位置、不用上一轮的坐标、不拿行程目的地顶替。Trigger 中无法核实到达则保持静默，不发到达卡。
缓存定位用于地点 Trigger 的 Judge 候选判断和命中后的复核；后台不调用 `get_geo_location`
向设备请求实时坐标。缓存防抖由下游处理，`condition` 不检查采集时间。
未能确认目标行政区或精度时不能据此发卡；宝安与南山交界无法判清就不发卡。

拿到 lat/lng 之后用本包的 `check_proximity` 算距离，不要自己心算经纬度差。

### `tongchengtravel`

| 工具 | 能拿到 |
| --- | --- |
| `flight_search` | 国内/国际航班列表，参数是自然语言 `toolQuery` |
| `flight_detail` | 选定航班的舱位、价格、可订资源、退改签、行李额 |
| `train_search` | 国内火车票 |
| `hotel_search` | 按城市/区域/偏好查酒店 |

**这些是静态班次/可订资源，不是个人票据或运行动态。** `train_search` 的座别和余票不等于
用户的车厢、座位，也不含可靠的检票口或站台；`flight_search` / `flight_detail` 不含用户座位、
实时登机口、延误、取消或实际起降时间。不要承诺盯延误，也不要建航班状态触发规则。
行前 1–2 小时的单次提醒可以按已核实的计划出发时刻创建；执行时重新查询班次。
个人座次只从用户提供的电子客票等确认资料读取；检票口、站台、登机口必须来自届时可用且
明确标注查询时间的可信实时来源。没有这样的来源就写「请查看车票/现场屏幕」，不要猜。

参数是自然语言的工具（`flight_search` / `train_search`）要把用户说明的出发地、目的地、
日期、人数、舱等原样带上，不要省略也不要自行补充。

`ai_search` 产出是一段话而不是结构化字段，**不要用它取卡片要填的字段**，理由见下面降级第 6 条。

目的地到达快览可在**有 Web Search 能力的执行环境**检索当地美食、景区官方介绍、
游览建议及近期公告，记下来源 URL 和查询时间；城市、美食、景点是**不同对象**，
每张图文卡只选该对象的一条可核实、能压进摘要的完整建议，
标题不超过 18 个汉字，摘要不超过 40 个汉字；不把搜索长文、标题党或省略号“点开看”放进卡片。
这张快速推荐卡配置点击回原会话的 `agent_chat` tap；缺能力或找不到可信来源时省略
当日开放、预约、管制等动态提示。Web Search 不作为地点 Judge 的工具，也不能顶替
`check_weather`、`find_nearby` 或票务接口的结构化回包。

酒店走 `hotel_search` 查信息，但**落地仍然用本包的 `prepare_landing kind=hotel`**——
卡片要的是能拼进小程序路径的参数，自然语言搜索不保证给。

## 同程鉴权

同程网关按 `Authorization` 头鉴权，**值是裸 key，不加 `Bearer` 前缀**——加了照样 401。
key 从环境变量 `MY_TRAVEL_API_KEY` 读，沙箱内由平台注入，不要写进代码或卡片。

没配 key 时所有同程调用（`scenery` / `hotel` / `get_place_media` / `api.py` 的 spot）
统一返回「同程网关鉴权失败」。**这不是代码坏了**，报错里已经写明原因和出口。
取不到就按下面降级，不要改用 `web_search` 顶替字段。

腾讯地图那条链路（`check_weather` / `check_route_eta` / `find_nearby` / `kind=map`）
不依赖这个 key，同程不通时仍然可用。

## 执行六项降级

1. **缺少实时位置。** 用户问「我附近」时说明无法定位，请他提供城市或地标；不要把行程站点当作用户当前位置。若仅能根据行程建议，可明确写「武侯祠附近」等站点周边，不写「您附近」或「距您 X 米」。城市未知时不发布 `recommend_list`，并按 `scenarios.md` 的顺序降级。
2. **缺少航班/车站动态或个人票据。** 不要承诺能查到延误、登机口、检票口、站台或个人座次。
   行前卡仅展示有实际来源的字段；缺失时引导用户查看官方行程、车票或现场屏幕。
3. **缺少定性路况。** 使用 `check_route_eta.trafficHint` 和 `reserveMin` 提供预留区间。
4. **天气超出 3 天。** 当 `horizonExceeded=true` 时不要判断是否适合户外活动。
5. **缺少餐饮或纪念品商业数据。** 不要根据腾讯地点搜索断言评分、人均或预订信息。按 [card-media.md](card-media.md) 获取图片，但不要从图片推断商业数据。
6. **工具调用失败。** 不要更换数据源补取同一字段。`check_weather` 失败时说明天气不可用，不要改用 `web_search`；`find_nearby` 未提供评分或人均时不要从点评站补充。通过减少断言执行降级；普通对话在正文中说明数据缺口，已命中的 Trigger 若承诺向用户通知查询结果，则用 `show_widget` 告知无法核实，不以 session 回复代替。

`check_weather`、`check_route_eta` 和 `find_nearby` 是本 Skill 的取数脚本，回调执行时通过 `run_tool` 调用；地点到达规则的 Judge 仍只使用已绑定的 `geo-location/get_last_known_location`。
