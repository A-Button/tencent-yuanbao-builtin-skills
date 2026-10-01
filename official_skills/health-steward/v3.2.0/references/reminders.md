# 提醒：创建、到点回调、四条场景

只建会发动态的四条线。护肤、选菜、睡眠本期没有能力，没有对应工具，别为它们建 Todo / Trigger。

Thing / Todo / Trigger / `show_widget` 用 make-things 的原生工具，调用方式见 SKILL.md：表里已有就直接调，没有就 `load_skill(make-things)` 一次。不要写成 `_run.py` 的参数，也不要把创建转交给子任务。

创建、修改、删除的字段名以刚加载的 make-things 及其 `references/create-update.md` 为准。创建是否完成看规则有没有启用成功，不看 Now 卡。`after_enable.send` 为 false，不要发卡。到点先跑 `now_card`：发不发、卡片长什么样由脚本算好。`send` 为 true 时把回执里的 `show_widget` 原样交给 `show_widget`，不要改字段、不要自己拼卡、不要搜图。

## 创建

一条提醒也先跑 `now_setup`，`scenes` 只放这一条，不要扩成四条，也不要自己写触发 prompt。prompt 用回执 `lines` 里的那句。用户要「每天按饮食自动生成或改训练计划」时，不要伪装成普通 S2，按 SKILL.md 的边界先问是否改为「先排训练，再每天提醒」。

整套提醒，或首次加载并收到长期提醒需求且还没有本 Skill 的 Thing、用户又没拒绝：先用 `ask_user_question` 让用户选类型与时刻。没有选择就四类全部按默认建；明确拒绝或只想看一次数据，不建。只要其中几条，就只建那几条。已有 Thing 时不再问、不重建，只补缺的项。

整套先跑一次 `now_setup`（必须带 `ONEAGENT_APP_CALLER=model`）。一条提醒同样先跑，`scenes` 只放要的那几条。回执的 `lines` 是意图：场景、本地时刻、标题、`prompt`、希望使用的 `preferred_todo_id`。按刚加载的 make-things 普通创建写进去。schema 不接受预设 id 时用回包 id，并把 scene 留在 prompt 里。schema 有 `mcp_app_ids` 时只填 `health-steward`，`goal` 写入回执里的那句。取钟按 make-things，不要把回执改写成 `dtstart` 或 `enabled: false`。没有这份回执不要创建。

创建不发 Now 卡。`after_enable.send` 为 false，新建、补规则、改时刻都一样。启用成功后直接回复用户，不要调 `show_widget`，也不要跑 `now_card` 的 `scene=created`。到点 prompt 用回执里的，不要改成自己拼 Now 图文卡。规则还没启用时正文只能写「已记下、尚未运行」，不能写「已开启」。`create_thing`、`write_todos`、`trigger/create_trigger`、`trigger/update_trigger` 返回错误时，必须把失败原因告诉用户，并给出下一步（稍后再试，或改一条再创建）。不能说成已经建好或已开启，也不要改用 delegate 或子任务再试。重试先重读 Thing 和规则，只补没成功的步骤。

| 线 | 标题 | 希望的任务标识 | 重复 | 默认时刻 |
|---|---|---|---|---|
| S1 拍三餐 | 三餐拍照提醒 | `todo-s1-meals` | 每天，早 / 午 / 晚各一条 | 08:30 / 11:30 / 17:30 |
| S2 今日训练 | 今日训练 | `todo-s2-train` | 每天 | 08:00 |
| S3 健康日报 | 健康日报 | `todo-s3-daily` | 每天 | 22:00 |
| S4 健康周报 | 健康周报 | `todo-s4-weekly` | 每周日 | 22:00 |

到点 prompt 统一是：加载 health-steward，重读当前 Thing，调用 `now_card`（S1 再带本餐 `slot`）。`send` 为 false 不调 `show_widget`；为 true 就把回执里的 `show_widget` 原样交给 `show_widget`。S2 的 prompt 还要写明：只展示已经排好的当天训练，不要根据前一天饮食生成新计划。不要用 create_timer、番茄钟或逐轮建 DELAY。

## 四条规则（唯一会发动态的）

状态都在 App 持久卷里，只能经 bash 读，规则不带 judge。到点后由你自己读状态再决定发不发。

