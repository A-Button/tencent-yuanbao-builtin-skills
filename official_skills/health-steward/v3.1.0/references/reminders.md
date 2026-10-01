# 提醒：创建、到点回调、四条场景

只建会发动态的四条线。护肤、选菜、睡眠本期没有能力，没有对应工具，别为它们建 Todo / Trigger。

Thing / Todo / Trigger / `show_widget` 只能使用本轮工具表中真实存在的平台工具，**不要 `load_skill(make-things)`，也不要 delegate**（原因见 SKILL.md）。收到长期提醒需求时，先一次性检查 `get_thing`、`create_thing`、`trigger/create_trigger`、`write_todos`、`trigger/update_trigger`、`show_widget` 是否全部可用；缺任一项立即停止，不先查时间、不运行 `now_setup`、不承诺稍后补建。工具齐全时，整个创建流程只跑一次 `now_setup`；到点只跑一次 `now_card`。参数和卡片照抄脚本回执，不自己编 rrule、重算 `dtstart`、拼卡或搜图。`show_widget` 的字段和踩过的坑在 [now-card-spec.md](now-card-spec.md)。

## 创建

先完成平台工具可用性检查。检查失败就结束本轮创建，不得执行 `date`、不得运行 `now_setup`、不得 delegate。检查通过后只调用一次 `now_setup`，所有 Trigger 共用该回执中的同一个时间基准；即使包含早、午、晚三条规则，也禁止逐条再次确认当前时间。

首次加载且 `get_thing` 确认还没有本 Skill 的 Thing 时，先用 `ask_user_question` 让用户选提醒类型与时刻。用户没有选择（关闭、跳过、没给有效选项）就四类全部按默认建；明确拒绝或只想看一次数据不属于未选择，不建。只要其中几条，就只建那几个 Todo 和规则，不要把不要的也建上再停用。已有 Thing / Todo 时不再问、不重建，只补缺的项。

顺序：

1. `get_thing` 确认没有；`create_thing` 建空 Thing，`mcp_app_ids` 只绑 `health-steward`，三餐时刻与训练时间写进 `Thing.goal`。
2. 预设稳定的 todo-id（见下表），一条场景一个 Todo。
3. `trigger/create_trigger` 逐条建规则，创建时一律 `enabled=false`。
4. 一次 `write_todos`，`rule_ids` 填上一步返回的真实 `trigger_id`。
5. 重读确认，再逐条 `trigger/update_trigger {"enabled":true}`。
6. 发一条初始动态：`card_type` 用 `todo_remind`，`title` 写安排了什么，`data.items` 一条规则一项写清时刻，`todoId` / `thingId` 指向本批。先把完整请求存到工作区按 Thing 分隔的 setup 文件再调用，回包有 `now_id` 才算发出。

规则仍停用时正文只能写「已记下、尚未运行」，不能写「已开启」。这些工具不在表里就停，如实说本会话建不了长期提醒。重试先重读 Thing、规则和已保存的回执，只补没成功的步骤。

| Todo | todo_id | 规则 |
|---|---|---|
| 三餐拍照提醒 | `todo-s1-meals` | S1（早 / 午 / 晚各一条 Trigger） |
| 今日训练 | `todo-s2-train` | S2 |
| 健康日报 | `todo-s3-daily` | S3 |
| 健康周报 | `todo-s4-weekly` | S4 |

## 四条规则（唯一会发动态的）

所有规则都是 `trigger_kind: "rrule"`、`run_at: ""`、创建时 `enabled: false`，**不带 `judge`**：状态都在 App 持久卷里、只能经 bash 读，不是 Judge 能填的平台工具，规则又全是时间驱动。到点后由你自己读状态再决定发不发。`instruction` 统一写「加载 health-steward，重读当前 Thing，执行本次到点工作。」`timezone` 一律 `Asia/Shanghai`；`dtstart` 只能照抄本轮唯一一次 `now_setup` 的回执，由脚本自动选择创建当天或次日。禁止运行系统 `date`，禁止自行判断“今天是否已过”、逐条重算或校验。长期跟进不写 `UNTIL`，不要用 create_timer、番茄钟或逐轮建 DELAY。

