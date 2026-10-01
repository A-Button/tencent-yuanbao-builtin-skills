# WeStock Tool

**作用**：提供五种选股 / 选基方式——条件选股（自定义表达式筛选）、策略选股（预置策略一键获取信号股票）、标签选股 / 选基（股票分类标签 + ETF 主题池）、事件选股（按预定义事件类型筛选触发股票）、**排行选股 / 选基**（按涨跌停/财务/评分/两融/资金流入等指标对股票排序，或按规模/估值/行情/换手/溢折率等对 ETF 排序，支持在板块/标签/策略/事件结果内做二次排序）。

> ⚠️ **本工具内 6 个子命令的路由原则**：
> - **`filter` 表达式**：用户描述**自定义条件**（如"PE<20且ROE>15"）
> - **`filter --preset`**：用户需要**条件型预设筛选**（如"低PE股"、"高股息股"）
> - **`strategy`**：用户提到**策略信号**（如"MACD金叉"、"巴菲特策略"）
> - **`label`**：用户提到**分类标签**（如"央企"、"ST股"、"新股"、"破净股"；ETF 加 `--asset etf`：高股息 ETF/千亿基金/科创占比高）
> - **`event`**：用户提到**事件+时间窗口下的"哪些股票"**（如"近期有哪些股票限售解禁"、"哪些公司发布了回购公告"、"董监高增持的股票"）
>   - ❌ event 返回的是**触发该事件的股票列表（用于选股）**，不是事件本身的公告/新闻原文。如需事件资讯/公告原文，请用 `westock-data news/notice`。
> - **`ranking`**：用户提到**按指标排序、最多/最少、TOP/榜单**——典型口语：
>   - "今天两融减仓最多的" → `ranking margin_chg_d --asc`
>   - "评分 TOP 10" → `ranking CompScore --limit 10`
>   - "涨停封单量最大" → `ranking limit_up_seal_amount`
>   - "央企里评分最高" → `ranking CompScore --label 央企`
>   - "MACD 金叉中估值最低" → `ranking PE_TTM --strategy MACD金叉 --asc`
>   - "ETF 规模榜/涨幅榜" → `ranking <指标> --asset etf`
> - **❌ 概念股查询不属于本工具**：用 `westock-data sector search <关键词>`

---

## 🔴 清单查询规则（强制执行命令，禁止凭文档列举）

> 当用户问"有哪些事件 / 标签 / 策略 / 指标 / 预设 可以用"时，**必须执行对应 `--list` 命令获取实时清单**，不要凭本文档里的样例回答。SKILL.md 与 references 中列出的事件/标签/策略**仅是举例**，完整且最新的清单**以命令输出为准**（防止文档过时导致漏报/错报）。
>
> | 用户问法 | 必须执行的命令 |
> | --- | --- |
> | "有哪些事件可以选股" | `event --list` |
> | "有哪些标签可以选股" | `label --list` |
> | "ETF 有哪些主题池" | `label --asset etf --list` |
> | "有哪些策略可以选股" | `strategy --list` |
> | "有哪些排行指标" | `ranking --list` |
> | "ETF 有哪些排行指标" | `ranking --list --asset etf` |
> | "filter 有哪些预设" | `filter --list-presets` |

**数据源**：腾讯自选股选股数据接口 | **条件选股**：A股、港股、美股 | **策略/标签/事件/排行（股票）**：仅A股 | **ETF 选基（label/ranking --asset etf）**：沪深 ETF（约 1530 只）

---

## ⚙️ 命令调用约定

> 下文示例统一写作 `westock-tool <命令>`，这是**逻辑命令名**，并非可执行程序。实际执行规则如下：
>
> - **执行方式**：`node <本SKILL.md所在目录>/scripts/index.js <命令> [参数]`（`<本SKILL.md所在目录>` 按实际环境解析为本文件所在目录）
> - **禁止**：硬编码任何具体安装路径（如 `~/.openclaw/skills/...`、`/usr/local/...` 等），各运行环境目录不同
> - **环境**：Node.js ≥ v18，脚本已单文件打包，无需 `npm install`

