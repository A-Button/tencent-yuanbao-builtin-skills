---
name: travel_plan
description: "规划多日旅行行程。用户要安排某城市的多日游/深度游/周末游, 要一份行程或旅游攻略,要在已有行程上加一天、增删景点时使用。 常见说法: 帮我规划、做份攻略、几日游、行程安排、景点安排、深度游。不要用于: 单独查机票或火车票、只订酒店而不做行程、出行途中的实时导航。"
---

# Travel Plan

生成纯景点的多日行程卡。你负责选点、排序和规划文案；坐标、地址、图片、评分、票价、营业时间、介绍、购票链接、站间距离与真实路网由脚本补齐。

## 严格规则

1. 行程的读取与写入只能通过统一 CLI 执行：`app travel_plan <tool> '<json>'`。`<tool>` 只能取 `get_plan_state`、`update_trip_meta`、`upsert_day`、`upsert_stop`、`apply_verified_web_facts`、`delete_stop`、`delete_day`、`render_trip`、`reset_trip`、`undo_last_mutation`。禁止直接执行 `scripts/` 下的任何 handler（如 `python3 scripts/upsert_day.py`、`python3 scripts/travel_api.py`），也禁止用 `python3 -c` 或自写脚本代替 CLI：绕开 CLI 时不会产生宿主挂载卡片所需的结果行，即使数据写进了本地状态，用户侧也看不到任何变化。唯一例外是规划阶段的只读查询 `scripts/api.py`（见「1. 规划」），它不读写行程，也不出卡片。
2. 每个动作是一条独立命令，stdout 原样交给宿主。不要把调用包进自写脚本，也不要用 `head`、`tail`、`grep`、`jq` 过滤或截断输出——卡片靠完整 stdout 挂载，被包裹或截断后卡片就拿不到数据。「原样」只约束命令怎么执行，不代表要把这份 stdout 展示给用户，见规则 8、9。
3. `stops` 只放景点、景区、博物馆、公园、古镇及明确的游玩体验点。机场、火车站、高铁站、客运站、公交站、地铁站、码头、酒店、餐厅一律不进 `stops`，可以在对话里建议。
4. 只写行程标题/目的地、每日分组与顺序、`day.city`、景点 `name` 和规划型 `summary`。不要写坐标、图片、门票、评分、等级、营业、地址、电话、介绍、链接、距离、时长、交通方式或路线。
5. 写入不需要传任何版本号：并发由脚本内部串行化，你只管按顺序调用。写入 ACK 里 `changed=false` 表示这次调用的内容与当前状态一致（幂等命中），不必重试。
6. 写入 ACK 只回行程骨架 `planDays`（每个景点给 `stopId` 和 `name`，`summary` 一律省略成 `…`），不含图片、坐标、票价和路线。这份骨架已经够你确认结果并接着改下一处，不必为了拿 `stopId` 再调一次 `get_plan_state`。要看完整客观字段时调 `render_trip`。
7. **只要这一轮碰过行程，这一轮就必须出一次卡。** `render_trip` 是唯一出卡片的动作，`update_trip_meta`、`upsert_day`、`upsert_stop`、`apply_verified_web_facts`、`delete_stop`、`delete_day`、`reset_trip`、`undo_last_mutation` 全都只写状态、不出卡。首轮建行程要出，之后每一轮增、删、改同样要出——用户看到的是卡片，不是你的复述；这一轮没渲染，用户这一轮就什么都没看见，上一轮的旧卡不算数。判断依据是回包里的 `rendered` 与 `nextAction`：只要 `rendered=false`、`nextAction=render_trip` 或 `issues` 含 `RENDER_REQUIRED`，就说明卡片还没刷新，此刻坐标、图片、评分、票价、营业状态和真实路线全是空的。此时立刻调 `render_trip`，拿到 `rendered=true` 再回复用户；在那之前不要说"行程已更新""行程卡已生成"，也不要用长文攻略替代卡片。一轮里连改多处时不必每改一处渲染一次，改完最后一处再统一渲染一次即可。
8. 工具输出一律不进回复。stdout、`structuredContent`、`issues`、`warnings`、坐标与折线，以及运行时替超大回包生成的 `.json` 文件，都只给宿主和你自己看。回复里不要粘贴或转述这些字段，尤其不要写出任何 `.json` 文件名或文件引用。用户该看到的只有卡片本身和你的自然语言说明。
9. 这三份 JSON 不发给用户，任何形式都不行：行程沙盒状态文件（`$MY_TRAVEL_STORE`，默认 `~/.travel_plan/trip.json`）、`render_trip` 的回包、运行时替超大回包转存的 `.json`。不写进 `<media_info>`，不做成附件、文件卡片或下载链接，也不在正文里提它们的文件名。用户要 PDF、Word、Excel 等导出件时照常给，但要另行生成，不能把这几份 JSON 原样递出去或改个后缀充当导出件。

