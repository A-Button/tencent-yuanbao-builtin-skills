# 落地目标

卡片上可点的地方要有明确去处。跳合作方小程序或地图时用 `prepare_landing` 生成 `tap`，
不要手拼路径，也不要编造 ID；回原会话直接配置 `{"type":1,"agent_chat":{}}`。

点开看一个具体地方时可走对应小程序；行程的多地点、时间轴或推算过程在主对话中说明，
NOW 卡的点击目标配 `{"type":1,"agent_chat":{}}`，不生成自建详情页。

## 六种可用 kind

| `kind` | 落到哪 | 必填 |
| --- | --- | --- |
| `map` | 腾讯地图 `gh_ff25a9b4394d`，按 city+name 自查 `poiId` | `name`，建议给 `city` |
| `scenery` | 同程景点 `gh_0a00573ff7cf`，自查 `sid` | `sid`，或 `city` + `name` |
| `hotel` | 同程酒店 `gh_0a00573ff7cf` | `city` |
| `food` | 美团 `gh_870576f3c6f9` | `keyword` |
| `ticket` | 猫眼 `gh_d9004ba7511f` | `keyword` |
| `navigate` | 各家地图自己的唤端页（`type=2`） | `name` + `lat`/`lng`，或 `city` + `name` |

按地点类型分流，不要一律用 `map`：景区、公园、博物馆、古镇走 `scenery`（有简介、门票、开放时间）；
餐厅、美食街、夜市走 `food`；电影、演出、展览购票走 `ticket`；商场、街区、车站等其他 POI 走 `map`。

`mini_program.name` 必须是 `gh_` 开头的**原始 ID**。填 AppID（`wx` 开头）会 bad_param。
小程序原始 id 与 `travel_plan` 同源。

```bash
run_tool prepare_landing '{"kind":"scenery","city":"成都","name":"武侯祠"}'
run_tool prepare_landing '{"kind":"map","city":"深圳","name":"海岸城"}'
run_tool prepare_landing '{"kind":"ticket","keyword":"流浪地球3"}'
```

## 猫眼：按片名 / 演出名进搜索结果

`kind=ticket` 落猫眼搜索结果页的「全部」tab。`keyword` 写纯片名或演出名（「流浪地球3」「周杰伦 嘉年华」），
不要带影院、场次、城市——猫眼搜索不收城市，多余的词只会搜不到。

## 美团：深链没配好之前不可用

美团的深链 `path` 还没拿到。**`kind=food` 现在会直接报 `DEEPLINK_MISSING` 拒绝，不会落首页。**

理由：卡上写着「海岸城」，点进去是美团首页还得自己再搜一遍——这比没有跳转更伤。
没跳转用户知道要自己找；给了跳转却落错地方，他会认为这个功能坏了。

**替代做法**：餐厅、美食街这类地点改用 `kind=map`，腾讯地图能定位到具体 POI；
需要导航时可改用地图落地；NOW 推荐卡则配 `{"type":1,"agent_chat":{}}`
回原会话，把关键词写进卡片标题或 `summary`，不因美团深链缺失而变成不可点击。

拿到深链后填 `scripts/landing_links.py` 顶部的 `MEITUAN_PATH` / `MAOYAN_PATH`（参数名和来源参数在旁边的 `*_PARAMS` / `*_EXTRA`）即可开启，
别处不用改。要的是**路径模板**（形如 `pages/search/index`），不是「复制链接」得到的
`#小程序://名称/xxxx`——那是 shortLink，协议的 `{name, path, mp_type}` 里没有地方放它。

## 导航

`kind=navigate` 跳**各家地图自己托管的唤端页**，全是 HTTPS，我们不需要部署任何页面。
在手机上打开时，装了对应 app 的用户会被引导跳过去，没装的留在网页版。

```bash
run_tool prepare_landing '{"kind":"navigate","city":"深圳","name":"宝安机场"}'
run_tool prepare_landing '{"kind":"navigate","name":"宝安机场","lat":22.6393,"lng":113.8108,"provider":"amap"}'
```

`provider` 可选 `qqmap`（默认，同生态）、`amap`、`baidu`、`apple`，省略即腾讯。
四个地址都实测可达。

**坐标一律 gcj02**（腾讯地图返回的就是）。腾讯与高德原生 gcj02 直接用；百度默认按 bd09 解释，
工具已强制带 `coord_type=gcj02`，改这段时别弄丢——错了是静默偏移几百米，界面上看不出来。

### 想让用户自己挑用哪个地图

一个 `tap` 只能落一家。要给选择权，就发一张 `recommend_list`，每行一家地图、各挂各的 `tap`：
选择权放在卡片上，而不是页面里。对各家分别调一次 `prepare_landing kind=navigate` 拿 tap 即可。

协议只有三种 tap，`geo:` / `iosamap://` 这类 scheme 没法直接下发（不是 HTTPS，容器也只会把
`h5.url` 丢进 WebView），所以唤起手机**系统级**的「打开方式」选择框做不到；
上面这个卡片式选择是等效的替代。

## 把 tap 挂在哪

优先挂 `actions[].tap`，并给按钮写清文案（「查看路线」「看看这家」）。点击目标明示，用户知道自己要去哪。

整卡 `tap` 只在**整张卡就一个去处**时用。地点、美食、景点等 NOW 推荐列表的整卡和每一项
都用相同的 `agent_chat` 目标回原会话，这种组合可以同时配置。
`recommend_list` 的行各自去不同页面时不要再配整卡 `tap`：
卡片留白仍然可点，会落到和点行不同的地方——点「海岸城」那行开地图、点它旁边的空白去了别处，
没有用户能预期这个。`prepare_card` 检出这种组合会在 `warnings` 里点名。

逐项落地放 `recommend_list.items[].tap`，每行指向自己的地点。

## 取不到 ID 时

- `scenery` 查不到 `sid` 会**失败而不是猜**，以免跳到错误景点。改用 `kind=map`。
- `map` 查不到 `poiId` 仍可用关键词打开，`resolvedPoi=false` 就是这种情况。
- 一律不要编造 `gh_` ID、`sid`、`poiId` 或页面路径。普通信息卡取不到落地可省略 `tap`；NOW 推荐卡仍配回原会话的 `agent_chat` tap。

## 旧 `page` 调用

已有 Trigger 里若保留了 `prepare_landing kind=page`，工具仅返回
`{"type":1,"agent_chat":{}}`，点击回原会话。新规则不要再调用这个 kind；
需要用户知道的行程信息直接写在卡片摘要中，更多内容在主对话继续说明。