---

## 已知限制速查

| 限制项 | 说明 |
|--------|------|
| 市场覆盖 | 沪深A股、港股、美股；**不支持北交所** |
| 港股/美股字段名 | 估值字段名与沪深不同（见下方字段速查），**切勿混用** |
| PE/PB 负值 | 亏损股 PE/PB 为负，筛选时必须排除负值，如 `PE_TTM > 0` |
| 预设函数市场 | 港股必须加 `--market hk`，美股必须加 `--market us` |
| 多条件AND | **必须使用 `intersect([...])`**，不支持 `&`/`&&`/`AND` |

### ⚠️ 常见错误

| 错误写法 | 正确写法 |
|---------|---------|
| `PE_TTM < 20 & ROE_TTM > 15` | `intersect([PE_TTM > 0, PE_TTM < 20, ROETTM > 15])` |
| `PE_TTM < 20 AND ROETTM > 15` | `intersect([PE_TTM > 0, PE_TTM < 20, ROETTM > 15])` |

---

## 条件选股（filter）

```bash
# 单条件 / AND / OR
westock-tool filter "ClosePrice >= 100"
westock-tool filter "intersect([PE_TTM > 0, PE_TTM < 20, ROETTM > 15])"
westock-tool filter "union([ChangePCT > 5, Chg5D > 10])"

# 排序 / 港股 / 美股 / 板块限定
westock-tool filter "intersect([PE_TTM > 0, PE_TTM < 15, ROETTM > 15])" --by ROETTM --desc
westock-tool filter "intersect([PeTTM > 0, PeTTM < 10, DivTTM > 5])" --market hk
westock-tool filter "intersect([PeTTM > 0, PeTTM < 30, TotalMV > 1000])" --market us
westock-tool filter "intersect([PE_TTM > 0, PE_TTM < 20])" --universe 11010001 --limit 20

# 预设函数（条件型预设：估值/技术/财务/资金/机构/组合 6 大类 20+ 函数）
westock-tool filter --preset LowPE --limit 30
westock-tool filter --preset HighDividend --market hk
westock-tool filter --list-presets                        # 查看所有预设函数名
```

**表达式语法**：

| 语法 | 说明 |
|------|------|
| `字段 比较符 值` | 单条件，如 `ClosePrice >= 100` |
| `intersect([条件1, 条件2, ...])` | **AND 组合（必须使用，不支持 `&`/`&&`/`AND`）** |
| `union([条件1, 条件2, ...])` | OR 组合 |

**主要参数**：`--date`（日期）、`--limit`（默认 20）、`--by <字段> [--asc|--desc]`（排序，默认降序；兼容旧写法 `--orderby <字段:asc|desc>`）、`--market hk|us`、`--universe <板块代码>`、`--raw`（输出严格 JSON 而非 Markdown 表格，**所有命令通用**）。

> **`filter --preset` 与 `strategy` 的边界**：filter --preset 是**条件型**预设（输出含指标列的表格）；strategy 是**策略信号型**预置（输出仅含 code/name 的表格）。
>
> **预设函数完整列表（含默认参数）+ 表达式语法详解**参见 [references/ai_usage_guide.md](./references/ai_usage_guide.md)

### 同义需求 → 推荐命令对照

