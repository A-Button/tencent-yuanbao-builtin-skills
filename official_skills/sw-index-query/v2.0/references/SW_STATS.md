> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_STATS — 单指数全指标快照

## 1. 概述

单一指数的全部关键指标一次返回：年化收益、年化波动、Sharpe、Calmar、最大回撤、**日/月/年胜率**、多周期收益（YTD/近 1/3/5 年）、估值（PE/PB/股息率/换手率/流通市值）。回答"算一下 XX 指数的 年化 / 波动 / 胜率 / Sharpe / Calmar / MDD"。

## 2. 输入

```
sw_stats.py --code CODE [--name NAME] [--days N] [--benchmark BCODE]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--code` | 是 | — | 6 位申万指数代码 |
| `--name` | 否 | 空 | 展示名 |
| `--days` | 否 | `1250`（5 年） | K 线回溯根数 |
| `--benchmark` | 否 | — | 可选基准代码（保留扩展） |

## 3. 输出

```json
{
  "status": "ok",
  "mode": "stats",
  "code": "801780", "name": "银行",
  "stats": {
    "window_days": 1216, "range": "2021-04-19~2026-04-18",
    "annual_return": 5.20,  "annual_vol": 15.14,
    "sharpe": 0.21,  "calmar": 0.47,  "max_drawdown": -11.16,
    "win_rate_day": 52.40,  "win_rate_month": 61.70,  "win_rate_year": 80.00,
    "m1_return": 3.93, "m3_return": -3.51, "ytd_return": -3.51,
    "y1_return": 1.22, "y3_return": 2.85, "y5_return": 4.10,
    "y1_vol": 15.14, "y3_vol": 16.60, "y5_vol": 17.20,
    "pe": 6.14, "pb": 0.52, "dp": 5.16, "turnover": 0.79, "circ_mcap": 25071.17
  },
  "summary_text": "指数: 银行(801780) | 窗口: 2021-04-19 ~ 2026-04-18（1216根K线）\n收益：年化 5.20%  |  近1年 1.22%  | ...\n风险：年化波动 15.14%  |  最大回撤 -11.16%\n风调后：Sharpe 0.21（rf=2%）  |  Calmar 0.47\n胜率：日 52.40%  |  月 61.70%  |  年 80.00%\n估值：PE 6.14  |  PB 0.52  |  股息率 5.16%  |  换手率 0.79%  |  流通市值 25071.17亿"
}
```

| 字段 | 含义 |
|------|------|
| `annual_return` / `annual_vol` | 从 K 线算的年化收益 / 波动 |
| `sharpe` | `(年化收益 - 2%) / 年化波动` |
| `calmar` | `年化收益 / \|最大回撤\|` |
| `max_drawdown` | 窗口内最大回撤（负值 %） |
| `win_rate_day` / `_month` / `_year` | 日/月/年胜率（上涨期数/总期数，%） |
| `m1/m3/ytd/y1/y3/y5_return` | API 返的区间收益 |
| `pe/pb/dp/turnover/circ_mcap` | 基本面字段（日级快照） |
| `summary_text` | 格式化全量展示 — **agent 直接引用** |

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "算一下申万银行指数的年化收益率、年化波动率、Sharpe、Calmar、最大回撤、日胜率" | `sw_stats.py --code 801780 --name 银行` |
| "申万50 的全指标" / "申万50 所有统计" | `sw_stats.py --code 801001 --name 申万50` |
| "电子指数近 3 年统计" | `sw_stats.py --code 801080 --name 电子 --days 750` |
| "申万300 近 10 年胜率" | `sw_stats.py --code 801300 --name 申万300 --days 2500` |

## 5. 已知坑 / 边界

- 默认 `--days 1250` ≈ 5 年。过短（<30）脚本会报错"K 线不足"
- `win_rate_day` 要 ≥30 根 K 线才计；`win_rate_month` 要 ≥2 月；`win_rate_year` 要 ≥2 年
- `sharpe` 使用 **2% 固定无风险利率**，不是动态国债利率
- `calmar` 用"年化收益 / |MDD|"；MDD 过小（<0.01%）时 calmar=null
- 基本面字段（PE/PB/dp/turnover）来自日级 API，盘中非实时（盘中问估值不会看到当日变化）
- 与 `sw_rank.py` 区别：RANK 是**横向排名**（多指数对比），本脚本是**单指数全景**
- 与 `sw_deep.py` 区别：sw_deep 是**综合报告**（行情+技术+成分+估值），本脚本是**纯统计表**（无技术指标无成分股，专注指标汇总）
- 与 `sw_regression.py` 区别：后者需要基准计算 alpha/beta；本脚本是单指数绝对指标
