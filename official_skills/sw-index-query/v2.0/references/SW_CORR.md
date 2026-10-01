> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_CORR — N 指数相关性矩阵

## 1. 概述

≥3 个指数的两两日收益 Pearson 相关系数矩阵 + 平均相关 + 最强/最弱配对。回答"31 一级行业互相相关性 / TMT 4 行业相关矩阵"。**仅 2 个指数请用 sw_regression.py**（含 alpha/beta/TE 更全）。

## 2. 输入

```
sw_corr_matrix.py [--codes a,b,c | --scope S] [--names ...] [--days N]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--codes` | 或 `--scope` 二选一 | — | 逗号分隔，**≥3 个** |
| `--names` | 否 | 自动 | 与 codes 对齐，省略时脚本从代码表查 |
| `--scope` | 或 `--codes` 二选一 | — | 预设：`l1`（31 一级）/ `style`（18 风格）/ `market`（4 市场表征）/ `consumer`/`tmt`/`cyclical`/`finance`/`mfg`/`defensive` |
| `--days` | 否 | `250` | 回溯交易日 |

## 3. 输出

```json
{
  "status": "ok",
  "mode": "corr_matrix",
  "count": 4,
  "window_days": 250,
  "effective_days": 243,
  "codes": ["801080","801750","801770","801760"],
  "names": ["电子","计算机","通信","传媒"],
  "matrix": [
    [1.000, 0.820, 0.750, 0.710],
    [0.820, 1.000, 0.790, 0.680],
    [0.750, 0.790, 1.000, 0.660],
    [0.710, 0.680, 0.660, 1.000]
  ],
  "avg_corr": 0.7330,
  "max_pair": {"a":"电子","b":"计算机","corr":0.820},
  "min_pair": {"a":"传媒","b":"通信","corr":0.660},
  "summary_text": "4 个指数共同窗口 250 日（实际 243 日重叠）平均相关 0.733\n最强: 电子-计算机 = 0.820\n最弱: 传媒-通信 = 0.660"
}
```

| 字段 | 含义 |
|------|------|
| `count` | 参与计算的指数数（成功拉到 K 线的） |
| `effective_days` | 所有指数共同覆盖的交易日数 |
| `matrix[i][j]` | codes[i] 和 codes[j] 的 Pearson 相关系数（对角线 = 1） |
| `avg_corr` | 所有两两对相关系数的均值（不含对角线） |
| `max_pair` / `min_pair` | 最强 / 最弱相关的指数对 |
| `summary_text` | 精简摘要 — agent 直接引用 |

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "31 一级行业相关性" | `sw_corr_matrix.py --scope l1` |
| "TMT 4 行业相关矩阵" | `sw_corr_matrix.py --scope tmt` |
| "消费板块相关性" | `sw_corr_matrix.py --scope consumer` |
| "风格指数两两相关" | `sw_corr_matrix.py --scope style --days 500` |
| "电子、计算机、申万300 的相关" | `sw_corr_matrix.py --codes 801080,801750,801300 --names 电子,计算机,申万300` |

## 5. 已知坑 / 边界

- **≥3 个指数必选**；2 个请走 `sw_regression.py`
- **≤31 个上限**（>31 矩阵过大；若 scope=l1=31 个正好边缘）
- 指数重叠交易日 < 30 时报错（某些指数上市晚或暂停交易太久）
- 相关系数是**日收益率 Pearson**，不是价格或累计收益；适合衡量"短期共振度"
- 大 scope（l1 31 行业）下 `matrix` 字段体积较大（31×31=961 个数），**agent 回复只引用 avg_corr + max/min_pair**，不要读整个矩阵
