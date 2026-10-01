# WeStock CLI 用法（本包内置）

`westock` 是本 Skill 内置的金融数据 CLI。支持股票（A股/港股/美股/日韩股）、ETF、指数、板块、期货、外汇、可转债的行情、财报、研报、新闻、公告、事件、股东、分红、ETF 持仓、热搜榜、新股/投资日历、龙虎榜；以及行业经营数据、申万行业估值/盈利预测/财务、全球宏观经济。**它是本 Skill 的数据源，不是另一层场景编排**——四个场景怎么走、卡怎么出，仍以 [SKILL.md](../SKILL.md) 与 [data-recipes.md](./data-recipes.md) 为准。

## 安装（本包自举）

二进制随本包发布在 `scripts/westock/`。取数前若 `westock` 不在 PATH，先自举安装一次：

```bash
command -v westock >/dev/null 2>&1 || bash /data/skills/stock-watch/scripts/westock/setup.sh -y
```

装好后直接 `westock <子命令> [参数]` 调用。

> **注意**：这只影响交互分析 / 异动归因 / 回调正文的取数。Judge（Trigger 周期取数）跑在精简环境、**不装 westock**，那一层用本包自带的 `check_anomaly.py` / `_quote_src.py`，不要改成 westock。

## 调用方式

- 统一 Go CLI；子命令列表见 `westock --help`，单命令参数见 `westock <子命令> --help`
- 需网络

```bash
westock search 宁德时代
westock quote sh600519
westock quote sh600519,sh601318,sz300750    # 批量
```

**并发**：无依赖的多个查询（如 quote + news + kline）应在同一轮工具调用中并行发出，不要串行等结果。

---

## 参考文档（仅不确定时查阅，禁止每次任务都读）

- [westock/routing-guide.md](./westock/routing-guide.md) — 场景路由、与其它 Skill 边界
- [westock/commands.md](./westock/commands.md) — 完整命令语法
- [westock/scenarios-guide.md](./westock/scenarios-guide.md) — 分析场景模板
- [westock/ai_usage_guide.md](./westock/ai_usage_guide.md) — 返回字段说明
- [westock/macro-fields.md](./westock/macro-fields.md) — 宏观指标短名与字段

---

## 核心铁律

1. **CLI 优先，web_search 兜底**——命中本 CLI 能力域的查询，**优先**用 `westock` 取数；**取不到 / 空结果 / 明显不足 / 用户指定较早历史区间**时，用 `web_search` 兜底补齐，整合两源并**标明来源**（区分 westock / web），冲突时以交易所/公司公告口径为准。**宏观数据**（GDP/CPI/PMI/利率等）先走 `westock macro indicator`，短名**禁止按自然语言猜**——先 `westock macro list [--region cn|us|hk|jp|eu]` 查可用短名（如 `us_inflation`），再传给 `indicator`；westock 无覆盖时再 web_search 兜底。
2. **未知代码先 `westock search`**——用户只给名称时，先 `westock search` 拿代码再查行情。
3. **货币单位正确**——港股港元/美元、美股美元、日股日元、韩股韩元；禁用人民币符号。
4. **筛股用 `westock-screener`**——本 CLI 只做数据查询。
5. **多股批量**——对比/分析 N 只股票时，**凡支持批量的命令只调 1 次**、代码用逗号分隔；**禁止**同一轮对比里「有的命令批量、有的按股拆开」。例外（必须单代码）见下方「批量例外」。
6. **代码必须带市场前缀**——A股 `sh/sz/bj`、港股 `hk`、美股 `us`、日股 `t`、韩股 `ks/kq`、期货 `fu/hf/r_hd`、外汇 `fx`、板块 `pt`；**禁止**裸 6 位数字（`300685`）、**禁止** Wind 格式（`601988.SH`）、**禁止**港股漏前缀（`00700`→`hk00700`）。
7. **探索纪律**——`SKILL.md` / `commands.md` 已覆盖的命令**禁止再调 `--help`**；每个任务 `--help` 至多 1 次；不确定优先用本文「高频命令速查」与「参数命名约定」，而非反复 `| grep` 试探。
8. **指定日行情 → `westock quote --date`**——查「某天/昨天/某历史日」的行情数据（涨跌幅、量比、收盘价等任意 quote 字段）一律用 `westock quote <代码> --date YYYY-MM-DD`，**直接读返回字段**（见 ai_usage_guide.md）；**禁止**用 `westock kline` 手算、**禁止**用无 `--date` 的实时 `westock quote` 取当天值答历史日。
9. **财报精确取值 → `--fields`**——`finance` 默认输出核心字段窄表（`--fields core`，约 30 个核心指标）；需全字段时加 `--fields all`（100+ 列）。避免宽表列名相近看错列（如 `OperatingRevenue` ≠ `OperatingProfit`）；比率类指标（ROE / 毛利率等）直读报表返回值，**禁止**自行拼算。
10. **资金口径**——A股/港股资金流向用 `westock fund flow`；港股/美股**卖空、空头** 用 `westock fund short`；港股南下持仓快照用 `westock fund south-holding`；**个股龙虎榜**用 `westock fund lhb <代码>`（仅沪深，支持 `--date` 指定日或 `--start/--end` 区间）；美股无 `fund flow`，卖空数据用 `westock fund short`。**禁止**用南下持仓替代卖空数据。
11. **复合分析靠编排原子命令**——「事件后收益、多年 ROE 验证、板块/指数成份对比」等无单一命令，须编排多个原子命令：**批量**（逗号多 code）+ **并行**（无依赖同轮发）+ **限量采样**（`--limit` 20~30，基于 Top N 样本、非全量，交付须注明）。完整步骤见 [westock/scenarios-guide.md §16](./westock/scenarios-guide.md)。