| 规则 | 重复 | 默认时刻 | 到点做什么 | 什么时候发 |
|---|---|---|---|---|
| S1 拍三餐提醒 | 每天三条 | 早 08:30 / 午 11:30 / 晚 17:30 | `now_card`，scene=s1，slot 对应该餐 | 本餐还没记录、也没跳过才发 |
| S2 今日训练 | 每天 | 08:00 | `now_card`，scene=s2 | 有未完成的动作才发。不在回调里生成新计划 |
| S3 健康日报 | 每天 | 22:00 | `now_card`，scene=s3 | 拿到 `report_path` 才发 |
| S4 健康周报 | 每周日 | 22:00 | `now_card`，scene=s4 | 拿到 `report_path` 才发 |

S2 的能力边界是“提醒并展示已经排好的当天训练”，不是无人值守地根据前一天饮食和训练记录自动生成一套新计划。用户要求“每天自动生成/动态调整计划”时，不得伪装成普通 S2 提醒创建，也不得 delegate；应简短说明当前只支持先排训练再定时提醒，并询问是否改为这个方案。

表里「发」一律指用 `show_widget` 出一张 Now 卡，**不是在对话里写一段提醒话术**。到点命中且有内容时发卡是默认动作，不需要用户再点头；只有上表写明的那几种情况才允许安静。用正文顶替发卡，用户手机上收不到任何东西，而且回包里没有 `now_id`，不能对他说已经提醒过。

## 回调

1. 只信任宿主提供的本轮规则身份，用 `get_thing`、必要时 `trigger/list_triggers` 重读。Todo 已完成、已暂停、条件已改或规则不再绑定时，不执行旧任务。
2. 跑 `now_card`，`scene` 和 `slot` 用规则 instruction 里写的那一对。读取失败、超时、字段缺失都是失败，不等于没有新进展。
3. `send` 为 false 就停，不要调 `show_widget`。为 true 就把回执里的 `show_widget` 原样交给宿主的 `show_widget`，不要改字段。
4. 发布不幂等：超时、连接中断或回包缺失都不要自动重试，也不要改改标题重发，如实说结果未确认。回包带真实 `now_id` 才记为已发布。

调用 `now_card` 时，`thing_id` 用 `get_thing` 回执里的真实 ID，`todo_id` 用本条规则上的那一条。平台不按内容去重：同一天同一餐再调一次 `show_widget` 就是再发一张，所以发之前只信 `now_card` 的 `send`。

## S1 拍三餐提醒

| 餐次 | meal key | 默认提醒时刻 |
|---|---|---|
| 早餐 | `breakfast` | 08:30 |
| 午餐 | `lunch` | 11:30 |
| 晚餐 | `dinner` | 17:30 |

到点跑 `now_card {"scene":"s1","slot":"<本餐>"}`。本餐已记录或已跳过，回执 `send` 为 false，这次不发。用户改作息时三条时刻一起改，写进 `Thing.goal`，并用 `now_setup` 的 `times` 重算规则。

### S1 的 Now 卡

卡由 `now_card` 填好，原样发出。用推荐列表 `recommend_list`，不要用 `todo_choice`，这张卡没有勾选框，也不要写 `selected`、`done` 或 `select_mode`。只列这一次提醒的那一餐，不要把另外两餐也列上。这一行带着预设占位图，图只留在 Now 卡的 `image` 上。不要搜图，不要画图，也不要把这张图写进主对话：不要贴进正文，不要写 `<media_info>`，不要调 `image_generation`。禁止把 `show_widget` 参数、回执或历史里的 `image` 地址抄进正文、`<media_info>`、`present_files` 或 `photoUrl`。主对话只看回执里的 `chat_note`。这一行和「去记录」「不吃了」两个按钮缺一不可，两个按钮都带完整一句上屏，不许退化成纯文字提醒卡，也不要自己改 `title` 或 `desc`。

按钮上的话已经是完整一句，推荐列表不会再拼接餐次名：

- 收到「这是我今天的午餐」（早餐、晚餐换成对应餐次）：这条消息里还没有食物、也没有图时，不要 `diet_record`，不要编「午餐（待确认）」这类占位，不要出卡。请用户拍一张或说出吃了什么。下一句有图或有真实菜名再记；有图必须把用户本轮刚上传的图片地址放进 `photoUrl`，那一轮才出饮食卡。Now 卡和历史里 `show_widget` 的 `image` 地址禁止当作 `photoUrl`。
- 收到「今天不吃午餐」就立刻调用 `diet_skip`。

点完之后这张 Now 卡不会改勾选，也不会变成已记录。对话里记上或跳过，要等下一次到点由 `now_card` 决定还发不发。

## S2 今日训练

每天 08:00 到点跑 `now_card {"scene":"s2"}`：没有排期、排期里没有动作、或动作都已经完成时，`send` 为 false，不发。还有未完成的动作才用回执里的卡。训练建议照抄 `workout_today`，练完后的消耗由 22:00 的日报计入。

