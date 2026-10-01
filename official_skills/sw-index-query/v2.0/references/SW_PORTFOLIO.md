> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_PORTFOLIO — 指数级加权组合聚合

## 1. 概述

按指定权重聚合 2+ 个指数为一个虚拟组合，计算组合累计/年化收益 / 波动 / Sharpe / Calmar / MDD，以及（可选）vs 基准的 Beta/α/超额。回答"30% 电子 + 40% 申万300 + 30% 银行 组合 YTD 多少"。

**⚠️ 仅处理指数级加权组合**（权重 = 占比小数）。如用户给"**个股 + 股数 + 买入日**"（如"1月5日买入招行1000股"），**不走本脚本**——通过 WorkBuddy 通用金融数据能力处理（`neodata-financial-search` 取个股行情/财务 + adhoc 计算，或 WebSearch / 金融 Connector）。

## 2. 输入

```
sw_portfolio_agg.py --codes a,b,c --names A,B,C --weights 0.3,0.4,0.3
                    [--days N] [--benchmark BC] [--bench-name BN]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--codes` | 是 | — | 逗号分隔指数代码 |
| `--names` | 否 | 自动 | 逗号分隔名称（与 codes 对齐） |
| `--weights` | 是 | — | 逗号分隔权重。和应 ≈ 1（`0.3,0.4,0.3`）或 ≈ 100（`30,40,30`，脚本自动归一化） |
| `--days` | 否 | `250` | 回溯交易日 |
| `--benchmark` | 否 | 无 | 可选基准代码，加了会算 Beta/α/超额 |
| `--bench-name` | 否 | 自动 | 基准名 |

## 3. 输出

```json
{
  "status": "ok",
  "mode": "portfolio_agg",
  "components": [
    {"code":"801080","name":"电子","weight":0.3,"cum_return":19.4,"annual_return":24.1,"annual_vol":28.5},
    {"code":"801300","name":"申万300","weight":0.4,"cum_return":12.3,"annual_return":15.2,"annual_vol":19.8},
    {"code":"801780","name":"银行","weight":0.3,"cum_return":3.9,"annual_return":4.2,"annual_vol":15.1}
  ],
  "window": "2025-04-20 ~ 2026-04-18",
  "effective_days": 243,
  "cum_return": 11.7, "annual_return": 14.3, "annual_vol": 18.2,
  "sharpe": 0.68, "calmar": 1.21, "max_drawdown": -11.8,
  "vs_benchmark": {
    "benchmark":"801003","bench_name":"申万A指",
    "beta":0.92, "alpha_annual_pct":2.1,
    "port_cum":11.7,"bench_cum":9.6,"excess_return":2.1
  },
  "summary_text": "组合: 电子(30%), 申万300(40%), 银行(30%)\n窗口: 2025-04-20 ~ 2026-04-18（243 日）\n组合累计收益: 11.70%  |  年化 14.30%  |  年化波动 18.20%\n风调后: Sharpe 0.68（rf=2%）  |  Calmar 1.21  |  最大回撤 -11.80%\nvs 申万A指: Beta 0.92  |  年化α 2.10%  |  累计超额 2.10%"
}
```

| 字段 | 含义 |
|------|------|
| `components[]` | 各成分指数及其单独收益/波动 |
| `cum_return` / `annual_return` | 组合的累计 / 年化收益 % |
| `annual_vol` | 组合年化波动率 % |
| `sharpe` / `calmar` / `max_drawdown` | 风调指标 |
| `vs_benchmark` | 可选，只有传了 `--benchmark` 才有 |

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "30% 电子 + 40% 申万300 + 30% 银行 组合 YTD" | `sw_portfolio_agg.py --codes 801080,801300,801780 --names 电子,申万300,银行 --weights 0.3,0.4,0.3` |
| "同上组合 vs 申万A指" | 加 `--benchmark 801003 --bench-name 申万A指` |
| "消费 50% + TMT 50% 组合近 1 年" | `sw_portfolio_agg.py --codes 801260,801080 --names 申万消费,电子 --weights 0.5,0.5` |
| "等权 5 行业组合" | `sw_portfolio_agg.py --codes 801780,801080,801150,801260,801300 --weights 0.2,0.2,0.2,0.2,0.2` |

## 5. 已知坑 / 边界

- **仅接受权重（百分比占比）**，不接受股数/金额。用户给股数 → 走 WorkBuddy 通用金融数据能力（`neodata-financial-search` + adhoc 计算 / WebSearch / 金融 Connector）
- 权重和必须 ≈ 1（小数）或 ≈ 100（百分数）。脚本容忍 5% 偏差；否则报错
- `--codes` 2+ 个必填；单个指数走 `sw_stats.py`
- 共同交易日 < 30 时报错（某些指数上市晚）
- 组合按"每日按权重线性加权"模拟，**不是**"初始买入不再调仓"
- 与 `sw_corr_matrix.py` 区别：CORR 是"两两相关"；本脚本是"组合整体表现"
- 与 `sw_rank.py` 区别：RANK 是"多指数排名"；本脚本是"N 指数合成为 1 个虚拟组合"
