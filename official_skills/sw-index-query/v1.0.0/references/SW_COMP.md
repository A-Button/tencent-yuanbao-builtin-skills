> 行情优先使用 westock；必要时通过网页检索补充并核实来源、日期与口径。执行与交付遵循 [DATA_SOURCE.md](DATA_SOURCE.md)；最终回复只表达结果与分析范围，不转述内部诊断。

# SW_COMP — 成分股 / 成分基金

## 1. 概述

单一指数的成分股（或基金指数的成分基金）列表 + 权重饼图 + Top5 高亮 + 集中度统计。支持所有申万指数类型（普通 / 基金 / 大类风格 / 金创），以及 `index-codes.md` 中登记的外部常用指数。

## 2. 输入

```
sw_comp.py --code CODE [--type TYPE] [--name NAME]
```

| 参数 | 必填 | 默认 | 说明 |
|------|------|------|------|
| `--code` | 是 | — | 申万指数代码或外部常用指数代码（如 `000300`、`000905`、`HSI`） |
| `--type` | 否 | `auto` | `auto` / `normal` / `fund` / `style` / `jc` / `external_index`。`auto` 按代码范围和 `index-codes.md` 登记表判断 |
| `--name` | 否 | 空 | 展示名（留空脚本自动查） |

## 3. 输出

```json
{
  "status": "ok",
  "indexCode": "801780",
  "indexName": "银行",
  "indexType": "normal",
  "total": 42,
  "top5_pct": 42.88,
  "top10_pct": 63.66,
  "max_weight_stock": "招商银行(14.5%)",
  "summary_text": "指数: 银行(801780), 类型: normal, 共42只成分。\nTop5权重: 42.88%, Top10权重: 63.66%。\n最大权重: 招商银行 14.5%, 最小权重: 西安银行 0.16%。\nTop5成分: 招商银行(14.5028%), 兴业银行(9.1715%), ..."
}
```

| 字段 | 含义 | Agent 使用要点 |
|------|------|---------------|
| `total` | 成分总数 | 必列 |
| `top5_pct` / `top10_pct` | 前 5 / 10 权重之和 | **必列**（集中度关键指标） |
| `max_weight_stock` | 最大权重成分"(权重 %)"字串 | 必列 |
| `summary_text` | 含 Top5 明细 + 最大/最小 | agent 引用 |

## 4. 路由示例

| 用户说 | Agent 执行命令 |
|-------|--------------|
| "银行成分股" / "801780 成分股" | `sw_comp.py --code 801780 --name 银行` |
| "电子成分股有哪些" | `sw_comp.py --code 801080 --name 电子` |
| "申万300 前十大权重" | `sw_comp.py --code 801300 --name 申万300` |
| "中证500 前十大权重股" | `sw_comp.py --code 000905 --name 中证500` |
| "恒生指数成分股" | `sw_comp.py --code HSI --name 恒生指数` |
| "申万宏源权益基金的成分" | `sw_comp.py --code 807100 --type fund` |
| "大类风格-周期包含哪些股" | `sw_comp.py --code 801271 --type style` |
| "金创指数 802612 的成分" | `sw_comp.py --code 802612 --type jc` |

## 5. 已知坑 / 边界

- 用户没给具体指数名 → 先触发澄清（`clarification-patterns.md` 模板 2）
- 宽基指数（如申万A指，3000+成分）只展示 Top10-20，agent 需提示"共 N 只成分，展示权重前 10"
- 若 Top10 权重 >80% → agent 可补充"集中度极高"解读
- `--type` 通常用 `auto` 即可，只有代码落在交界区（如 806xxx 新三板）才需显式指定
- 外部常用指数成分统一走共享 `market_indices` adapter：优先读 thesis 本地缓存，再用 Tushare `index_weight`，最后对有 qlib universe 的指数用等权成分兜底；恒生指数行情可走 `index_global`，成分需要本地缓存或后续数据源补齐
- 成分股 **权重日期** 可能滞后一个月（月末调整发布），如需最新请查公告（走 `sw_latest_announcements.py`）