> **web_search 口径统一**：本 CLI 全域采用「CLI 优先 + web_search 兜底」，不再对任何数据域禁用 web_search。行情/K 线/技术/财务/资金等命令取不到或不足时，同样可用 web_search 补齐并标注来源。资讯/公告/研报场景的兜底细则见 [data-recipes.md](./data-recipes.md) 场景四。

### 参数命名约定

本 CLI 参数名与取值都用简短写法（如 `--limit 20`、`--period day`、`--type sector`），不要自创长参数或复数形式；**不确定某参数/取值，回 commands.md 该命令小节核对，不要猜**。

- 条数 → `--limit`，**仅**下列命令支持：`calendar`/`connect`/`dehydrated`/`etf holdings`/`finance`/`hot news`/`hot sector`/`index constituent`/`index list`/`kline`/`macro indicator`/`news list`/`notice list`/`report list`/`search`/`sector constituent`/`sector ranking`/`technical`/`trade-calendar`；其余传入报 `unknown flag`（`dividend` 用 `--years`，`buyback`/`fund flow`/`fund lhb` 用 `--start`/`--end`）
- 周期 → `--period m1|m5|m15|m30|m60|m120|day|week|month|season|year`（**仅** `kline`/`technical`）；`finance` 用 `--limit`（期数）或 `--start`/`--end`，无 `--period`
- 板块 → `--type sector`（概念/行业统一 `sector`，非 `concept`/`industry`/`all`）
- 代码 → 一律带市场前缀（见铁律 6）
- `--raw` → 输出严格 JSON 而非 Markdown 表格（**全局**，所有命令通用）；多 section 命令自动包成 `{ sections: [...] }`，便于程序化消费

### 输出与解析纪律

- **默认输出已是结构化 Markdown 表格**（含关键字段），直接读取分析，**禁止**用脚本/正则/Python 去解析命令的文本输出。
- **禁止终端截断**：不要用 `| grep` / `| head` / `| tail` / `| sed` 过滤输出，也不要用 `&&` / `;` 拼接多条命令；条数、分页、筛选只用**该子命令自己的参数**（不同命令支持的 flag 不同，禁止跨命令套用）。
- 返回字段含义见 [westock/ai_usage_guide.md](./westock/ai_usage_guide.md)，不确定字段含义再查阅，不要靠反复试错猜。

### search 规则

**默认仅搜股票**（`westock search <关键词>` = `--type stock`，只调 1 次接口）。不会自动查 ETF/板块/指数/期货/外汇。`--type` **支持逗号分隔多个类型同时搜**（如 `--type etf,index,sector`），一条命令按类型分组返回，优于依次盲试。