| 规则 | rrule | 默认时刻 | 到点做什么 | 什么时候发 |
|---|---|---|---|---|
| S1 拍三餐提醒 | `FREQ=DAILY;INTERVAL=1` ×3 | 早 08:30 / 午 11:30 / 晚 17:30 | `now_card`，scene=s1，slot 对应该餐 | 本餐还没记录、也没跳过才发 |
| S2 今日训练 | `FREQ=DAILY;INTERVAL=1` | 08:00 | `now_card`，scene=s2 | 有排期才发 |
| S3 健康日报 | `FREQ=DAILY;INTERVAL=1` | 22:00 | `now_card`，scene=s3 | 拿到 `report_path` 才发 |
| S4 健康周报 | `FREQ=WEEKLY;BYDAY=SU` | 周日 22:00 | `now_card`，scene=s4 | 拿到 `report_path` 才发 |

S2 的能力边界是“提醒并展示已经排好的当天训练”，不是无人值守地根据前一天饮食和训练记录自动生成一套新计划。用户要求“每天自动生成/动态调整计划”时，不得伪装成普通 S2 提醒创建，也不得 delegate；应简短说明当前只支持先排训练再定时提醒，并询问是否改为这个方案。

表里「发」一律指用 `show_widget` 出一张 Now 卡，**不是在对话里写一段提醒话术**。到点命中且有内容时发卡是默认动作，不需要用户再点头；只有上表写明的那几种情况才允许安静。用正文顶替发卡，用户手机上收不到任何东西，而且回包里没有 `now_id`，不能对他说已经提醒过。

## 回调

1. 只信任宿主提供的本轮规则身份，用 `get_thing`、必要时 `trigger/list_triggers` 重读。Todo 已完成、已暂停、条件已改或规则不再绑定时，不执行旧任务。
2. 跑 `now_card`，`scene` 和 `slot` 用规则 instruction 里写的那一对。读取失败、超时、字段缺失都是失败，不等于没有新进展。
3. `send` 为 false 就停，不要调 `show_widget`。为 true 就把回执里的 `show_widget` 原样存成按 Thing 分隔的事件文件，再交给宿主的 `show_widget`，不要改字段。
4. 发布不幂等：超时、连接中断或回包缺失都不要自动重试，也不要改改标题重发，如实说结果未确认。回包带真实 `now_id` 才记为已发布。

`thingId` 用 `get_thing` 回执里的真实 ID，`todoId` 用本次相关的那一条，两者要么都给要么都不给。请求整体上限 64KB，图多时把 `desc` 写短。没有 `eventId`，平台也不按内容去重：同一天同一餐重复调用就是重复发卡，靠的是你发之前先读状态判断该不该发。

## S1 拍三餐提醒

| 餐次 | meal key | 默认提醒时刻 |
|---|---|---|
| 早餐 | `breakfast` | 08:30 |
| 午餐 | `lunch` | 11:30 |
| 晚餐 | `dinner` | 17:30 |

到点跑 `now_card {"scene":"s1","slot":"<本餐>"}`。本餐已记录或已跳过，回执 `send` 为 false，这次不发。用户改作息时三条时刻一起改，写进 `Thing.goal`，并用 `now_setup` 的 `times` 重算规则。

### S1 的 Now 卡

卡型是待办选择卡（`card_type: "todo_choice"`, `select_mode: 2`），请求体照抄 [now-card-spec.md](now-card-spec.md) 的「S1 三餐」那段。

**每次都列满三行，不是只列要提醒的那一餐**：已记录的标 `done: true` 置灰，待记录的留着可勾。三行 + 两个按钮缺一不可，**不许退化成纯文字提醒卡**。

- `title` 只写餐次两个字（`早餐` / `午餐` / `晚餐`），状态和吃了什么写进 `desc`（`已吃 · 酸辣粉+两个卤蛋` / `待记录 · 拍一张我帮你算`）。`title` 会被接进用户发回来的那句话，所以不带 emoji、`·` 或状态后缀。
- 已记录的餐次 `done: true`，同时必须 `selected: false` 或干脆不给 selected，否则整次发布失败。
- 配图由 `now_card` 填好：没记录的餐次用预设图库里的长期 HTTPS 地址；已记录的只有档案里本来就是公网 https 才用那张，否则同样用预设。不要搜图，不要拿沙箱路径或内网短链顶上。
- 「去记录」是导航动作，只跳回原会话，不自动发送“我要记录”等占位文字。用户随后直接上传照片或输入“这是我的午餐”即可。
- 「不吃了」是明确业务动作，保留 `send_prompt: 我要跳过`。勾着午餐点下去，用户发出的就是 `我要跳过午餐`；收到后立刻调用 `diet_skip`。未勾选餐次时只会收到半句，需追问是哪一餐。

