# WeStock Screener - AI 深度参考指南 · 分册 02

[本手册索引](ai_usage_guide.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

### 3.11 排行选股（ranking）

排行选股是**按指标排序选股**的统一入口，支持**六类指标源**（涨跌停 / 财务 / 评分 / 两融 / 资金流入 / 北向活跃），核心特色是可在板块、标签、策略、事件结果内做**二次排序**（北向活跃榜单除外，为固定 Top20）。

```bash
# 查看所有可用指标
westock screen ranking --list

# ── 评分排行（score 源） ──
westock screen ranking --type CompScore --limit 10              # 综合评分 TOP10
westock screen ranking --type CapScore --limit 20               # 资金评分 TOP20
westock screen ranking --type RiskScore --limit 15              # 风险评分排行
westock screen ranking --type CompScore --period weekly           # 评分周变动排行
westock screen ranking --type CompScore --period monthly          # 评分月变动排行

# ── 涨跌停排行（market 源） ──
westock screen ranking --type limitup_days                      # 连续涨停天数排行
westock screen ranking --type limitup_seal_volume               # 涨停封单量排行
westock screen ranking --type limitdn_days                      # 连续跌停天数排行
westock screen ranking --type limitdn_seal_volume               # 跌停封单量排行

# ── 财务排行（financial 源） ──
westock screen ranking --type fin_valuation --limit 10          # 估值排行（默认升序，PE最低）
westock screen ranking --type fin_growth --limit 20             # 成长能力排行
westock screen ranking --type fin_profit                        # 盈利能力排行
westock screen ranking --type fin_pershare                      # 每股指标排行
westock screen ranking --type fin_cash_size                     # 现金流规模排行

# ── 两融排行（margin 源） ──
westock screen ranking --type margin_balance --limit 20         # 两融余额最多 TOP20
westock screen ranking --type margin_chg_d                      # 两融日加仓榜（--asc 看日减仓榜）
westock screen ranking --type margin_chg_w                      # 两融周加仓榜
westock screen ranking --type margin_chg_m                      # 两融月加仓榜
westock screen ranking --type margin_chg_q                      # 两融季加仓榜
westock screen ranking --type margin_chg_y                      # 两融年加仓榜
westock screen ranking --type margin_in_days --min-MtInDays 5   # 两融连续扩大≥5天
westock screen ranking --type margin_out_days                   # 两融连续缩小天数排行

# ── 资金流入排行（capital 源） ──
westock screen ranking --type cap_main_net --limit 20           # 主力净流入榜（--asc 看主力净流出榜）
westock screen ranking --type cap_retail_net --limit 20         # 散户净流入榜
westock screen ranking --type cap_main_5d --limit 20            # 主力 5 日合计净流入榜
westock screen ranking --type cap_in_days --min-MainInDays 3    # 主力连续净流入≥3天
westock screen ranking --type cap_out_days                      # 主力连续净流出天数排行

# ── 北向活跃排行（north 源，固定 Top20，勿加 --limit） ──
westock screen ranking --type north_active_d                    # 近1周按日成交活跃股
westock screen ranking --type north_active_m                    # 近半年按月成交活跃股
westock screen ranking --type north_appear_w                    # 周上榜次数（AppearanceCnt 降序）

# ── 范围限定（核心特色） ──
westock screen ranking --type CompScore --within-label shareholder_central_state --limit 10  # 央企里评分最高
westock screen ranking --type fin_valuation --within-strategy macd_golden                    # MACD金叉中估值最低
westock screen ranking --type CompScore --within-event shareunlock_next_90                   # 限售解禁股评分排行
westock screen ranking --type fin_valuation --universe 11010001                              # 半导体板块估值排行
westock screen ranking --type margin_chg_d --universe 11010001 --limit 10                    # 半导体板块两融日加仓最多
westock screen ranking --type cap_main_5d --within-label shareholder_central_state           # 央企里主力 5 日累计加仓最多

# ── 阈值筛选 ──
westock screen ranking --type CapScore --min-CompScore 70 --limit 10   # 综合评分≥70按资金评分排序

# ── 历史日期 / 排序方向 / 分页 ──
westock screen ranking --type CompScore --date 2026-04-20
westock screen ranking --type CompScore --asc                   # 评分最低
westock screen ranking --type limitup_days --limit 50 --offset 20

```

**核心参数**：

| 参数 | 说明 |
|------|------|
| `--type <指标>` | **必填**，排行指标（共 **36 个**）：涨跌停（`limitup_*`/`limitdn_*`，4 个）、财务（`fin_*`，8 个）、评分（`CompScore`/`CapScore`/`FunmScore`/`RiskScore`/`TecScore`，5 个）、两融（`margin_*`，8 个）、资金流入（`cap_*`，5 个）、**北向活跃**（`north_*`，6 个，固定 Top20，不支持 `--limit`/`--asc`/`--within-*`） |
| `--period` | 评分类型：`cur`(默认) / `weekly` / `monthly`，仅 score 指标有效 |
| `--within-label` | 限定在指定标签内排行（如 `shareholder_central_state`） |
| `--within-strategy` | 限定在指定策略内排行（如 `macd_golden`） |
| `--within-event` | 限定在指定事件内排行（如 `shareunlock_next_90`） |
| `--universe` | 限定在板块内排行（板块代码） |
| `--min-<字段> 值` | 阈值筛选（如 `--min-MtInDays 5` 两融连续扩大≥5天） |
| `--asc` | 升序（默认降序；估值类默认升序）。变动类指标支持 `--asc` 看反向（如 `cap_main_net --asc` 看主力净流出榜） |
| `--date` | 查询日期，默认今天 |
| `--limit` / `--offset` | 分页 |
| `--list [分组]` | 列出所有指标，可按分组筛选（如 `--list 评分` / `--list 两融排行` / `--list 资金流入`） |

> ⚠️ `--within-label` / `--within-strategy` / `--within-event` **三者互斥**，只能用一个。

**指标维度**：

- **评分维度**：综合(CompScore) / 资金(CapScore) / 基本面(FunmScore) / 风险(RiskScore) / 技术(TecScore)
- **财务维度**：估值 / 成长 / 盈利 / 每股 / 现金流 / 营运 / 偿债 / 收入结构（8 个清单）
- **涨跌停维度**：连续涨跌停天数 + 封单量（4 个指标）
- **两融维度**：余额 / 日周月季年变动 / 连续扩大缩小天数（来自 `peer_cap_margin_daily`/`_interval`/`_days` 三个清单）
- **资金流入维度**：主力净流入 / 散户净流入 / 5日合计 / 连续净流入流出天数（来自 `peer_cap_daily`/`peer_cap_interval_money`/`peer_cap_interval_days` 三个清单）
- **组合查询**：`--within-*` 可与其他选股命令联动（如"MACD金叉中估值最低"、"央企里主力加仓最多"）
- 排行选股仅支持 A 股

#### 两融指标字段说明

来自 `peer_cap_margin_daily`、`peer_cap_margin_interval`、`peer_cap_margin_days` 三个清单：

| 指标 key | sortField | 字段含义 | 默认排序 | --asc 用途 |
|----------|-----------|---------|---------|-----------|
| `margin_balance` | MarginTrade | 最新融资融券余额（万） | desc | 余额最少 |
| `margin_chg_d` | MChgD | 融资融券余额日变动（万） | desc 加仓榜 | **日减仓榜** |
| `margin_chg_w` | MChgW | 融资融券余额周变动（万） | desc 加仓榜 | **周减仓榜** |
| `margin_chg_m` | MChgM | 融资融券余额月变动（万） | desc 加仓榜 | **月减仓榜** |
| `margin_chg_q` | MChgQ | 融资融券余额季变动（万） | desc 加仓榜 | **季减仓榜** |
| `margin_chg_y` | MChgY | 融资融券余额年变动（万） | desc 加仓榜 | **年减仓榜** |
| `margin_in_days` | MtInDays | 两融连续扩大天数（天） | desc | 短的排前 |
| `margin_out_days` | MtOutDays | 两融连续缩小天数（天） | desc | 短的排前 |

> **数据更新**：两融余额 T+1 披露，每日收盘后更新。**单位说明**：变动数额单位为"万元"。

#### 资金流入指标字段说明

来自 `peer_cap_daily`、`peer_cap_interval_money`、`peer_cap_interval_days` 三个清单：

| 指标 key | sortField | 字段含义 | 默认排序 | --asc 用途 |
|----------|-----------|---------|---------|-----------|
| `cap_main_net` | MainNetIn | 主力资金净流入（万） | desc 主力净流入榜 | **主力净流出榜** |
| `cap_retail_net` | RetailNetOut | 散户资金净流入（万） | desc 散户净流入榜 | **散户净流出榜** |
| `cap_main_5d` | MainSum5d（派生） | 主力 5 日合计净流入（万）= MainT0+T1+T2+T3+T4 | desc | **5 日累计净流出榜** |
| `cap_in_days` | MainInDays | 主力连续净流入天数（天） | desc | 短的排前 |
| `cap_out_days` | MainOutDays | 主力连续净流出天数（天） | desc | 短的排前 |

> **数据守恒**：散户净流入榜与主力净流出榜首位通常对应（同一只股票），体现资金流转零和性。
> **派生字段说明**：`MainSum5d` 由客户端聚合 `peer_cap_interval_money` 清单的 T0~T4 五日数据得到，用于"5 日合计净流入榜"排序。
> **数据更新**：盘中实时更新（基于逐笔成交）。**单位说明**：均为"万元"。

**ranking + 数据查询联动**：

```bash
# 先用排行选股找出综合评分最高的股票，再查看个股详情
westock screen ranking --type CompScore --limit 5
# → 从结果中提取股票代码
# → westock score sh600519       # 查看评分详情及变动
# → westock quote sh600519       # 查看行情

# 先找出连续涨停的股票，再查看个股详情
westock screen ranking --type limitup_days --limit 10
# → westock quote <涨停股代码列表>  # 查看行情

# 先找两融加仓最多的股票，再查融资融券明细
westock screen ranking --type margin_chg_d --limit 10
# → westock fund margin sh600519   # 查看个股两融详情

# 先找主力 5 日加仓最多的股票，再查资金流向时间序列
westock screen ranking --type cap_main_5d --limit 10
# → westock fund flow sh600519 --start 2026-04-15 --end 2026-04-20  # 查看资金流向时间序列

```

### 3.11.1 ETF 排行选基（ranking --asset etf）

通过 `--asset etf` 切换 ranking 命令到 ETF 维度（多类 ETF 排行指标，~1530 只 ETF 全市场）。与默认的股票排行职责并列：

```bash
# 列出全部 ETF 排行指标
westock screen ranking --asset etf --list

# 规模榜
westock screen ranking --type size --asset etf --limit 20                 # 默认 TotalAsset 降序

# 估值榜（--orderby 切换字段，--asc 覆盖默认方向）
westock screen ranking --type valuation --asset etf --orderby PB --asc         # 按 PB 升序（最低估值）
westock screen ranking --type valuation_pct --asset etf --orderby PE_TTM_PCT   # PE 历史百分位最低（默认升序）

# 区间表现
westock screen ranking --type qt_chg_interval --asset etf --orderby ChgPct20D --limit 10  # 近 20 日涨幅榜
westock screen ranking --type turn_interval --asset etf --orderby EtfTurnoverRAvgM        # 月均换手率榜
westock screen ranking --type disc_interval --asset etf --orderby EtfDiscAvgW             # 周均溢价榜

```

**ETF 排行指标速查**：

| 指标 | 中文 | 默认排序字段 | 默认方向 |
|------|------|-----------|---------|
| `size` | ETF 规模 | `TotalAsset` | ↓ |
| `nvsize_interval` | ETF 总规模波动 | `EtfSize` | ↓ |
| `valuation` | 估值 | `PE_TTM` | ↑ |
| `valuation_pct` | 估值历史百分位 | `PE_TTM_PCT` | ↑ |
| `qt_chg_interval` | 区间涨跌幅 | `ChgPct20D` | ↓ |
| `turn_interval` | 区间换手率均值 | `EtfTurnoverRAvgM` | ↓ |
| `disc_interval` | 溢折率波动 | `EtfDiscAvgM` | ↓ |

**核心参数**：

| 参数 | 说明 |
|------|------|
| `--type <指标>` | ETF 排行指标之一 |
| `--asset etf` | **必填**，切换为 ETF 维度（不传则走股票排行） |
| `--orderby <字段>` | 覆盖默认排序字段；valuation 如 `PB`、`PS_TTM`、`DIV_TTM`，以 [ETF 指标表](./etf-pools.md) 和当前 CLI 支持为准，不能猜别名 |
| `--asc` | 覆盖默认方向 |
| `--date` / `--limit` / `--offset` / `--list` | 同股票排行 |

> ⚠️ **数据职责边界**：
> - 用户问"ETF 规模最大/估值最低/涨幅最高"等**横截面排行** → 走 `westock screen ranking --asset etf`
> - 用户给具体 ETF 代码问详情 → 走 `westock etf profile` / `westock etf overview` 等子命令
>
> ⚠️ **限制**：ETF 排行不支持 `--within-label/--within-strategy/--within-event` 范围限定（这些仅作用于股票池）。

---

## 四、预设选股函数完整列表

> `westock screen condition --preset` 是 filter 命令的快捷方式，用预设条件表达式筛选，输出含指标列的 Markdown 表格。
> 与 `westock screen strategy` 命令的区别：strategy 输出仅含 code/name 的表格，preset 输出含指标列的表格。

#### 估值分析类

| 函数名 | 说明 | 内置默认值 |
|--------|------|------|
| `LowPE` | 低PE筛选 | `maxPE`=20 |
| `LowPB` | 破净股筛选(PB<1) | `maxPB`=1 |
| `HighDividend` | 高股息筛选 | `minDividend`=3% |
| `ValuationPercentile` | 估值百分位低位 | `maxPercentile`=30 |
| `PEG` | PEG策略(PEG<1) | `maxPEG`=1, `minGrowth`=20% |

#### 技术指标类


| 函数名 | 说明 | 内置默认值 |
|--------|------|------|
| `KDJOversold` | KDJ超卖 | `maxJ`=20 |
| `RSIOversold` | RSI超卖 | `maxRSI`=30 |
| `NineTurnGreen9` | 神奇九转绿9信号 | - |

#### 财务分析类

| 函数名 | 说明 | 内置默认值 |
|--------|------|------|
| `HighROE` | 高ROE筛选 | `minROE`=15% |
| `HighGrowth` | 高成长筛选 | `minRevenueGrowth`=20%, `minProfitGrowth`=30% |
| `LowDebt` | 低负债筛选 | `maxDebtRatio`=50% |
| `PositiveCashFlow` | 正现金流筛选 | - |

#### 资金流向类

| 函数名 | 说明 | 内置默认值 |
|--------|------|------|
| `MainInflow` | 主力资金流入 | `minInflow`=1亿 |
| `SustainedInflow` | 主力持续流入(5/10/20日) | - |
| `HighShortRatio` | 高卖空比例 | `minShortRatio`=10% |

#### 机构评级类（港股/美股）

| 函数名 | 说明 | 内置默认值 |
|--------|------|------|
| `HighRating` | 高机构评级 | `minBuyRating`=5 |
| `TargetPriceUpside` | 目标价上行空间 | `minUpside`=20% |

#### 组合策略类

| 函数名 | 说明 | 内置默认值 |
|--------|------|------|
| `HighDividendLowValuation` | 高股息+低估值 | `minDividend`, `maxPE`, `maxPB` |
| `WhiteHorseGrowth` | 白马成长(高ROE+稳定增长) | - |
| `Turnaround` | 困境反转 | `minTurnaround`=50% |
| `SmallCapValue` | 小盘价值(20-100亿市值) | - |
| `TechFundamentalCombo` | 技术面+基本面组合 | - |

> ⚠️ 预设函数的参数均为内置默认值，不支持通过 CLI 传入自定义参数。如需自定义条件，请使用 `westock screen condition` 表达式语法手写条件。

---

## 五、错误处理

- 检查返回 JSON 的 `code` 字段，`0` 表示成功，非 `0` 时查看 `msg` 获取原因
- 常见错误：字段名混用（如沪深用了 `PeTTM`）、港股/美股未指定 `--market`、表达式语法错误

---

**记住**：选股查询是 Skill 的职责，数据分析是 AI 的职责！

---

## 六、策略选股完整列表

| 分类 | 策略代码 | 名称 |
|------|---------|------|
| 基本面 | `big_cap` | 行业高增长 |
| 基本面 | `pb_roe` | 高盈利价值 |
| 基本面 | `high_dividend` | 高股息 |
| 基本面 | `food_beverage` | 低估食品饮料 |
| 基本面 | `household_appliances` | 优质家电 |
| 基本面 | `profit_preannounce` | 业绩预增 |
| 大师策略 | `buffet` | 价值龙头 |
| 大师策略 | `trinity` | 三一投资型风格选股法 |
| 大师策略 | `davis` | 估值业绩齐飞 |
| 大师策略 | `derryman` | 逆向投资 |
| 大师策略 | `graham` | 格雷厄姆型风格策略 |
| 大师策略 | `fisher` | 费雪型风格策略 |
| 综合 | `golden_strategy` | 策略金股 |
| 综合 | `increase_holding` | 高管增持 |
| 综合 | `investor_investigation` | 机构调研 |
| K线形态 | `dawn_breaks` | 曙光初现 |
| K线形态 | `up_down_up` | 两阳夹一阴 |
| K线形态 | `morning_star` | 早晨之星 |
| K线形态 | `red_three_solider` | 红三兵 |
| K线形态 | `zthmq` | 涨停回马枪 |
| K线形态 | `rise_big_up` | 跳空向上 |
| K线形态 | `hibiscus_out_of_water` | 出水芙蓉 |
| K线形态 | `over_drop_rebound` | 超跌反弹 |
| K线形态 | `long_red_show_road` | 长阳指路 |
| K线形态 | `xianrenzhilu` | 仙人指路 |
| K线形态 | `open_high_close_low` | 高开低走 |
| 指标信号 | `macd_golden` | MACD金叉 |
| 指标信号 | `kdj_golden` | KDJ金叉 |
| 指标信号 | `bias_golden` | BIAS金叉 |
| 指标信号 | `rsi_golden` | RSI金叉 |
| 指标信号 | `rsi_oversold` | RSI超卖 |
| 指标信号 | `bias_oversold` | BIAS超卖 |
| 指标信号 | `wr_oversold` | WR超卖 |
| 指标信号 | `kdj_super_golden` | 黄金KDJ |
| 指标信号 | `macd_bottom_deviate` | MACD底背离 |
| 指标信号 | `macd_red_wave` | MACD红二波 |
| 指标信号 | `kdj_bottom_deviate` | KDJ底背离 |
| 指标信号 | `bias_bottom_deviate` | BIAS底背离 |
| 指标信号 | `rsi_bottom_deviate` | RSI底背离 |
| 指标信号 | `sar_buy_signal` | SAR买入信号 |
| 均线/布林 | `one_rise_three_ma` | 一阳三线 |
| 均线/布林 | `ma_long` | 均线多头发散 |
| 均线/布林 | `ma_long_boll_bt_mid` | 均线多头+布林中轨突破 |
| 均线/布林 | `boll_bt_upper` | 布林带上轨突破 |
| 均线/布林 | `boll_bt_mid` | 布林带中轨突破 |
| 均线/布林 | `ma_stick` | 均线粘连 |
| 资金面 | `major_force` | 主力抢筹 |
| 资金面 | `institution_chasing` | 机构接盘 |
| 资金面 | `abnormal_trade_at_dayend` | 尾盘掘金 |
| 资金面 | `margin_trade` | 融资追涨 |
| 当日-新高新低 | `today_newhigh_in_month` | 今日创月内新高 |
| 当日-新高新低 | `today_newhigh_in_halfyear` | 今日创半年新高 |
| 当日-新高新低 | `today_newhigh_in_year` | 今日创一年新高 |
| 当日-新高新低 | `today_newhigh_in_hist` | 今日创历史新高 |
| 当日-新高新低 | `today_newlow_in_month` | 今日创月内新低 |
| 当日-新高新低 | `today_newlow_in_halfyear` | 今日创半年新低 |
| 当日-新高新低 | `today_newlow_in_year` | 今日创一年新低 |
| 当日-新高新低 | `today_newlow_in_hist` | 今日创历史新低 |
| 当日-均线突破 | `today_upbreak_ma5` | 今日向上突破5日均线 |
| 当日-均线突破 | `today_upbreak_ma10` | 今日向上突破10日均线 |
| 当日-均线突破 | `today_upbreak_ma20` | 今日向上突破20日均线 |
| 当日-均线突破 | `today_upbreak_ma60` | 今日向上突破60日均线 |
| 当日-均线突破 | `today_upbreak_ma120` | 今日向上突破120日均线 |
| 当日-均线突破 | `today_upbreak_ma250` | 今日向上突破250日均线 |
| 当日-均线突破 | `today_dnbreak_ma5` | 今日向下突破5日均线 |
| 当日-均线突破 | `today_dnbreak_ma10` | 今日向下突破10日均线 |
| 当日-均线突破 | `today_dnbreak_ma20` | 今日向下突破20日均线 |
| 当日-均线突破 | `today_dnbreak_ma60` | 今日向下突破60日均线 |
| 当日-均线突破 | `today_dnbreak_ma120` | 今日向下突破120日均线 |
| 当日-均线突破 | `today_dnbreak_ma250` | 今日向下突破250日均线 |
| 当日-布林带 | `today_boll_upbreak_upper` | 今日布林带向上突破上轨 |
| 当日-布林带 | `today_boll_upbreak_mid` | 今日布林带向上突破中轨 |
| 当日-布林带 | `today_boll_upbreak_lower` | 今日布林带向上突破下轨 |
| 当日-布林带 | `today_boll_dnbreak_upper` | 今日布林带向下突破上轨 |
| 当日-布林带 | `today_boll_dnbreak_mid` | 今日布林带向下突破中轨 |
| 当日-布林带 | `today_boll_dnbreak_lower` | 今日布林带向下突破下轨 |
| 当日-MACD | `today_macd_green_to_red` | 今日MACD绿转红 |
| 当日-MACD | `today_macd_red_expanding` | 今日MACD红柱扩大 |
| 当日-MACD | `today_macd_red_knee` | 今日MACD红柱拐点确认 |
| 当日-MACD | `today_macd_red_shrink` | 今日MACD红柱收缩 |
| 当日-MACD | `today_macd_red_to_green` | 今日MACD红转绿 |
| 当日-MACD | `today_macd_green_expanding` | 今日MACD绿柱扩大 |
| 当日-MACD | `today_macd_green_knee` | 今日MACD绿柱拐点确认 |
| 当日-MACD | `today_macd_green_shrink` | 今日MACD绿柱收缩 |
| 当日-MACD | `today_macd_golden_cross` | 今日MACD金叉 |
| 当日-MACD | `today_macd_dead_cross` | 今日MACD死叉 |
| 当日-涨跌统计 | `today_continue_up` | 今日连涨 |
| 当日-涨跌统计 | `today_continue_down` | 今日连跌 |
| 当日-涨跌停 | `today_first_limitup` | 今日首板涨停 |
| 当日-涨跌停 | `today_first_limitdown` | 今日首板跌停 |
| 当日-涨跌停 | `today_continue_limitup` | 今日连板涨停 |
| 当日-涨跌停 | `today_continue_limitdown` | 今日连板跌停 |
| 当日-成交量 | `today_volume_expanding_s` | 短期放量 |
| 当日-成交量 | `today_volume_expanding_m` | 中期放量 |
| 当日-成交量 | `today_volume_expanding_l` | 长期放量 |
| 当日-成交量 | `today_volume_shrinking_s` | 短期缩量 |
| 当日-成交量 | `today_volume_shrinking_m` | 中期缩量 |
| 当日-成交量 | `today_volume_shrinking_l` | 长期缩量 |

> **当日技术信号（`strategy_today_*`）**：基于当日行情的实时技术信号，仅 A 股。不传 `--date` 默认当天；自然语言可直接命中，例如"今天创一年新高的股票" → `westock screen strategy --type today_newhigh_in_year`，"站上 250 日线的" → `today_upbreak_ma250`，"MACD 金叉的" → `today_macd_golden_cross`，"连续涨停的" → `today_continue_limitup`。

---