| 用户意图 | 命令 | 不要 |
|---------|------|------|
| 找股票代码（默认） | `westock search 宁德时代` | 不要无 `--type` 时再去试 etf/bond/index/sector |
| 找 ETF/基金 | `westock search 沪深300 --type etf` | 用户说了「ETF」就直接带 type，不要先默认再重试 |
| 找指数 | `westock search 中证红利 --type index` | |
| 找板块 | `westock search 银行 --type sector` | |
| 找可转债 | `westock search 兴业 --type bond` | |
| 找期货/外汇 | `westock search 黄金 --type futures` / `--type forex` | |
| 一次找多个类型 | `westock search 港股通创新药 --type etf,index,sector` | 不要拆成多次单类型命令依次盲试 |
| 日韩股 | `westock search 三星 --market kr` | `--market` 与 `--type` 互斥 |

**空结果时**：读 CLI 返回的提示，按用户原意**最多再试 1 种** `--type`（或 `--market`），不要对同一关键词依次扫 etf→bond→index→sector。**仍无结果**则改用 `web_search` 兜底或告知用户，不要死磕同一关键词反复换 type。

**禁止**：对同一关键词连续换 3+ 种 `--type` 盲试（如需多类型，用 `--type a,b,c` 一次搞定）。

### 批量查询

多标的对比：代码用逗号写在**同一条命令**里（如 `westock finance sh600519,sz000651`），不要一股一条命令。

```bash
# 分析 sh600519 + sz000651 → 下面 6 条各 1 次（共 6 次），不是 12+ 次
westock quote sh600519,sz000651
westock quote sh600519 --date 2026-07-03        # 指定历史日行情（涨跌幅/量比/收盘价等，见 ai_usage_guide.md）
westock kline sh600519,sz000651 --period day --limit 60
westock finance sh600519,sz000651 --limit 4
westock news list sh600519,sz000651 --limit 10
westock technical sh600519,sz000651
westock fund flow sh600519,sz000651
```

**批量例外**（不支持逗号多代码，须分开调；可同一轮并行发出）：

| 命令 | 限制 |
|------|------|
| `westock minute` / `westock search` | 不支持代码批量 |

无依赖的多种查询（上列各条）**同一轮并行发出**。完整限制见 [westock/routing-guide.md §六/§九](./westock/routing-guide.md)。

---

## 高频命令速查

```bash
# 搜索
westock search 宁德时代
westock search 半导体 --type sector

# 行情 / K 线 / 财务 / 技术
westock quote sh600519
westock kline sh600519 --period day --limit 20
westock finance sh600519,sz000651 --limit 1          # 多股三大表
westock technical sh600519

# 新闻 / 研报 / 公告
westock news list sh600519 --limit 10
westock report list sh600519 --limit 5
westock notice list sh600519 --limit 10

# 板块 / 指数 / 宏观
westock sector constituent pt01801080          # 成份股
westock sector valuation pt01801080            # 估值 PE/PB/PS + 历史百分位
westock sector finance pt01801780               # 申万行业财报 TTM 聚合（仅申万行业，聚源概念不支持）
westock index constituent sh000300
westock macro indicator cn_core --date 2026-03-01

# 资金 / 北向
westock fund flow sh600519
westock fund north-holding sh600519
westock fund south-holding hk00700
westock fund north-holding pt01801080             # 仅申万行业，聚源概念板块不支持

# ETF / 发现
westock etf profile sh510300
westock hot stock                               # 热搜股；另有 hot news/sector/etf
```

完整语法见 [westock/commands.md](./westock/commands.md)。

---

## 异常与空结果

1. **命令失败**：如实转述，禁止编造数据；可用 `web_search` 兜底补齐并标注来源。
2. **空结果**：说明「暂无数据」；区分代码不支持 vs 时点无披露（必要时先 `westock search`）；仍需要时用 `web_search` 兜底。
3. **能力不支持**：如实告知（如美股无 `westock fund flow`），见 [westock/routing-guide.md §六](./westock/routing-guide.md)；可用 `web_search` 兜底。
4. **兜底纪律**：CLI 优先，取不到才 web_search；两源整合务必**标明来源**，不得把 web 结果冒充 westock 权威数据，也不得凭训练数据臆造。

---

## 重要声明

> 本能力仅提供客观市场数据查询，不构成投资建议。数据可能有延迟，以交易所官方为准。投资有风险，决策需谨慎。

**数据来源**：腾讯自选股数据接口