| 用户表述 | 推荐命令 | 说明 |
|---------|---------|-----|
| "低估值股有哪些" / "破净股" | `label valuation_lowpb` / `label valuation_negpe` | 静态分类，无需阈值 |
| "PE<20 且 ROE>15 的股" | `filter "intersect([PE_TTM>0, PE_TTM<20, ROETTM>15])"` | 自定义阈值 |
| "低 PE TOP 30" | `filter --preset LowPE --limit 30` | 参数化预设 |
| "估值最低的 10 只" | `ranking fin_valuation --limit 10` | 排行榜（升序） |
| "MACD金叉" / "巴菲特股" | `strategy macd_golden` / `strategy buffet` | 策略信号 |
| "MACD金叉里估值最低的" | `ranking fin_valuation --within-strategy macd_golden` | 范围限定 + 排序 |
| "新股有哪些" / "次新股" | `label listeddate_5days` / `label listeddate_3mons` | 上市时间标签 |
| "近期限售解禁" | `event shareunlock_next_90` | 事件 + 时间窗口 |
| "央企里评分最高" | `ranking CompScore --within-label shareholder_central_state` | 范围限定 + 排序 |

---

## 策略选股（strategy）

```bash
westock-tool strategy --list                                          # 查看所有可用策略
westock-tool strategy macd_golden                                     # 单策略
westock-tool strategy macd_golden --date 2026-04-10                   # 指定日期
westock-tool strategy high_dividend,pb_roe                            # 多策略并查
westock-tool strategy macd_golden --start 2026-04-01 --end 2026-04-10 # 区间趋势（⚠️ 多天必须用 --start/--end）
westock-tool strategy buffet --limit 10 --offset 20                   # 分页
```

**主要参数**：策略名（必填，逗号分隔多个）、`--date` / `--start` / `--end`、`--limit` / `--offset`、`--list`。支持直接传入任意 listcode，新增策略无需更新工具代码。

**可用策略概览**（仅展示代表性条目，**完整且最新清单必须执行 `strategy --list`**）：

| 分类 | 代表性策略 |
|------|----------|
| 基本面 | `high_dividend`(高股息)、`pb_roe`(高盈利价值)、`profit_preannounce`(业绩预增) |
| 大师策略 | `buffet`(价值龙头)、`graham`(格雷厄姆)、`fisher`(费雪) |
| K线形态 | `morning_star`(早晨之星)、`red_three_solider`(红三兵) |
| 指标信号 | `macd_golden`(MACD金叉)、`kdj_golden`(KDJ金叉)、`rsi_oversold`(RSI超卖) |
| 均线/布林 | `ma_long`(均线多头发散)、`boll_bt_upper`(布林带上轨突破) |
| 资金面 | `major_force`(主力抢筹)、`institution_chasing`(机构接盘) |

> **完整策略列表参见** [references/ai_usage_guide.md](./references/ai_usage_guide.md)「六、策略选股完整列表」

---

## 排行选股（ranking）

> 当用户问"评分TOP10"、"连续涨停的股票"、"估值排行"、"央企里评分最高的10只"、"MACD金叉中估值最低的"等**按指标排序**问题时使用

统一的"按指标排序选股"入口，支持 **5 类指标源**（涨跌停 / 财务 / 评分 / 两融 / 资金流入），核心特色是可在板块、标签、策略、事件结果内做**二次排序**。

```bash
# 查看所有可用指标
westock-tool ranking --list
westock-tool ranking --list 评分                          # 按分类筛选

# ── 评分（score） ──
westock-tool ranking CompScore --limit 10                 # 综合评分 TOP10（如需查"单只股票的评分"请用 westock-data score）
westock-tool ranking CompScore --type weekly              # 评分周变动（cur/weekly/monthly）

# ── 涨跌停（market） ──
westock-tool ranking limitup_days                         # 连续涨停天数
westock-tool ranking limitup_seal_volume                  # 涨停封单量

# ── 财务（financial） ──
westock-tool ranking fin_valuation --limit 10             # 估值排行（默认升序看最低 PE）
westock-tool ranking fin_growth                           # 成长能力
westock-tool ranking fin_profit                           # 盈利能力（ROE）

# ── 两融（margin） ──
westock-tool ranking margin_balance --limit 20            # 两融余额最多
westock-tool ranking margin_chg_d                         # 两融日加仓榜（--asc 看日减仓榜）
westock-tool ranking margin_in_days --min-MtInDays 5      # 两融连续扩大≥5天

# ── 资金流入（capital） ──
westock-tool ranking cap_main_net --limit 20              # 主力净流入榜（--asc 看主力净流出榜）
westock-tool ranking cap_main_5d                          # 主力 5 日合计净流入榜
westock-tool ranking cap_in_days --min-MainInDays 3       # 主力连续净流入≥3天
```

