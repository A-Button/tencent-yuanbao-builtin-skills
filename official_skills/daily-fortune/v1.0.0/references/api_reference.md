# daily-fortune API 参考

统一入口：`app daily-fortune daily_fortune '<json>'`。入参顶层平铺，不套 `payload`。
输出为结构化 JSON（含 `phase`、`facts`、`data`、`confidence`、`warnings`、`source`、`audit`、`disclaimer`），
界面与 Agent 消费同一份 `structuredContent`。

本技能**只有出卡能力**：没有订阅、没有推送，也不写任何个人数据文件。

## 通用返回

```jsonc
{
  "phase": "result",
  "data": {
    "subject": "self",
    "timekey": "today",       // today | week | month | year
    "topickey": "career",     // career | love | wealth | social
    "target_date": "2026-09-10",
    "card": { /* 见下；缺档案时为 null */ },
    "needs_profile": false,
    "profile_message": "",
    "card_error": "",
    "message": "这是你的运势卡片"
  }
}
```

`data.card` 结构：

| 字段 | 说明 |
|---|---|
| `score` | `{value, scale:"45–88", label}` |
| `keyword` | `{label, value, desc}` |
| `overview` | 重点概述 |
| `lucky` | `{color, colorHex[], time, timeGlyph, direction, directionGlyph, number, numberGlyph, food, foodGlyph, accessory, accessoryGlyph}` |
| `advice` | `{do, avoid}` |
| `insight` | `{title, body, meta}` |
| `transit` | `{yearGanZhi, monthGanZhi, dayGanZhi, anchorGanZhi, timekey}` |
| `bazi` | `{dayMaster, dayMasterElement, pillars}` |
| `evidence` | 评分依据数组 |

## get_card

出卡。可选 `subject`、`target_date`、`timekey`、`topickey`。
缺档案时返回 `needs_profile=true` 与 `profile_message`，`card` 为 `null`。

## describe

返回操作契约、时间维度、主题与档案读取位置。无必填参数。

## 错误信封

```jsonc
{ "phase": "error", "code": "INVALID_ARGUMENT", "message": "缺少 operation", "retryable": false }
```

业务错误码：`INVALID_ARGUMENT`、`INVALID_JSON`、`UNKNOWN_OPERATION`、`RUNTIME_UNAVAILABLE`、
`ENGINE_FAILED`、`INVALID_ENGINE_OUTPUT`、`CALCULATION_FAILED`、`ENGINE_CRASH`。
CLI 层另有 `SKILL_NOT_FOUND`、`UNKNOWN_TOOL`、`FORBIDDEN` 等，业务码不与它们重名。

## 存储位置

- 出生档案（只读）：`~/.one-agent/metaphysics-profile/profiles.json`
- 本技能不写任何文件

## 计算口径

- 八字：`@mingora/bazi`（真太阳时、节气换柱、十神、五行占比）
- 流期干支：`lunar-javascript`（年/月/日柱）
- 评分：版本化五行互动规则（45–88），非预测
- 时间维度锚点：today→日干；week→按星期几在日干上偏移出"周干"；month→月干；year→年干（流年）
- 喜用：日主之"印"（生助日主之五行），用于推导幸运色/方位/数字/时段/食物/配饰
