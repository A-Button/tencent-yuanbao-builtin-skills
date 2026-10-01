---
name: task-schedule
description: 用于管理用户的定时/例行任务，包括查看、创建、更新、删除、暂停和重启任务。
---

# 任务管理（task-schedule）

通过 `manage_task_tool` 统一管理定时/例行任务。

## 操作类型

| operation | 用途 | 必填参数 |
|-----------|------|---------|
| `add` | 新建任务 | task_title, task_content, start_date, is_repeat |
| `update` | 修改已有任务（支持部分字段） | task_id |
| `delete` | 删除任务 | task_id |
| `pause` | 暂停任务（停止触发，不删除） | task_id |
| `resume` | 重启已暂停的任务 | task_id |

## 决策流程

1. **用户要查看任务** → 不需要调工具，直接从下方 `** 当前task列表 **` 中读取并回复。
2. **用户要新建任务** → `add`。
3. **用户要修改任务** → 先从当前 task 列表中匹配 task_id，再 `update`。只传需要修改的字段，不传的字段保持原值。
4. **用户要删除/暂停/重启** → 先从当前 task 列表中匹配 task_id，再执行对应 operation。
5. **列表中找不到目标任务** → 直接文本告知用户「未找到该任务」，不要调用工具。

## 参数填写规则

### task_title
精准概括任务核心意图，风格简洁，如「每日Keep提醒」「周五周报生成」「生日祝福」。

### task_content
仅保留**核心执行指令**，剔除时间/日期/周期等信息。
- 用户说「每天早上8点提醒我喝水」→ task_content = "提醒喝水"
- 用户说「每周五下午5点生成周报」→ task_content = "生成周报"

### 时间参数

**优先级：start_time > fuzzy_time**

| 用户表述 | start_date | start_time | fuzzy_time |
|---------|-----------|-----------|-----------|
| "明天早上8点" | 明天日期 | 08:00:00 | 不填 |
| "下周一上午" | 下周一日期 | 不填 | forenoon |
| "每天晚上" | 今天日期 | 不填 | night |
| "3月15号" | 2026-03-15 | 不填 | 不填 |

**关键规则：**
- `start_date` 格式 `YYYY-MM-DD`，无明确日期时默认**今天**。
- `start_time` 格式 `HH:MM:SS`，能提取精确时间时填写，否则留空。
- `fuzzy_time` 仅当无法提取精确 `start_time` 时才使用，可选值：`morning`(早晨)、`forenoon`(上午)、`noon`(中午)、`afternoon`(下午)、`evening`(傍晚)、`night`(晚上)、`midnight`(凌晨)、`early_morning`(清晨)、`all_day`(全天)。
- 如果提取的时间**早于当前时间**且用户**未指定具体日期**，`start_date` 自动顺延至明天。
- 当前时间参考 `meta_info.current_time`。

### 重复任务参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `is_repeat` | 是否重复，单次任务填 false | true |
| `repeat_cycle` | 重复周期：daily/weekly/monthly/yearly | "weekly" |
| `interval` | 间隔数，默认1。如「每两周」→ interval=2, repeat_cycle="weekly" | 2 |
| `by_WeekDay` | 每周哪几天（0=周日, 1=周一, ..., 6=周六） | [1,3,5] → 周一三五 |
| `by_MonthDay` | 每月哪几号（1-31） | [1,15] → 每月1号和15号 |
| `by_Month` | 哪几个月（1-12） | [3,6,9,12] → 每季度 |
| `cycle_end_date` | 重复截止日期 `YYYY-MM-DD` | "2026-12-31" |

**常见组合：**
- 「每天早上8点」→ is_repeat=true, repeat_cycle="daily", start_time="08:00:00"
- 「每周一三五下午3点」→ is_repeat=true, repeat_cycle="weekly", by_WeekDay=[1,3,5], start_time="15:00:00"
- 「每月15号」→ is_repeat=true, repeat_cycle="monthly", by_MonthDay=[15]
- 「每两周一次」→ is_repeat=true, repeat_cycle="weekly", interval=2
- 「明天下午3点（仅一次）」→ is_repeat=false, start_date=明天, start_time="15:00:00"

## 约束与边界

以下情况**不调用工具**，直接用文本回复用户进行婉拒或引导：

- **周期小于天**（如「每小时」「每30分钟」）→ 告知暂不支持小时级以下的周期任务。
- **任务数已达上限**（当前列表 ≥ 10 条）→ 建议用户先清理已有任务。
- **触发条件不是明确时间**（如「天气变冷时提醒我」「股价跌破100时通知」）→ 告知仅支持基于时间的定时任务。
- **涉及农历或节假日**（如「每年春节」「中秋节前一天」）→ 需要先通过搜索工具获取对应的公历日期，再创建任务。

## 回复风格

- 创建/更新成功后，用简洁自然的语言确认任务详情（标题、执行时间、是否重复）。
- 删除/暂停/重启成功后，简要确认操作结果。
- 遇到歧义时主动追问，不要猜测用户意图。例如用户说「改一下那个任务」但列表有多个任务时，应列出并请用户指定。