### ⭐ 范围限定（核心能力）

```bash
westock-tool ranking CompScore --within-label shareholder_central_state    # 央企里评分最高
westock-tool ranking fin_valuation --within-strategy macd_golden           # MACD金叉中估值最低
westock-tool ranking CompScore --within-event shareunlock_next_90          # 限售解禁股评分
westock-tool ranking fin_valuation --universe 11010001                     # 板块内估值排行
westock-tool ranking margin_chg_d --universe 11010001 --limit 10           # 板块内两融加仓
westock-tool ranking cap_main_5d --within-label shareholder_central_state  # 央企里主力5日累计加仓最多

# 阈值筛选 / 升序 / 历史 / 分页
westock-tool ranking CapScore --min-CompScore 70 --limit 10
westock-tool ranking CompScore --asc                       # 评分最低
westock-tool ranking CompScore --date 2026-04-20           # 历史日期
westock-tool ranking limitup_days --limit 50 --offset 20
```

**主要参数**：指标名（必填）、`--type cur|weekly|monthly`（仅 score）、`--within-label|--within-strategy|--within-event`（**三者互斥**）、`--universe <板块>`、`--min-<字段> 值`、`--asc`、`--date`、`--limit` / `--offset`、`--list [分组]`。

**可用指标速查**：

| 分类 | 指标代码 |
|------|---------|
| 评分 | `CompScore`(综合)/`CapScore`(资金)/`FunmScore`(基本面)/`RiskScore`(风险)/`TecScore`(技术) |
| 涨跌停 | `limitup_days`/`limitup_seal_volume`/`limitdn_days`/`limitdn_seal_volume` |
| 财务排行 | `fin_valuation`(估值)/`fin_growth`(成长)/`fin_profit`(盈利)/`fin_pershare`(每股)/`fin_cash_size`(现金流规模)/`fin_operation`(营运)/`fin_liquidity`(偿债)/`fin_profit_structure`(收入结构) |
| 两融排行 | `margin_balance`(两融余额)/`margin_chg_d/w/m/q/y`(日/周/月/季/年变动)/`margin_in_days`(连续扩大天数)/`margin_out_days`(连续缩小天数) |
| 资金流入 | `cap_main_net`(主力净流入)/`cap_retail_net`(散户净流入)/`cap_main_5d`(主力5日合计)/`cap_in_days`(主力连续净流入天数)/`cap_out_days`(主力连续净流出天数) |

**`--min-<字段>` 字段名速查**（指标代码 ↔ `--min-` 拼接的字段名不一致，常用对照）：

| 指标代码 | `--min-<字段>` 的字段名（数据列名） |
|---------|------------------------|
| `CompScore` / `CapScore` / `FunmScore` / `RiskScore` / `TecScore` | 同名 |
| `limitup_days` | `LimitUpDays` |
| `margin_chg_d/w/m/q/y` | `MChgD` / `MChgW` / `MChgM` / `MChgQ` / `MChgY` |
| `margin_in_days` / `margin_out_days` | `MtInDays` / `MtOutDays` |
| `cap_main_net` | `MainNetIn` |
| `cap_retail_net` | `RetailNetOut` |
| `cap_main_5d` | `MainSum5d` |
| `cap_in_days` / `cap_out_days` | `MainInDays` / `MainOutDays` |
| `fin_valuation` / `fin_profit` / `fin_pershare` | `PE_TTM` / `RoeTTM` / `EpsTTM` |

