> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_VAL — 估值横截面排行

## 1. 概述

对一类指数按估值指标（PE / PB / 股息率 / 换手率 / 流通市值）做横截面排序。回答 "哪些行业 PE 最低 / 股息率最高 / 换手率最活跃" 等问题。

## 2. 输入

```
sw_valuation.py [--index-type X] [--scope Y] [--metric Z] [--order O] [--limit N]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--index-type` | 否 | `一级行业` | 分类：`市场表征` / `一级行业` / `二级行业` / `风格指数` |
| `--scope` | 否 | `all` | 板块过滤：`all` / `consumer` / `tmt` / `cyclical` / `finance` / `mfg` / `defensive`。**仅对 `一级行业` 生效**，其他 index-type 下传入会被忽略 |
| `--metric` | 否 | `pe` | 排序指标：`pe` / `pb` / `dp`（股息率%）/ `turnover`（换手率%）/ `change_pct` / `circ_mcap`（流通市值亿元） |
| `--order` | 否 | 自动 | `asc` / `desc`。省略时：PE/PB 默认 asc（便宜优先）；dp/turnover 默认 desc（高优先） |
| `--limit` | 否 | `50` | 输出行数上限 |

## 3. 输出

```json
{
  "status": "ok",
  "mode": "valuation",
  "index_type": "一级行业",
  "scope": "all",
  "metric": "pe",
  "order": "asc",
  "count": 31,
  "bargaindate": "2026-04-17",
  "top5":    [{"name":"银行","code":"801780","pe":6.14}, ...],
  "bottom5": [{"name":"综合","code":"801230","pe":123.29}, ...],
  "summary_text": "A股市场 估值排行 - PE 升序 ..."
}
```

| 字段 | 含义 | Agent 使用要点 |
|------|------|---------------|
| `count` | 参与排序的指数数（通过过滤后） | 回复时明确基数（"31 个一级行业中" / "TMT 板块 4 行业中"） |
| `bargaindate` | 数据日期 | 回复必须标注 |
| `top5` / `bottom5` | 指定 metric 排序的头尾 5 条 | 引用具体数值 |
| `summary_text` | **agent 直接引用撰写回复**，含中位数 + 区间 | 禁止自己重新统计 |

**Agent 核心规则**：所有数值、排名来自 `summary_text` 或 `top5/bottom5`，不得自行计算。

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "哪些行业 PE 最低" | `sw_valuation.py --metric pe` |
| "股息率最高的行业" | `sw_valuation.py --metric dp --order desc` |
| "TMT 板块 PE 排行" | `sw_valuation.py --scope tmt --metric pe` |
| "消费板块 PB 从低到高" | `sw_valuation.py --scope consumer --metric pb` |
| "风格指数 PE 对比" | `sw_valuation.py --index-type 风格指数 --metric pe` |
| "哪个行业换手率最高" | `sw_valuation.py --metric turnover --order desc` |
| "最便宜的行业" | `sw_valuation.py --metric pe`（便宜 = PE 升序） |

## 5. 已知坑 / 边界

- `--scope` **只对 `--index-type 一级行业` 生效**，其他分类下会被忽略
- 小板块（finance=3 / defensive=3 / mfg=4 / tmt=4）样本 <10 时，`bottom5` 返回空数组（脚本阈值），agent 不要列出重复数据
- `bargaindate` 是**最近一个已收盘交易日**的快照，**盘中非实时**（盘中问估值不会看到当日变化）
- 基本面字段偶尔为 `null`（新指数 / 停牌 / 无数据），脚本已自动过滤掉缺失 metric 的行，`count` 可能小于分类总数
- 若用户要"单指数全指标快照" → 走 `sw_stats.py`，不是本脚本