## S2 今日训练

每天 08:00 到点跑 `now_card {"scene":"s2"}`：没有排期时 `send` 为 false，不发；有排期就用回执里的卡。训练建议照抄 `workout_today`，练完后的消耗由 22:00 的日报计入。

### S2 的 Now 卡

卡型同样是待办选择卡，骨架见 [now-card-spec.md](now-card-spec.md) 的「S2 训练」。**动作行加两个按钮缺一不可，不许退化成一句「今天练什么」的纯文字卡**。

- `title` 只写动作名，`desc` 写组数 × 次数或秒数，照抄 `workout_today` 回执里这个动作的 `meta`。
- 每行的示范图由 `now_card` 从预设图库取；库里没有就整行不给 `image`。不要自己搜图。
- 已完成的动作 `done: true` 且 `selected: false`。
- 动作多时未完成优先、最多三行，其余在 `summary` 里带一句「还有 N 个动作」。
- 「改计划」是导航动作，只跳回原会话，不自动发送“我想调整”等占位文字。用户进入会话后再自然描述要怎么改。
- 「练了这些，帮我记上」是明确业务动作，保留 `send_prompt: 我练完了`。勾选臀桥和硬拉后会发送 `我练完了臀桥、硬拉`，收到后调用 `workout_done {"names":["臀桥","硬拉"]}`；只收到半句时追问具体动作，不按整张清单全记完。

## S3 健康日报

每天 22:00。跑 `now_card {"scene":"s3"}`，它会按 [reports.md](reports.md) 生成当天日报再决定发不发。

### S3 的 Now 卡

只有 `report_daily` 生成成功且回执带非空 `report_path` 才发；报告没生成、命令失败或缺 `report_path` 时不发，不能发一张点进去没有报告的空通知。`report_mode` 是 `partial` 也照发，正文把回执 `questions` 原样问出来。

封面图 + 一句话总结，不发选择卡，骨架照抄 [now-card-spec.md](now-card-spec.md) 第 3 节：`card_type: "image_text"`，`title` 写「今天的健康日报」，`summary` 写摄入、能量差额和最值得说的那条异常，数字取回执的 `intake_kcal` / `total_burn_kcal` / `balance_kcal`，`todoId` 用 `todo-s3-daily`。**卡上不放 HTML 链接也不放图表**：地址模型拿不到、拿到也只活两小时，图表 Now 卡画不了。HTML 文件本来就在会话里，卡的作用是把人领回会话。

## S4 健康周报

周日 22:00。跑 `now_card {"scene":"s4"}`，它会按 reports.md 生成本周周报再决定发不发；本周发布成功后本周不再重复。

### S4 的 Now 卡

只有 `report_weekly` 生成成功且回执带非空 `report_path` 才发；`sparse` 或没拿到 `report_path` 时不发，把回执 `summary` 讲出来即可。

跟 S3 同一张卡型，换成周口径：`title` 写「本周健康周报」，`summary` 写这一周的热量趋势和最值得留意的那条，`todoId` 用 `todo-s4-weekly`，按钮文案「看完整周报」。同样不放 HTML 链接、不放图表，HTML 周报在会话里。

## 收口与停止

- S1 / S2 / S3 每天都会有，Todo 长期保持 `PENDING`，不因某天发布成功就收口。
- 用户说某条场景不跟了：停该 Todo 名下全部规则，保留其他场景。改时刻就更新原规则，不删除重建；永久取消用 `trigger/delete_trigger`，明确成功后再从 Todo 快照移除对应 `rule_ids`。
- 用户给的期限到了：停该线规则，Todo 收口，发一条收尾动态。
- 没有业务证据不能把用户行动标成完成：练没练、拍没拍，判据只有对应的记录。
- 目标完成、用户取消之外，不要自己判定「他好像不需要了」就停规则。
