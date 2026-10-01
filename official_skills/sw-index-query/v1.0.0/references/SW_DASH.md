> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_DASH — 市场全景仪表盘

## 1. 概述

A 股全市场当日总览：31 个一级行业 + 4 个市场表征指数的涨跌 / 成交额 / 上涨家数。回答"今天市场怎么样 / 大盘 / 盘面总览 / 某板块今天表现"。支持历史日期快照。

## 2. 输入

```
sw_dashboard.py [--date YYYYMMDD] [--scope SCOPE]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--date` | 否 | 不传 | 历史日期快照（YYYYMMDD，如 `20260410`）。不传 = 实时快照 |
| `--scope` | 否 | `all` | 板块范围：`all` / `consumer` / `tmt` / `cyclical` / `finance` / `mfg` / `defensive` |

## 3. 输出

```json
{
  "status": "ok",
  "mode": "dashboard",
  "industries_count": 31,
  "up": 9, "down": 22, "total_amount": 24178.48,
  "top3":    [{"name":"通信","change_pct":4.19}, ...],
  "bottom3": [{"name":"食品饮料","change_pct":-2.10}, ...],
  "summary_text": "日期:...\n上涨行业: 9, 下跌行业: 22, 平盘: 0\n全市场成交额: 24178亿元\n..."
}
```

| 字段 | 含义 | Agent 使用要点 |
|------|------|---------------|
| `industries_count` | 参与统计的行业数（scope 过滤后） | 小板块回复时说"X 个行业"，别讲"31 个" |
| `up` / `down` / `flat` | 涨/跌/平数 | 回复必列 |
| `total_amount` | 全市场成交额（亿元） | 回复必列 |
| `top3` / `bottom3` | 领涨/领跌 | 引用具体名称 + change_pct |
| `summary_text` | 含 Top5/Bottom5 明细 + 日期 | agent 直接引用，不重新统计 |

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "今天市场怎么样" / "大盘表现" | `sw_dashboard.py` |
| "17号市场" / "4月10日大盘" | `sw_dashboard.py --date 20260410` |
| "上周五大盘" / "昨天盘面" | `sw_dashboard.py --date <具体YYYYMMDD>` |
| "金融板块全景" | `sw_dashboard.py --scope finance` |
| "消费板块今天表现" | `sw_dashboard.py --scope consumer` |

## 5. 已知坑 / 边界

- **小板块**（finance=3 / defensive=3 / mfg=4 / tmt=4）时，`top3` 和 `bottom3` 会出现**相同指数**（因样本太小），agent 只列一张排序表，不要分别列 top/bottom
- `scope` 仅支持上面 6 个预设；用户要 2-3 个具体指数对比 → 走 `sw_chart.py --mode compare`
- 只引用脚本/API 返回的数据日期和行情值；不要根据当前日期、成交额/成交量为 0 等改写行情状态
- "上周五" 等相对日期要先转为具体 YYYYMMDD（如今天是周六 4-18，"上周五"=`20260410`）
- 严禁 `--start X --end X`（那是 K 线参数，不是 dashboard）
