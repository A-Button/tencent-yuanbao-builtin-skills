> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_REGRESSION — 双指数回归分析

## 1. 概述

两个指数之间的回归关系：相关系数、Beta、Alpha、追踪误差、信息比率、超额收益、滚动 Beta / 相关性曲线。回答"XX 对 YY 的 alpha / beta / 相关性 / 超额收益 / 追踪误差"。**只处理 2 个指数**（多指数相关走 `sw_corr_matrix.py`）。

## 2. 输入

```
sw_regression.py --code CODE --name NAME [--benchmark BCODE] [--bench-name BNAME] [--days N]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--code` | 是 | — | 目标指数代码 |
| `--name` | 是 | — | 目标指数名称 |
| `--benchmark` | 否 | `801003` | 基准指数代码（默认申万A指）。用户未指定基准时用此默认 |
| `--bench-name` | 否 | `申万A指` | 基准名 |
| `--days` | 否 | `500` | 回溯交易日数（约 2 年） |

## 3. 输出

```json
{
  "status": "ok",
  "name_a": "银行", "code_a": "801780",
  "name_b": "申万A指", "code_b": "801003",
  "metrics": {
    "correlation": 0.85,
    "beta": 0.72,
    "alpha_annual_pct": 3.5,
    "tracking_error_pct": 8.2,
    "info_ratio": 0.43,
    "cum_return_a": 15.8, "cum_return_b": 10.2,
    "excess_return": 5.6,
    "annual_return_a": 8.5, "annual_return_b": 5.2,
    "annual_vol_a": 12.3, "annual_vol_b": 15.1,
    "max_drawdown_a": -8.5
  },
  "summary_text": "银行(801780) vs 申万A指(801003) 近500日回归：correlation 0.85, beta 0.72, 年化 α +3.5%, TE 8.2%, IR 0.43 ..."
}
```

**指标意义**（agent 回复可引用解释）：
- `correlation` -1~1：相关系数，越接近 1 走势越同步
- `beta`：目标 vs 基准的敏感度。>1 波动大于基准；<1 更稳
- `alpha_annual_pct`：年化超额收益（扣基准）
- `tracking_error_pct`：追踪误差（目标 vs 基准收益差的年化波动）
- `info_ratio = alpha / tracking_error`：信息比率

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "银行相对申万A指 alpha" / "银行对大盘的 beta" | `sw_regression.py --code 801780 --name 银行` |
| "电子相对申万300 的超额收益" | `sw_regression.py --code 801080 --name 电子 --benchmark 801300 --bench-name 申万300` |
| "基础化工和申万A指的相关性" | `sw_regression.py --code 801030 --name 基础化工` |
| "医药 vs 消费近一年回归" | `sw_regression.py --code 801150 --name 医药生物 --benchmark 801260 --bench-name 申万消费 --days 250` |

## 5. 已知坑 / 边界

- K 线重叠交易日不足 30 时脚本会报错（`status="error"`），agent 需告知 "数据窗口太短，请加 `--days`"
- **仅 2 个指数**。需要 3+ 指数互相关走 `sw_corr_matrix.py`
- 用户未给基准时**默认申万A指**（大盘基准）。若用户说"相对 XX" → 把 XX 当基准
- `info_ratio` 负值表示目标长期跑输基准
- **严禁预测**（如不能讲"β<1 说明银行会跑输大盘"），只陈述数字
