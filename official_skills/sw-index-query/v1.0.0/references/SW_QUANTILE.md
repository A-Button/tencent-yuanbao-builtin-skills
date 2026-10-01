> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_QUANTILE — 单指数历史分位数

## 1. 概述

回答"当前 XX 在近 N 年历史处于什么分位"。支持 PE / PB / 股息率 / 换手率 / 收盘价 5 类指标。

## 2. 输入

```
sw_quantile.py --code CODE [--name NAME] --metric M [--years Y] [--index-type T]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--code` | 是 | — | 6 位申万指数代码 |
| `--name` | 否 | 空 | 展示名 |
| `--metric` | 否 | `pe` | `pe` / `pb` / `dp` / `turnover` / `close` |
| `--years` | 否 | `5` | 回溯年数 |
| `--index-type` | 否 | 自动 | 指数类型（`市场表征` / `一级行业` / `二级行业` / `风格指数`）；留空自动识别 |

## 3. 输出

```json
{
  "status": "ok",
  "mode": "quantile",
  "code": "801780", "name": "银行",
  "metric": "pe", "years": 5,
  "index_type": "一级行业",
  "current": 6.14,
  "percentile": 12.3,
  "category": "低位（<25%）",
  "min": 5.80, "max": 11.20,
  "median": 7.90, "p25": 6.50, "p75": 8.85,
  "samples_count": 60,
  "range": "2021-04-30 ~ 2026-03-31",
  "summary_text": "银行(801780) 当前 PE 6.14，处于近 5 年 12.30% 分位（低位（<25%））\n历史区间：5.80~11.20  中位数 7.90  25分位 6.50  75分位 8.85\n（样本 60 个月点，范围 2021-04-30 ~ 2026-03-31）"
}
```

| 字段 | 含义 |
|------|------|
| `current` | 当前指标值（用最新日级数据，比月点更新） |
| `percentile` | 百分位（0-100，≤current 的样本占比） |
| `category` | 归档：极低位 / 低位 / 中下位 / 中上位 / 高位 / 极高位 |
| `min/max/median/p25/p75` | 分布统计 |
| `samples_count` | 月点样本数（N 年 ≈ 12N 个月） |
| `summary_text` | 格式化呈现 — **agent 直接引用** |

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "银行当前 PE 在 5 年历史什么分位" | `sw_quantile.py --code 801780 --name 银行 --metric pe --years 5` |
| "申万300 股息率近 10 年分位" | `sw_quantile.py --code 801300 --name 申万300 --metric dp --years 10` |
| "电子 PB 分位数" | `sw_quantile.py --code 801080 --name 电子 --metric pb` |
| "医药生物换手率历史分位" | `sw_quantile.py --code 801150 --name 医药生物 --metric turnover --years 5` |

## 5. 已知坑 / 边界

- **样本是按月末取样**（不是按日）—— 5 年 ≈ 60 个样本点。分位数对日内波动不敏感，够用但不精细
- `--years` 太小（<1）报错；样本 <12（API 数据不足）报错
- `--metric close` 用 K 线数据；其他 metric 用月末基本面快照
- `percentile < 25` 通常意味"低估值"/"低活跃"（视 metric 语义）；`> 75` 意味"高"
- 指数类型**自动识别**（扫 4 类 fundamentals_batch）—— 首次调用约 1-2s；如确定可显式传 `--index-type` 加速
- 大类风格指数（801271-276）、金创（802608-612）、基金指数（807xxx/808xxx）**不在 fundamentals_batch 覆盖范围**，本脚本无法处理
- 与 `sw_stats.py` 区别：STATS 是"**当前单期全指标**"；本脚本是"**单指标历史分位**"
- 与 `sw_rank.py` 区别：RANK 是"多指数横向排序"；本脚本是"**单指数纵向分位**"
- 用户问"哪些指数 PE 低于历史 10%分位"（跨指数筛选） → 暂不直接支持，建议拆分为多次调用或告知用户