## 过程中说给用户听的两件事

一趟完整规划要跑十几轮、好几分钟，用户全程只能靠两条通道感知进展：每次调用的 `description`，和你写在正文里的话。两条都要写——只填 `description`，用户就只能盯着一串没有来龙去脉的短句干等。

### `description`：每次工具调用都填，无一例外

`api.py`、`web_search`、`ask_user_question`、每一条 `app travel_plan <tool>`，以及 read / edit / write 都算。漏填或照抄该参数自带的英文默认（`"Why execute this command."` / `"Why need to view this file."` 之类），用户那一步就只剩一句实现黑话。

**怎么写：** 说这一步替用户拿到了什么，不说内部动作——不出现工具名、参数名、字段名、文件名，不用"写入 / 读取 / 更新 / 渲染 / 状态 / 调用 / 卡片 / 行程卡 / 官方名称"这类实现词，对用户一律只说"行程"；一句口语短语，简短，不带"我 / 正在 / 已"，带上城市、第几天或景点名让用户看出进展。核对类的步骤按用户关心的结果写（`确认喀纳斯三湾的位置和开放情况`），不要写成内部校对（`核对喀纳斯三湾的官方名称`）。

下面「三阶段流程」和「修改已有行程」里每个命令旁都给了该步的范例（`desc ▸` 行）——那才是关键：执行到哪一步，就照那一行的语气填上，不用再回头背规则。范例是语气示范不是穷举，没列到的动作照同样口吻自造。

### 正文：开工、转折、收尾各说一次

`description` 只有一行，承载不了取舍和理由。下面三个节点要在发起工具调用的同时写一小段正文：

- **第一次调工具时**：两三句说清这趟打算怎么安排——几天、走哪条线、为什么这么分段，并说明接下来要花点时间把详情补齐。这段最要紧：用户后面要等几分钟，得先知道自己在等什么。
- **做出用户会在意的判断时**：改变天数或路线结构、放弃某个热门点、因为车程太长把一天拆成两天、发现景点临时关闭或要预约，都顺带说清理由。
- **`render_trip` 拿到 `rendered=true` 后**：给最终说明，和卡片一起交付，然后按下面「交付后问一句」收尾。

其余轮次保持安静，只填 `description` 就够；不要每调一次工具就汇报一次，也不要把同一件事在正文里说第二遍。

正文和规则 7、8 不冲突：`rendered=true` 之前照样不能说"行程已更新""行程卡已生成"，也不能把工具输出、坐标、折线或 `.json` 文件名写进正文。过程中的正文只讲规划思路和取舍，不讲数据从哪来。

## 三阶段流程

### 1. 规划

- 信息不足时用 `ask_user_question`，一次只问最关键的一两项。
  `desc ▸ 先跟你确认几个关键的出行安排`
- 用 `spot` 和 `place` 交叉查询真实景点候选；多城市行程按城市分别查。优先采用两源返回的官方名称写入 `upsert_day`，减少同名与简称歧义。这是唯一不走 `app` CLI 的命令，因为 `api.py` 只查外部数据源，不读写行程也不出卡片：

```bash
python3 <skill>/scripts/api.py '{"type":"spot","cityName":"成都","keyword":"熊猫"}'
python3 <skill>/scripts/api.py '{"type":"place","city":"成都","keyword":"熊猫基地","autoExtend":true}'
```
`desc ▸ 为你挑选成都值得一去的熊猫主题景点`
`正文 ▸ 成都三天我按"市区人文 — 熊猫和近郊 — 古镇"分段，第一天不排太满留点缓冲。先把这些点的位置、开放时间和门票逐个落实，需要一两分钟。`

