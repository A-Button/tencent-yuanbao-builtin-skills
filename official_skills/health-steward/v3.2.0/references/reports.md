# 健康日报 · 健康周报

日报周报出的是工作区里的 HTML 产物，不出卡：两张图表 A2UI 画不出来。判成功看回执里的 `report_mode`。`complete` 时回执带 `report_path`，那就是要交给用户的那一份。交文件只调一次 `present_files`，`files` 里只放这个路径的原文：

`present_files`，`files` 为 `["回执里的 report_path"]`

路径一个字都不要改，不要把连字符改成下划线，不要自己另起一个文件名。不要再调一次报告工具，也不要把路径贴进正文。不要自己编 `<media_info>`；`present_files` 的回执若要求终稿再写，路径必须与 `files` 里那条完全相同。`sparse` 没有文件，不要调 `present_files`。同一天的日报、同一周的周报文件名固定，只保留最后一份。

问健康日报或健康周报时，禁止调用 `diet_record`、`diet_estimate`、`diet_day`。这三个工具一调就会出饮食卡，先调了也收不回来。不要先调 `diet_day` / `workout_today` 去拼报告。报告成功后脚本会占住本轮卡槽，只能挡住之后才调的饮食工具，挡不住已经发出的那张卡。

生成报告的是脚本，不是你。只传日期：

- 日报：`report_daily {"date":"YYYY-MM-DD"}`
- 周报：`report_weekly {"date":"YYYY-MM-DD"}`，或改传 `week_start`（必须是周一）

脚本自己读库里已经记下的饮食和训练，再写出 HTML。不要先调 `diet_day`、`workout_today`、`body_expenditure`，也不要自己组一份报告数据交回去。不传日期直接报错，不会退回旧版报告。只传旧的五项摄入（kcal / 碳水 / 蛋白 / 脂肪 / 纤维）同样报错。

下面是脚本从库里取数的口径，用来读回执，不是让你先跑一遍再组装。

日报无论当天记录 0、1、2 或 3 餐、是否有训练，都输出同一份完整四段式模板。未记录餐次按 0 纳入“当前记录口径”；已记录食物和运动优先使用真实数值，缺失值按脚本内明确规则计算或兜底，并标注估算来源，最终页面不得出现“未知 kcal/分钟/km/配速”或“今天已记录的部分”。周报规则保持不变。

## 日报

### 脚本怎么取

传 `date` 之后这些都由脚本读库：

- 当天每一餐进 `meals[]`。没记下的餐次按 0 纳入当前记录口径。
- 已完成的训练进 `exercises[]`。排了但一个都没练完，就是空数组。
- 基础代谢、日常活动、身高体重和推荐区间能从档案里读到就填上，读不到按脚本里的兜底。

能量差额由 `report_daily` 算，你不要另算一遍。调用就这一次：`report_daily {"date":"YYYY-MM-DD"}`。`day_complete_confirmed` 不再控制模板分流；报告始终按当前记录生成完整格式。

### 回执怎么读

| `report_mode` | 你该做什么 |
|---|---|
| `complete` | 讲三个数：`intake_kcal` / `total_burn_kcal` / `balance_kcal`。调一次 `present_files`，`files` 里只放 `report_path` 原文，不要改文件名 |

## 周报

调用就这一次。脚本自己填这一周的七天，不要逐日调 `diet_day`。

脚本按这个口径填：

- `meals` 是 `{"breakfast":{"summary":…,"kcal":…},"lunch":…,"dinner":…}`。**没记录的餐次是 `null`**，不是 0 或空对象，周历会画成「暂无记录」。
- `nutrition` 是当天的 `protein_g` / `fat_g` / `carb_g`。
- `exercise_slots` 按 `noon` / `commute` / `evening` 三槽放当天已完成的运动，没有就是 `null`。
- 摄入和消耗缺一侧时，这天不进能量累计。

有效日由脚本判（≥2 餐，或 1 餐 + 1 条运动）。

报告工具读不到钠。要在正文里提钠，等报告生成之后再查 `diet_stats`。这一步不出卡。周报没有 `nutrition_flags` 这个入参。

周报只画已经记下的这一周，不收下一周的饮食或运动计划。用户要排下周时另说，不要写进 `report_weekly`。

### 回执怎么读

| `report_mode` | 你该做什么 |
|---|---|
| `complete` | 讲 `intake_kcal` / `total_burn_kcal` / `balance_kcal` / `valid_days`；回执带的 `calendar_prompt`（「要不要一键帮你同步到日历？」）只在对话正文里问，不写进 HTML、不塞进 Now 卡。调一次 `present_files`，`files` 里只放 `report_path` 原文 |
| `sparse` | 不满 3 个有效日，不出 HTML，把回执 `summary` 讲出来，不要调 `present_files` |

## 到点发的报告卡

22:00 的日报、周日 22:00 的周报直接跑 `now_card`（`scene` 为 `s3` 或 `s4`），不要再跑一遍 `report_daily` / `report_weekly`。脚本自己生成报告。`send` 为 true 时回执同时带 Now 卡和 `report_path`：把 `show_widget` 原样发出，再调一次 `present_files`，`files` 里只放这个路径的原文。不要改文件名。卡上放不了 HTML 链接也放不了图表，封面不要贴进正文，也不要放进 `present_files`。用户点「看完整日报」或「看完整周报」时，若上一轮已经交过同一份文件就不要再交；还没交就再调一次对应的报告工具，再按回执 `report_path` 调一次 `present_files`。文件名固定，不会多出一份。
