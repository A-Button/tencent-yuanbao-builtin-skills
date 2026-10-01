> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_RANK — 指数多维度排名

## 1. 概述

对一类指数（一级行业 / 基金大类 / 基金细分 / 风格指数 / 板块预设）按指定指标横向排名。回答"哪个指数表现最好 / YTD 最高 / Calmar 最大 / 最大回撤最少"。

## 2. 输入

```
sw_rank.py --category CAT [--codes a,b,c] [--sort M] [--days N]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--category` | 否 | `l1` | 分类预设，见下表；或用 `--codes` 自定义 |
| `--codes` | 否 | — | 自定义指数代码（逗号分隔），**传入则覆盖 `--category`** |
| `--sort` | 否 | `ytd` | 排序指标：`ytd` / `calmar` / `sharpe` / `max_drawdown` / `y1` / `y3` / `y5` / `m1` / `m3` / `vol` |
| `--days` | 否 | `250` | 回撤/波动率 / Calmar 的回溯窗口（交易日） |

**`--category` 预设**：

| 值 | 说明 |
|----|------|
| `l1` | 一级行业 31 个 |
| `fund` | 基金大类 7 个（权益/债券/混合/货币/另类/组合/QDII） |
| `fund_equity` / `fund_bond` / `fund_theme` / `fund_enhance` | 基金细分 |
| `style` | 风格指数 18 个 |
| `consumer` / `tmt` / `cyclical` / `finance` / `mfg` / `defensive` | 板块预设 |

## 3. 输出

```json
{
  "status": "ok",
  "category": "l1", "label": "一级行业",
  "sort": "calmar", "count": 31,
  "top3":    [{"name":"煤炭","code":"801950","ytd_return":16.83,"calmar":1.51}, ...],
  "bottom3": [{"name":"非银金融","code":"801790","ytd_return":-14.98,"calmar":-0.70}, ...],
  "summary_text": "一级行业指数排名（按calmar排序，共31个指数）\nTop1. 煤炭(801950): YTD:+16.83%, Calmar:1.51, 最大回撤:-11.16%, Sharpe:0.94\n..."
}
```

**指标说明**：
- `ytd_return` / `m1_return` / `m3_return` / `y1_return` / `y3_return` / `y5_return`：区间收益 %
- `y1_vol` / `ytd_vol`：年化波动率 %
- `max_drawdown`：最大回撤 %（负值）
- `calmar = ytd_return / |max_drawdown|`
- `sharpe = (y1_return - 2%) / y1_vol`（无风险利率取 2%）

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "哪个行业 Calmar 最大" | `sw_rank.py --category l1 --sort calmar` |
| "基金指数 YTD 排名" | `sw_rank.py --category fund --sort ytd` |
| "一级行业 Sharpe 排名" | `sw_rank.py --category l1 --sort sharpe` |
| "周期板块哪个回撤最大" | `sw_rank.py --category cyclical --sort max_drawdown` |
| "比较银行和非银金融" | `sw_rank.py --codes 801780,801790` |
| "风格指数近一年排名" | `sw_rank.py --category style --sort y1` |
| "行业主题基金 Calmar 最高" | `sw_rank.py --category fund_theme --sort calmar` |

## 5. 已知坑 / 边界

- `--codes` 自定义列表建议 3-10 个，过多（>20）排序表可读性差
- `max_drawdown` 数值为**负值**，"最大回撤最少" = `--sort max_drawdown`（升序放前 = 接近 0 的）
- `--days` 默认 250（≈1 年）。"近半年" 时用 `--days 125`
- 与 `sw_rank.py` 可做的 vs 其他脚本分工：
  - **跨期反转** ("上月 vs 这月") → `sw_period_rank.py --compare-offset`
  - **单指数全指标快照** ("银行年化/波动/胜率") → `sw_stats.py`
- 用户问"某一类指数排名"但没说按什么排 → 默认 `--sort ytd`
