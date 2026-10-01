> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_RISK — 收益风险矩阵

## 1. 概述

行业指数的年化收益率 × 年化波动率散点 + **收益风险比**（`y1_return / y1_vol`）排名。回答"行业风险收益 / 哪个行业性价比高"。

## 2. 输入

```
sw_risk_matrix.py [--scope SCOPE] [--codes a,b,c]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--scope` | 否 | `all` | `all` / `consumer` / `tmt` / `cyclical` / `finance` / `mfg` / `defensive` |
| `--codes` | 否 | — | 自定义代码（逗号分隔），**传入则覆盖 `--scope`** |

## 3. 输出

```json
{
  "status": "ok",
  "mode": "risk_matrix",
  "industries_count": 31,
  "top3": [
    {"name":"通信","ratio":2.7541},
    {"name":"有色金属","ratio":2.4134},
    {"name":"综合","ratio":2.3617}
  ],
  "bottom3": [
    {"name":"家用电器","ratio":-0.1781},
    {"name":"美容护理","ratio":-0.4433},
    {"name":"食品饮料","ratio":-0.6939}
  ],
  "summary_text": "共31个行业的年化收益/风险数据\n收益风险比最高: 通信(2.75), ...\n收益风险比最低: ...\n均值收益率: 21.91%\n均值波动率: 23.56%"
}
```

| 字段 | 含义 |
|------|------|
| `ratio` | 收益风险比 = 年化收益 / 年化波动率（越高性价比越好） |
| `top3` / `bottom3` | ratio 排序头尾 3 条 |
| `summary_text` | 含 top5 / bottom5 + 均值收益 + 均值波动 |

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "行业风险收益排名" / "哪个行业性价比高" | `sw_risk_matrix.py` |
| "TMT 风险收益" / "消费板块收益风险" | `sw_risk_matrix.py --scope tmt` |
| "基础化工和电子的收益风险对比" | `sw_risk_matrix.py --codes 801030,801080` |

## 5. 已知坑 / 边界

- `ratio` 不是 Sharpe（没扣无风险利率）。用户问"Sharpe 排名"要走 `sw_rank.py --sort sharpe`
- 波动率为 0 时 ratio 为 `null`（极少数异常数据）
- 与 `sw_rank.py` 区别：RANK 是**多指标排名**（YTD/Calmar/Sharpe 等），本脚本仅按"收益/波动"单指标 + 含散点图维度
- 小板块（<5 行业）散点图退化；建议提醒用户"行业较少，建议直接看排序表"