---

## 事件选股（event）

> 当用户问"近期有哪些股票限售解禁"、"董监高增减持的股票"、"回购的股票"等**事件+时间窗口**问题时使用
> **`event` vs `label`**：label 是**静态分类**（央企永远是央企），event 是**动态时间窗口**（"限售解禁"随时间变化）。

```bash
westock-tool event --list                                  # 查看所有可用事件
westock-tool event --list 董监高变动                        # 按分组筛选
westock-tool event shareunlock_next_90                     # 单事件
westock-tool event manager_change,manager_sharechg         # 多事件并查（不做交集）
westock-tool event block_past_30 --limit 50 --offset 20    # 分页
```

**主要参数**：事件名（必填，逗号分隔多个）、`--limit` / `--offset`、`--list [分组]`。支持任意 listcode 字符串。

**可用事件概览**（仅展示代表性条目，**完整且最新清单必须执行 `event --list`**）：

| 分类 | 代表性事件 |
|------|----------|
| 分红 | `dividend_plan`(预案)/`dividend_exdiv`(除权) |
| 业绩 | `earnings_schedule`(预约披露)/`earnings_forecast`(预告)/`earnings_release`(披露) |
| 定增 | `seo_past_7`(前一周)/`seo_next_30`(后一月) |
| 董监高变动 | `manager_change`(变动)/`manager_sharechg`(增减持)/`manager_shareplan_sell_incoming`(计划减持) |
| 限售解禁 | `shareunlock_next_90`(预计三月内)/`shareunlock_incoming`(实际解禁) |
| 回购 | `buyback` |
| 交易异动 | `block_past_30`(大宗交易)/`longhu_statis_past_15`(龙虎榜统计) |
| 指数变动 | `index_add_incoming`(将加入)/`index_del_incoming`(将踢出) |
| 重大事项 | `merger_unclosed`(吸收合并)/`regroup_unclosed`(资产重组) |

> **完整事件列表参见** [references/ai_usage_guide.md](./references/ai_usage_guide.md)「八、事件选股完整列表」

---

## 标签选股（label）

> 当用户问"央企有哪些"、"ST股"、"新股"、"次新股"、"破净股"、"高ROE股"等**分类标签**问题时使用

```bash
westock-tool label --list                                  # 查看所有可用标签
westock-tool label --list 股东属性                          # 按分组筛选
westock-tool label shareholder_central_state               # 单标签
westock-tool label valuation_lowpb,fin_high_roettm         # 多标签并查（不做交集）
westock-tool label risk_st --limit 50 --offset 20          # 分页
westock-tool label shareholder_central_state --start 2026-04-01 --end 2026-04-10  # 区间（多天必须用）
```

**主要参数**：标签名（必填，逗号分隔多个）、`--date` / `--start` / `--end`、`--limit` / `--offset`、`--list [分组]`。支持任意 listcode。

**可用标签概览**（仅展示代表性条目，**完整且最新清单必须执行 `label --list`**）：

| 分类 | 代表性标签 |
|------|----------|
| 股东属性 | `shareholder_central_state`(央企)/`shareholder_local_state`(国企)/`shareholder_hkfund`(陆股通) |
| 风险标签 | `risk_st`(ST股)/`risk_broken_ipo`(破发股) |
| 估值水平 | `valuation_lowpb`(破净股)/`valuation_negpe`(亏损股) |
| 财务特征 | `fin_high_roettm`(高ROE)/`fin_forecast_inc`(业绩预增)/`fin_healthy_growth`(降本增效) |
| 上市时间 | `listeddate_5days`(新股5日内)/`listeddate_3mons`(近端次新) |
| 价格与市值 | `price_up1000`(千元股)/`marketcap_super_big`(超大盘)/`marketcap_super_small`(超小盘) |

> **完整标签列表参见** [references/ai_usage_guide.md](./references/ai_usage_guide.md)，或用 `westock-tool label --list` 实时查看