- 用 `web_search` 了解候选景点的近期热点：新开/新展、时令活动、近期话题、临时关闭、预约变化、网红打卡及避坑信息。只把有规划价值的结论写进 `summary`，不要把搜索结果写成客观字段。
  `desc ▸ 帮你留意成都近期的热门玩法和注意事项`
- 每天景点地理就近、强度合理；剔除同名交通枢纽和非景点条目。
- 同程与腾讯地图凭证由 Sandbox NetworkPolicy 托管注入。调用时只请求脚本内固定的原始业务地址；不要设置、读取或传递业务 Token/Key，也不要让浏览器直接调用这些鉴权接口。

### 2. 逐天写入

先读状态确认当前有没有行程，再建卡：

```bash
app travel_plan get_plan_state '{}'
app travel_plan update_trip_meta '{"title":"成都三日游","destination":"成都","newTrip":true}'
```
`desc ▸ get_plan_state：看看你现在已经安排了哪些行程`
`desc ▸ update_trip_meta（新建）：为你开启成都三日游的规划`

`newTrip=true` 只用于当前没有行程时的首次创建。改已有行程严禁再用它；用户明确要放弃旧行程另规划一趟时，确认后用当前 `tripId` 调 `reset_trip`。

一天一次写全当天景点，多城市行程给当天补 `city`：

```bash
app travel_plan upsert_day '{"label":"第1天","title":"成都经典","city":"成都","stops":[{"name":"武侯祠","summary":"三国文化地标与红墙竹影。"},{"name":"锦里古街","summary":"川西民俗与夜景。"}]}'
```
`desc ▸ 安排好第1天成都经典线路的游玩点`

`upsert_day.stops` 是整天列表替换，不是局部更新。

### 3. 渲染（必做，写完最后一天就执行）

```bash
app travel_plan render_trip '{}'
```
`desc ▸ 为你整理好行程，补齐景点详情和路线`
`正文 ▸（拿到 rendered=true 之后再说）三天这样走下来强度是均衡的，熊猫基地建议一早去，人少也更活跃。`

`render_trip` 补齐客观字段与真实路线，并输出卡片。它返回 `rendered=true` 才算这一轮做完，可以开始回复用户；成功一次就够，不要重复调用。

按返回的 `issues[]` 处理，`retryable=false` 时不要原样重试：

- `RENDER_REQUIRED`：还有未渲染的写入，立刻调 `render_trip`。
- `POI_CANDIDATE_AMBIGUOUS`：脚本已经先填入排序第一的候选；核对 issue 的 `candidates`（名称、城市、区县、地址、坐标和分类），选中正确实体后用其官方名调用 `upsert_stop`，再 `render_trip`。
- `LOCATION_UNRESOLVED`：用 `spot`、`place` 重新核对官方名称，再用 `upsert_stop` 改名并 `render_trip`；合理名称仍失败就换同类景点。
- 同一个站点最多纠正并重新渲染两轮；两轮后仍有 `POI_CANDIDATE_AMBIGUOUS` 或 `LOCATION_UNRESOLVED`，就更换景点或如实告知该点信息缺失，不得无限重试。
- `PROVIDER_EMPTY_BATCH`：某个数据源整批返回零结果，这一城景点的介绍、图片、票价、开放时间会全部留空。重新 `render_trip` 一次；仍为整批空就如实告知客观详情暂时取不到，不要反复重试。
- `PROVIDER_NO_RESULT`：该数据源没有收录这个景点。用 `spot`、`place` 核对官方名后 `upsert_stop` 改名再 `render_trip`；确实没有收录就走 `WEB_FACT_ELIGIBLE` 补齐或如实说明。
- `WEB_FACT_ELIGIBLE` 且明确列出 `introduction`、`ticketPrice`、`businessHours` 缺失：用 `web_search` 查政府、景点官网、官方账号或官方售票页，再写入：

```bash
app travel_plan apply_verified_web_facts '{"dayId":"day1","stopId":"stop-xxxx","facts":{"businessHours":"09:00-18:00"},"sourceUrl":"https://www.example.gov.cn/scenic-hours","sourceType":"government","retrievedAt":"2026-09-04T15:00:00Z","evidence":"政府文旅页面开放时间栏目明确写明每日09:00-18:00"}'
```
`desc ▸ 为你核实武侯祠的开放时间`

网页补充只允许这三个字段，不得写 `rating`、`level`、坐标或路线。没有官方信息就让字段保持缺失，界面会显示「暂无」——不要编造，也不要手填直线路线。