### S2 的 Now 卡

卡由 `now_card` 填好，原样发出。用推荐列表 `recommend_list`，不要用 `todo_choice`，这张卡没有勾选框。未完成的动作全部一行一个，带示范图，不要截成三行；已完成的不列进行里。动作行加「去记录」「改计划」两个按钮缺一不可，不许退化成纯文字卡。不要自己改行，也不要搜图。

收到按钮回传后再处理：

- 「去记录」上屏的句子已经带上卡上未完成的动作名。收到「我今天练了这些：臀桥、硬拉」就调用 `workout_done {"names":["臀桥","硬拉"]}`，成功后只回一句，不出卡。没动作名、只收到 `我今天练了这些：` 时追问具体动作，不按整张清单全记完。不要再把动作名接到这句后面。
- 「改计划」上屏「我想调整今天的训练计划」。这句话还没说改哪一项，先问要改哪个动作、改组数次数还是负重，再调 `workout_adjust`。不要当成练完。

点下去只是把这句话送进对话。这张 Now 卡不会跟着改勾选，也不会把动作标成已完成。对话里记完训练，不会写回这张卡。

## S3 健康日报

每天 22:00。跑 `now_card {"scene":"s3"}`，它会按 [reports.md](reports.md) 生成当天日报再决定发不发。

### S3 的 Now 卡

`now_card` 自己读库生成当天日报。生成成功且脚本内部确认写到了文件（`report_path`）才发；没有这份文件时 `send` 为 false，不发。`send` 为 true 时回执带 `report_path`。同一轮做完两件事：把 `show_widget` 原样发出，再调一次 `present_files`，`files` 里只放这个路径的原文。不要编文件名，不要再跑 `report_daily`，不要把封面贴进正文，也不要把封面放进 `present_files`。

卡是图文卡，标题「今天的健康日报」，按钮「看完整日报」，关联 `todo-s3-daily`。点整卡或按钮都跳回原会话，并上屏「我要看今天的健康日报」。若这一轮还没把文件交出去，收到这句就再调一次 `report_daily`，只传当天日期，再按回执 `report_path` 调一次 `present_files`。文件名固定，不会多出一份。不要出饮食卡，禁止调用 `diet_record`、`diet_estimate`、`diet_day`。不要自己改 `summary`，卡上不放 HTML 链接也不放图表。

## S4 健康周报

周日 22:00。跑 `now_card {"scene":"s4"}`，它会按 reports.md 生成本周周报再决定发不发；本周发布成功后本周不再重复。

### S4 的 Now 卡

`now_card` 自己读库生成本周周报。生成成功且脚本内部确认写到了文件（`report_path`）才发；`sparse` 或没有这份文件时不发，把回执 `summary` 讲出来，不要调 `present_files`。`send` 为 true 时回执带 `report_path`。同一轮把 `show_widget` 原样发出，再调一次 `present_files`，`files` 里只放这个路径的原文，不要再跑 `report_weekly`。收到「我要看本周的健康周报」且这一轮还没交文件时，再调一次 `report_weekly`，再按回执 `report_path` 调一次 `present_files`。

标题「本周健康周报」，按钮「看完整周报」，关联 `todo-s4-weekly`。点整卡或按钮都跳回原会话，并上屏「我要看本周的健康周报」。收到这句就按上面再调一次 `report_weekly`，把 `report_path` 原样交出去。不要再出饮食卡，禁止调用 `diet_record`、`diet_estimate`、`diet_day`。不要自己改 `summary`，卡上不放 HTML 链接也不放图表。同一周只有一份 HTML。

三餐卡和训练提醒只覆盖当天这一次。该餐已经记下或跳过、当天没有未完成的动作时，`send` 为 false，不再发。协议里没有「次日销毁」字段，也没有把单个按钮置灰的字段。不要自己加过期时间或按钮禁用字段。点完 Now 卡不会写回这张卡。

## 收口与停止

- S1 / S2 / S3 每天都会有，Todo 长期保持 `PENDING`，不因某天发布成功就收口。
- 用户说某条场景不跟了：按刚加载的 make-things 停该条任务名下的规则，保留其他场景。改时刻就更新原规则，不删除重建。永久取消也按那份说明书删规则并去掉任务上的引用。
- 用户给的期限到了：停该线规则，Todo 收口，发一条收尾动态。
- 没有业务证据不能把用户行动标成完成：练没练、拍没拍，判据只有对应的记录。
- 目标完成、用户取消之外，不要自己判定「他好像不需要了」就停规则。
