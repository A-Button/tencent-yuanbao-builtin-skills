---
name: websearch-watch
description: 用户希望持续关注天气、股票行情、新品发布等可通过网页搜索获取的信息，并在满足关注条件时通知或整理结果时使用。一次性查询直接 web_search，不必加载本技能。
metadata:
  version: v1.1
---

# websearch-watch 1.1

使用网页搜索持续关注用户指定的对象和条件。天气、股价、新品发布都使用同一套流程，不需要划分类型。

写入 Thing / Todo / Trigger 必须先 `load_skill(skill_name="make-things", skill_version="v1.0")`，再按 make-things 的创建顺序做。不要 load `yb-things`、`yb-weather`、`yb-stock-watch`、`weather-watch`、`stock-kline`、`westock-data`、`westock-tool`。不要 `create_timer`。取数只用当前对话已有的 `web_search`。

## 先确认再创建

缺的再问，齐了再写。没有用户确认不要创建。

1. **对象**：用户要关注的地点、公司或股票代码、产品或话题。
2. **条件**：按用户原话写清关注内容、阈值和时间范围，例如「上班时下雨」「股价大于 450」「公布正式售价和上市时间」。
3. **检查时间**：用户指定则跟。没说则用周期规则 `FREQ=DAILY`，`dtstart` 取下一个合理时刻（默认次日 08:00；用户说马上试，用数分钟后或最近整点）。用户没有指定结束时间时，不自行增加截止日期。分钟重复尚未确认，不要用大量单次规则模拟。需要每小时检查时写 `FREQ=HOURLY`，每 N 小时加 `INTERVAL`。

## 结构

**每个监控事项对应一条 Todo 和一条带 judge 的 Trigger。** 同一目标的多个关注对象可合在一个事项中。

| 项 | 值 |
| --- | --- |
| Todo `todo_id` | 为本事项预设稳定 ID，同一创建意图重试复用，不覆盖已有其他 Todo |
| Todo `status` | `IN_PROGRESS` |
| Todo `schedule_info` | `{ "kind": "MONITOR" }`，不要填 `time` |
| Todo `rule_ids` | 写入 `create_trigger` 回包的真实 `trigger_id` |
| Trigger `instruction` | 空字符串 `""`（有 judge 时必须空） |
| Trigger `enabled` | 创建时 `false`，Todo 写入后再 `update_trigger` 启用 |
| Trigger `timezone` | 默认 `Asia/Shanghai` |

`judge` 三个写入点（对应工具 schema，不要自造 `token` / `name` 字段）：

- **`judge.tool_call.tool_name`**：固定 `web_search`（网页搜索取数）。
- **`judge.tool_call.tool_arguments`**：只要 `{"query":["..."]}`。`query` 是字符串数组。搜索词包含对象、关注内容和时间范围，例如 `["深圳今天早高峰降雨预报"]`、`["腾讯控股 0700.HK 最新股价"]`、`["iPhone 18 iPhone Duo 官方发布 售价 上市时间"]`。
- **`judge.condition`**：根据取数结果判断是否命中的自然语言条件，写清对象、阈值和口径。调用失败、超时或异常结果不等于未命中。

**`judge.prompt` 写清命中后的具体工作：**

先用 `web_search` 复核该对象的最新信息，仅在本次结果仍支持用户条件时告知或整理结果。条件不满足、查询失败或证据不足时，不发送条件命中的提醒，不编造结果。把实际对象、条件和用户需要的内容写入 Prompt，不留占位词。

例如：天气提醒结合用户的通勤需求；股价提醒写明查到的价格和时间；新品发布整理用户关注的关键信息，并结合原来的换机或出售问题给出比较。投递只使用已有的 `web_search` 和文字回复，不要求再次 `load_skill`。

## 创建顺序

1. `load_skill(make-things, v1.0)`。
2. `get_thing` 查当前会话；按目标选择真实 Thing。需要新目标再 `create_thing`。`title` 用简短名称说明关注目标；`goal` 写对象、条件和检查节奏。不要写 `mcp_app_ids`。
3. 预设本事项的稳定 Todo ID，先不 `write_todos`。
4. `trigger/create_trigger`：`thing_id` 用回包、`todo_id` 用预设 ID、`enabled=false`、带完整 `judge`。周期规则 `trigger_kind=rrule`，`run_at=""`，`rrule` 不带 `RRULE:` 前缀；单次则 `trigger_kind=once`，`rrule=""`、`dtstart=""`。
5. `write_todos(merge=true)`：把回包 `trigger_id` 写入该 Todo 的 `rule_ids`，保留其他 Todo。
6. `trigger/update_trigger` 将该规则 `enabled=true`。

创建前可用 `web_search` 核对关注对象和信息；试跑即使像命中也不要提前通知。查不到就标明缺，不要用常识补数字。

## 修改与停止

改条件、对象或检查时间：先重读 Thing 和 Trigger，用 `write_todos` / `trigger/update_trigger` 改现有规则，不删除重建。用户叫停：先停用或删除 Trigger，再按 `make-things` 更新 Todo 状态；暂停或取消不标为完成。提醒发出、规则命中不等于 Todo 完成。持续命中是否去重尚未确认，不要承诺只通知一次。