---

## ETF 选基（label/ranking --asset etf）

> 当用户问"高股息 ETF 有哪些"、"千亿规模基金"、"科创板占比高的 ETF"、"ETF 规模榜"、"近 20 日涨幅最高的 ETF"等**ETF 发现/排行**问题时使用。
> ETF 选基复用 `label`（标签筛选）和 `ranking`（按指标排序）两个命令，通过 `--asset etf` 切换作用对象——与 `--market hk/us` 切换市场的设计模式一致。
> 与 `westock-data etf detail/holdings/...`（按代码精查）形成"先发现后精查"链路。

```bash
# 标签筛选（复用 label）
westock-tool label --asset etf --list                          # 列出全部 KYP 主题池
westock-tool label --asset etf --list 行情表现                  # 按分组筛选
westock-tool label high_dividend --asset etf                   # 高股息 ETF
westock-tool label low_valuation,high_roe --asset etf          # 多池并查
westock-tool label size_100 --asset etf --limit 50 --offset 50 # 百亿基金分页

# 横截面排行（复用 ranking）
westock-tool ranking --asset etf --list                        # 列出全部 ETF 排行指标
westock-tool ranking size --asset etf --limit 20               # 规模榜 TOP20（默认 TotalAsset 降序）
westock-tool ranking valuation --asset etf --by PB --asc       # 估值最低（按 PB 升序）
westock-tool ranking valuation_pct --asset etf --by PE_TTM_PCT # 估值百分位最低（默认升序）
westock-tool ranking qt_chg_interval --asset etf --by ChgPct20D # 近 20 日涨幅榜
westock-tool ranking turn_interval --asset etf --by EtfTurnoverRAvgM # 月均换手率榜
westock-tool ranking disc_interval --asset etf --by EtfDiscAvgW # 周均溢价榜
```

### ETF 主题池速查（仅代表性条目，**完整且最新清单必须执行 `label --asset etf --list`**）

| 分类 | 代表性池 |
|------|----------|
| 上市时间 | `issue_new`(最新发行)、`issue_in_3m/in_1y/over_5y` |
| 规模 | `size_1000`(千亿)、`size_500`、`size_100`(百亿) |
| 获奖 | `award_golden_bull`(得过金牛)、`award_all` |
| 持仓特征 | `high_stib_bj`(科创北证占比高)、`high_minicap`、`high_supercap`、`high_price_stocks` |
| 行情表现 | `qt_high_chg`(高涨幅)、`qt_high_vol`、`qt_high_amp`、`qt_high_unitnv` |
| 重仓股表现 | `stocks_high_up`、`stocks_high_super_bullish`、`stocks_high_bullish` |
| 主力资金 | `cap_focus_daily/weekly/monthly/quarterly/yearly`(主力看好) |
| 基本面 | `low_valuation`(低估值)、`high_dividend`(高股息)、`high_roe` |
| 诊股评分 | `high_score_comp/tec/cap/sentiment/fundamental/risk` |
| 境外/特殊 | `t0`(可T+0)、`america`、`euro`、`japan`、`hk` |
| 类型/策略 | `commodity`(商品型)、`bond`(债券型)、`currency`(货币型)、`strategy_div`(红利) |

### ETF 排行指标速查（仅代表性条目，**完整且最新清单必须执行 `ranking --list --asset etf`**）

