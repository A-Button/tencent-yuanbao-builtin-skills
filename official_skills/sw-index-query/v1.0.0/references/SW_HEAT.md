> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_HEAT — 行业热力 + 轮动象限

## 1. 概述

多时间维度（今日 / 5 日 / 20 日 / 60 日 / YTD）行业涨跌 + D20×D5 四象限轮动图。回答"行业表现 / 板块涨跌 / 行业轮动 / 谁强谁弱"。YTD 按最新交易日相对上一年最后一个交易日收盘计算。

## 2. 输入

```
sw_heatmap.py [--universe a-share-l1] [--scope SCOPE] [--codes a,b,c] [--show-dispersion]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--universe` | 否 | `a-share-l1` | 指数范围：`a-share-l1`=申万 A 股一级行业 |
| `--scope` | 否 | `all` | 板块：`all` / `consumer` / `tmt` / `cyclical` / `finance` / `mfg` / `defensive` |
| `--codes` | 否 | — | 自定义行业代码（逗号分隔，2-8 个，A 股 801xxx）。**传了 `--codes` 则覆盖 `--scope`** |
| `--show-dispersion` | 否 | off | 输出板块内部离散度（std/cv/range/iqr） |

## 3. 输出

```json
{
  "status": "ok",
  "mode": "heatmap",
  "industries_count": 31,
  "quadrant_counts": {"leading":14, "weakening":1, "lagging":5, "improving":11},
  "top3":    [{"name":"通信","today":4.19,"d5":8.40,"d20":23.71}, ...],
  "bottom3": [{"name":"食品饮料","today":-2.10,"d5":-1.70,"d20":-2.71}, ...],
  "summary_text": "行业数量: 31\n领涨行业(今日):...\n领跌行业(今日):...\n领涨象限..."
}
```

| 字段 | 含义 |
|------|------|
| `industries_count` | 实际统计的行业数（scope/codes 过滤后） |
| `quadrant_counts` | 四象限分布：领涨/回落/落后/改善（中期 D20 × 短期 D5） |
| `top3` / `bottom3` | 按今日涨跌幅，每项含 today + d5 + d20 多维度 |
| `summary_text` | 完整叙述（领涨/领跌 Top5 + 四象限分布解读） |
| `dispersion`（仅 `--show-dispersion`） | `{std, cv, range, iqr}` 板块内分化程度 |

**四象限语义**：D20 好 + D5 好 = 领先；D20 好 + D5 弱 = 回落；D20 弱 + D5 弱 = 落后；D20 弱 + D5 好 = 改善。

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "行业表现如何" / "板块涨跌" | `sw_heatmap.py` |
| "消费板块热力" / "TMT 板块涨跌" | `sw_heatmap.py --scope consumer` / `--scope tmt` |
| "基础化工和电子的热力对比" | `sw_heatmap.py --codes 801030,801080` |
| "TMT 板块内部分化严重吗" | `sw_heatmap.py --scope tmt --show-dispersion` |
| "行业轮动" / "哪个行业动能强" | `sw_heatmap.py`（关注 quadrant_counts） |

## 5. 已知坑 / 边界

- `--codes` 传入超过 8 个建议改用 `--scope all`（热力图可读性）
- 小板块（≤5 行业）象限图退化为几个散点，agent 可建议"行业较少，推荐直接看涨跌排序"
- 不支持历史日期快照（对比历史走势用 `sw_chart.py --mode compare`）
- 与 `sw_dashboard` 区别：dashboard 只关注今日；heatmap 含 d5/d20/d60/YTD 多维 + 轮动象限
- YTD 不是 60 日收益；脚本会拉取足够日 K，并用上一年最后一个交易日收盘作为年初至今基准
- 用户问"某板块"但没说哪个 → 先触发澄清（见 `clarification-patterns.md` 模板 3）