`businessHours` 只写时段本身，如 `09:00-18:00`、`08:30-11:30、13:00-17:00`、`全天开放`。不要写日期、当日开闭状态或成段说明（`2026-09-09 08:00`、`今日已闭园,明日8:30开放`、`实行分时段预约，详见公众号`都不行）：详情栏这一格只有一行宽，写长了会被截断成看不懂的半句。脚本会从你写的文本里挑时段，挑不出且文本过长时直接报 `INVALID_ARGUMENT`，改写成时段再提交。

## 修改已有行程

**这一节的每个动作都只写状态、不出卡；这一轮改完必须再走一次「3. 渲染」，用户才看得到结果。** 修改轮和首轮一样，最后一步永远是 `render_trip`。

先 `get_plan_state` 拿到 `tripId`，从 `planDays` 读 `dayId`、`stopId`。连续多轮修改时每轮都重新读，不要把只含第一天的数据重新建卡。

改一个景点必须带 `stopId`，只影响该站点：

```bash
app travel_plan upsert_stop '{"dayId":"day1","stopId":"stop-xxxx","name":"杜甫草堂","summary":"诗圣故居与古典园林。"}'
```
`desc ▸ 把第1天的景点换成杜甫草堂`

替换已有天时，必须同时提交 `replaceStops=true` 和刚读取的完整 `expectedStopIds`；任一 id 或顺序不符都会拒绝写入。

删除站点或天之前先让用户确认，并原样提交刚读取的快照：

```bash
app travel_plan delete_stop '{"expectedTripId":"trip-xxxx","dayId":"day2","stopId":"stop-xxxx","expectedStopName":"宽窄巷子"}'
app travel_plan delete_day '{"expectedTripId":"trip-xxxx","dayId":"day3","expectedStopIds":["stop-a","stop-b"]}'
```
`desc ▸ 按你的要求去掉宽窄巷子` / `desc ▸ 按你的要求删掉第3天的安排`

误删、误替换或误重置后立即撤销最近一次修改：

```bash
app travel_plan undo_last_mutation '{"expectedTripId":"trip-xxxx"}'
```
`desc ▸ 帮你撤回刚才的改动`

### 改完这一步不能省

不论上面做了哪一种改动、改了几处，这一轮的最后都要重新出卡：

```bash
app travel_plan render_trip '{}'
```
`desc ▸ 为你更新好行程，重新补齐详情和路线`

拿到 `rendered=true` 再回复用户。跳过它，用户这一轮看到的只有你的一段文字，行程卡不会有任何变化。

## 交付后问一句

行程卡只是一张图，它不会在出发前提醒用户带什么、几点出门、当天下雨要不要换备选。这些归行程助手管，
它能读到你刚排好的这份行程，把每天的安排变成待办和到点提醒。

**首轮把完整行程交付给用户之后**（`rendered=true`、最终说明已经写完），用 `ask_user_question` 问一次：

- 问题：`行程排好了，要我顺手帮你把出行安排盯起来吗？`
- 选项一（推荐，排第一）：`好，帮我安排提醒和待办（推荐）`
- 选项二：`先不用，我自己看看`

`desc ▸ 问问要不要把这趟行程盯起来`

用户选了第一项，就加载行程助手接着做，不要自己去建待办或提醒——那不是本 skill 的能力，
`travel_plan` 没有任何写待办、写提醒的工具，硬编一个只会让用户什么都收不到。
加载后把城市、日期和每天的主要景点交代给它，它会自己读这份行程补齐细节。

用户选了第二项就正常结束，不要追问第二次。

### 什么时候不问

- **改行程的轮次不问。** 用户加一天、删一个景点都弹一次，很烦。只在首轮完整行程交付后问一次。
- **这趟已经问过就不再问**，无论上次答的是要还是不要。
- **行程还没交付不问。** `rendered=true` 之前不问，卡都没出来就谈盯行程，用户不知道你在说什么。
- 用户自己已经提过要提醒、要待办、要人盯着行程，直接加载行程助手做，不用再问一遍。

### 措辞

问句和选项里只说「行程助手」「提醒」「待办」这类用户听得懂的词。规则 8 的约束在这里同样成立：
不出现 skill 名、工具名、参数名，也不要说「调用」「加载」「移交」。