| 指标 | 中文 | 默认排序字段 | 默认方向 | 可选字段 |
|------|------|-----------|---------|---------|
| `size` | ETF 规模 | `TotalAsset` | ↓ | TotalAsset/NetValue/NetValueTotal |
| `nvsize_interval` | ETF 总规模波动 | `EtfSize` | ↓ | EtfSize |
| `valuation` | 估值绝对值 | `PE_TTM` | ↑ | PE_TTM/PB/PS_TTM/PCF_TTM/PEG/ROE/DIV_TTM |
| `valuation_pct` | 估值历史百分位 | `PE_TTM_PCT` | ↑ | PE_TTM_PCT/PB_PCT/PS_TTM_PCT/PCF_TTM_PCT/PEG_PCT/ROE_PCT/DIV_TTM_PCT |
| `qt_daily` | 单日行情 | `ChgPct` | ↓ | ChgPct/TurnoverRate/TurnoverValue |
| `qt_chg_interval` | 区间涨跌 | `ChgPct20D` | ↓ | ChgPct/ChgPct5D/ChgPct20D/ChgPct60D/ChgPct52W/ChgPctYtd |
| `turn_interval` | 换手率波动 | `EtfTurnoverRAvgM` | ↓ | EtfTurnoverR/...AvgW/AvgM/AvgQ/AvgY |
| `amt_interval` | 成交额波动 | `EtfTurnoverAvgM` | ↓ | EtfTurnover/...AvgW/AvgM/AvgQ/AvgY |
| `disc_interval` | 溢折率波动 | `EtfDiscAvgM` | ↓ | EtfDisc/...AvgW/AvgM/AvgQ/AvgY |

**主要参数**：池名/指标名（必填）、`--asset etf`（必填，切换为 ETF 维度）、`--by <字段>`（仅 ranking）、`--asc`（覆盖默认方向）、`--date`、`--limit` / `--offset`、`--list`。

> **决策入口**：
> - 用户带"标签/主题"（如"高股息 / 千亿基金 / 科创板占比高"）→ `label ... --asset etf`
> - 用户带"排序/榜单"（如"规模最大 / 涨幅前 10 / 估值最低"）→ `ranking ... --asset etf`
> - 跨市场行情/单只 ETF 详情 → 改用 `westock-data etf detail/holdings/...`

---

## 股票代码格式

| 市场 | 格式 | 示例 |
|------|------|------|
| 沪市/科创板 | sh + 6位数字 | `sh600519`、`sh688981` |
| 深市 | sz + 6位数字 | `sz000001` |
| 港股 | hk + 5位数字 | `hk00700` |
| 美股 | us + 代码 | `usAAPL` |

---

## 常用字段速查（跨市场差异）

| 类别 | 沪深(HS) | 港股(HK) | 美股(US) |
|------|----------|----------|----------|
| 市盈率TTM | PE_TTM | PeTTM | PeTTM |
| 市净率 | PB | PbLF | PbLF |
| 股息率TTM | DividendRatioTTM | DivTTM | DivTTM |
| 收盘价 | ClosePrice | ClosePrice | ClosePrice |
| 涨跌幅 | ChangePCT | ChangePCT | ChangePCT |
| 总市值 | TotalMV (元) | TotalMV (元) | TotalMV (元) |
| ROE(TTM) | ROETTM | RoeWeighted | ROE |
| 主力净流入 | MainNetFlow | MainNetFlow | - |

> ⚠️ 港股 `PsTTM`/`PcfTTM` 仅选股查询支持，快照查询返回 0。
>
> **完整字段速查表（含行情、财务、技术指标等全部字段）参见** [references/fields-guide.md](./references/fields-guide.md)

---

## 使用规范

- ✅ 使用 `westock-tool` CLI 命令执行选股查询，输出 Markdown 表格，AI 直接从表格读取数据
- ✅ 查询结果应转为表格或可读格式展示，禁止直接输出原始 JSON
- ❌ 不创建临时脚本文件，不将数据分析逻辑写成独立脚本
- ⚠️ **港股必须指定 `--market hk`，美股必须指定 `--market us`**
- ⚠️ 筛选 PE/PB 时排除负值：`intersect([PE_TTM > 0, PE_TTM < 20])`
- ⚠️ 沪深和港股/美股的估值字段名不同，切勿混用

---

## 常见场景速查

