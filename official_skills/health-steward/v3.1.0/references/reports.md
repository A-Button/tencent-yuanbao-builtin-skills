# 健康日报 · 健康周报

日报周报出的是工作区里的 HTML 产物，不出卡：两张图表 A2UI 画不出来。判成功只看回执里的 `report_path`。

`report_daily` / `report_weekly` 收两种入参，同时给时以 `report_data` 为准：

- `{"date":"YYYY-MM-DD"}`：脚本自己读这一天（周报则是这一周）的饮食和训练记录来组装。周报也可以改传 `week_start`（必须是周一）。
- `{"report_data":{…}}`：你已经组好了就走这条。字段定义以 [health-report-v1.0/api_reference.md](health-report-v1.0/api_reference.md) 为准，完整样例在同目录 `cases/01_daily_complete.json`（日报）和 `cases/03_weekly_complete.json`（周报）。

两个都不传直接报错，不会退回旧版报告。只传旧的五项摄入（kcal / 碳水 / 蛋白 / 脂肪 / 纤维）同样报错。下面的取数顺序是你要自己组 `report_data` 时用的；传 `date` 就不用再跑一遍。

**取不到的一律填 `null`，不要编一个看着合理的默认值。** 数据不全不是失败：日报会出降级页并给追问，周报不满 3 个有效日就不出 HTML 只给小结。不要为了凑出完整报告去补造餐次、活动量或体重。一条 bash 只跑一个 `_run.py`，按下面的顺序一条一条跑。

## 日报

### 取数顺序

1. `diet_day '{}'`：当天每一餐的 `label`、`time`、`foods`、`kcal`、`protein_g`、`fat_g`、`carb_g`、`sodium_mg` 都在回执里，直接组 `report_data.meals[]`。`foods` 拆成 `[{name, portion}]`；`scene` / `signal` 你照记录写一句，只基于数据，不要编。
2. `body_expenditure '{}'`：`bmr` → `bmr_kcal`，`daily_activity` → `daily_activity_kcal`。`daily_activity_estimated` 为 true 时 `daily_activity_source` 写 `steps_estimate`，否则写 `connector`，取不到写 `unknown`。`missing` 里有 `body_profile` 说明档案没建，这两项只能是 `null`。
3. `workout_today '{}'`：`today.session.exercises` 里已完成的动作进 `report_data.exercises[]`。没有排期或一个都没练，`exercises` 就是空数组。
4. `body_profile '{}'` 取身高、体重、年龄、性别填 `profile`；四个 target 取 `nutrition_summary` 返回的推荐区间，取不到填 `null`。
5. `report_daily '{"report_data":{…}}'`。全天是否记完靠 `day_complete_confirmed`：用户没确认过就填 `false`，让报告自己降级。

能量差额由 `report_daily` 算，你不要另算一遍。

### 回执怎么读

| `report_mode` | `report_path` | 你该做什么 |
|---|---|---|
| `complete` | 有 | 讲三个数：`intake_kcal` / `total_burn_kcal` / `balance_kcal`，提一句报告已生成 |
| `partial` | 有（降级页） | 正常产物，把回执 `questions` 里的追问原样问出来，最多 3 条 |
| `no_data` | `null` | 报告没生成，用回执 `prompt` 邀请用户讲讲今天吃了什么、动了什么，不要说报告出好了 |

## 周报

`week_start` 是本周一、`week_end` 是本周日，两者必须正好差 6 天。七天逐日 `diet_day '{"date":"2026-09-14"}'`，每天组一条 `days[]`：

- `meals` 是 `{"breakfast":{"summary":…,"kcal":…},"lunch":…,"dinner":…}`，`summary` 用那餐的食物名拼一句。**没记录的餐次填 `null`**，不要填 0 或空对象，周历会画成「暂无记录」。
- `nutrition` 是当天的 `protein_g` / `fat_g` / `carb_g`，取回执里的 `totals`。
- `exercise_slots` 按 `noon` / `commute` / `evening` 三槽放当天运动，没有就 `null`。
- `intake_kcal` / `bmr_kcal` / `daily_activity_kcal` / `active_kcal` / `total_burn_kcal` 口径同日报。摄入和消耗只要缺一侧，这天就不进能量累计，两个都别硬凑。

有效日由脚本判（≥2 餐，或 1 餐 + 1 条运动，或你显式给 `is_valid_day: true`）。

报告工具读不到钠。先 `diet_stats '{"period":"week"}'` 查本周统计，钠连续偏高就写进正文，周报没有 `nutrition_flags` 这个入参。

`next_week_plan.days[]` 可选，给了就渲染成第三张周历（早餐 / 午餐 / 晚餐 / 顺手运动 / 目标差值）。份量只写「1 条、1 个、1 小碗、150g、250ml」这类自然单位，**不要写「一掌、一拳、半拳」**。没想好下周吃什么就整段不传，不要填占位。

### 回执怎么读

| `report_mode` | `report_path` | 你该做什么 |
|---|---|---|
| `complete` | 有 | 讲 `intake_kcal` / `total_burn_kcal` / `balance_kcal` / `valid_days`；回执带的 `calendar_prompt`（「要不要一键帮你同步到日历？」）只在对话正文里问，不写进 HTML、不塞进 Now 卡 |
| `sparse` | `null` | 不满 3 个有效日，不出 HTML，把回执 `summary` 讲出来 |

## 到点发的报告卡

22:00 的日报、周日 22:00 的周报先按上面生成，拿到 `report_path` 才发 Now 卡；卡的写法见 [reminders.md](reminders.md) 的 S3 / S4 和 [now-card-spec.md](now-card-spec.md) 第 3 节。卡上放不了 HTML 链接也放不了图表，HTML 文件本来就作为附件出现在会话里。