```
【命令选择】
- 策略名称（MACD金叉、巴菲特等）→ strategy
- 分类标签（央企、ST股、新股、破净股等）→ label
- 事件时间窗口（限售解禁、董监高增持等）→ event
- 自定义条件（PE<20且ROE>15）→ filter 表达式
- 预设函数（低估值、高股息等）→ filter --preset
- 按指标排序（评分/涨跌停/财务/两融/资金流入）→ ranking
- 组合查询（X 里的 Y 最高）→ ranking --within-*
- ETF 主题/榜单 → label / ranking 加 --asset etf

【典型示例】
strategy macd_golden                                                # MACD金叉
label shareholder_central_state                                     # 央企
label listeddate_5days                                              # 新股（5日内）
event shareunlock_next_90                                           # 限售解禁
ranking CompScore --limit 10                                        # 综合评分TOP10
ranking limitup_days                                                # 连续涨停
ranking fin_valuation --limit 20                                    # 估值排行
ranking margin_chg_d --limit 20                                     # 两融日加仓榜
ranking cap_main_5d --limit 20                                      # 主力5日合计净流入榜
ranking cap_in_days --min-MainInDays 3                              # 主力连续净流入≥3天
ranking CompScore --within-label shareholder_central_state          # 央企里评分最高
ranking fin_valuation --within-strategy macd_golden                 # MACD金叉中估值最低
filter "intersect([PE_TTM > 0, PE_TTM < 15, ROETTM > 15])" --by ROETTM --desc   # 低估值蓝筹
filter --preset HighDividend --market hk                            # 港股高股息
label high_dividend --asset etf                                     # 高股息 ETF
label size_100 --asset etf --limit 50                               # 百亿基金
ranking size --asset etf --limit 20                                 # ETF 规模榜 TOP20
ranking valuation_pct --asset etf --by PE_TTM_PCT                   # ETF PE 历史百分位最低
ranking qt_chg_interval --asset etf --by ChgPct20D --limit 10       # 近 20 日涨幅前 10 ETF
```

> **更多场景示例参见** [references/scenarios-guide.md](./references/scenarios-guide.md)
> **详细返回格式、分析模板、选股场景详解参见** [references/ai_usage_guide.md](./references/ai_usage_guide.md)
>
> **检索提示**（ai_usage_guide.md 较大，按需 grep 定位）：
> - 查某类完整清单 → 搜章节标题：`## 六、`（策略）、`## 七、`（标签）、`## 八、`（事件）、`## 九、`（排行指标）；ETF 搜 `--asset etf`
> - 查某个条目 → 直接搜短名（如 `macd_golden` / `shareholder_central_state` / `shareunlock_next_90` / `qt_chg_interval`）
> - 查字段对照 → 搜 `--min-` 或字段名（如 `MainSum5d`）

---

## 数据更新频率

| 数据类型 | 更新频率 |
|----------|----------|
| 条件选股 | 每日收盘后更新 |
| 策略选股 | 每日收盘后更新 |
| 标签选股 | 跟随财报/公告等基础数据更新 |
| 事件选股 | 跟随公告/事件等基础数据更新 |
| 排行选股（涨跌停指标） | 盘中实时更新 |
| 排行选股（财务/评分指标） | 每日收盘后更新 |
| 排行选股（两融指标） | 每日收盘后更新（两融余额T+1披露） |
| 排行选股（资金流入指标） | 盘中实时更新（基于逐笔成交） |

---

## 重要声明

> ⚠️ **重要声明**：
>
> 1. 本技能仅提供客观市场数据的筛选与展示服务，不含任何主观分析、投资评级或交易建议。
> 2. 本技能不构成证券投资咨询服务，使用本技能获取的数据不应作为投资决策的唯一依据。
> 3. 数据可能存在延迟，请以交易所官方数据为准。
> 4. 投资有风险，决策需谨慎。如需专业投资建议，请咨询持牌证券投资顾问机构。

**数据来源**：腾讯自选股数据接口

---
