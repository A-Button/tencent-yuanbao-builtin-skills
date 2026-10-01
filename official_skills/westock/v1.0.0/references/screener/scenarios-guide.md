# WeStock Screener - 常见选股场景详解

> **定位**：本文档是 SKILL.md 的 **L3 层补充材料**，提供完整的选股场景示例和详细操作步骤。
>
> **使用方式**：AI 在遇到不确定的选股场景时按需加载本文档。命令列表和基本用法请参见
> [SKILL.md](../../SKILL.md)，完整字段列表请参见 [fields-guide.md](./fields-guide.md)。

---

## 〇₀、路由与边界（仅在场景不明确时阅读）

本文是低频可选示例；优先使用[筛选速查](../screen.md)，默认文字回答，用户明确要求文件才创建。所有示例服从入口的必要项、停止与范围规则，不作为自动增加分析的清单。

### 0.1 筛选优先使用 Westock，真实缺口受控降级

- 命中已支持筛选能力时先调用对应Westock命令；已明确不支持的字段/历史模式直接记录缺口，不故意发失败请求。不得用私有接口或训练记忆替代。
- 正确调用后仍有接口异常、覆盖不足或字段缺失时，按[入口缺口处理](../../SKILL.md#5-缺口处理停止该分支不无限换源)用`web_search`仅补必要公开信息，说明原因、来源、日期和口径差异，保留已有结果。
- 服务不可用不代表能用网页凑出完整股票池；仅核验已有候选的缺失信息，不抓取全市场行情后自行重建筛选或排序。
- 筛选无匹配、尚未披露等正常空结果不触发降级；不得扩大范围、放宽条件或更换市场凑结果。仍无法核验时明确保留缺口。

### 0.2 筛选与数据查询边界（高频误判）

> 按事件找股票池使用 `westock screen event`，且必须核对事件内置窗口能否满足用户的 N 天要求。
> 数值条件、标签、策略、排行分别路由到对应 `screen` 子命令；单股明细或日历清单使用数据查询命令。

| 用户问 | 股票池入口 | 不要用明细替代筛选 |
| --- | --- | --- |
| "限售解禁的股票" | `westock screen event --type shareunlock_next_90 ` | `westock calendar --event lockup_release` |
| "业绩预约披露的股票" | `westock screen event --type earnings_schedule ` | `westock calendar` / `westock disclosure` |
| "近期回购的股票" | `westock screen event --type buyback ` | `westock buyback <代码>` |
| "近期大宗交易/龙虎榜的股票" | `westock screen event --type block_past_30 ` / `westock screen event --type longhu_statis_past_15 ` | `westock fund block` / `westock lhb` |
| "董监高变动/增减持的股票" | `westock screen event --type manager_change ` / `westock screen event --type manager_sharechg ` | `westock events` |

### 0.3 清单查询（强制执行命令）

> "有哪些 X 可以用" 必须执行 `--list`，不要凭文档列举（示例不全且可能过时）。

| 用户问法 | 命令 |
| --- | --- |
| "有哪些事件 / 标签 / 策略 / 排行指标" | `westock screen event/label/strategy/ranking --list` |
| "ETF 主题池 / 排行指标" | `westock screen label --asset etf --list` / `westock screen ranking --list --asset etf` |
| "filter 有哪些预设" | `westock screen condition --list-presets` |

> ⚠️ **`westock screen condition --list-presets` ≠ `westock screen strategy --list`**：
> - "预设/preset/filter 函数" → `westock screen condition --list-presets`（条件型，含阈值参数）
> - "策略/信号/形态" → `westock screen strategy --list`（信号型）
>
> ⚠️ **`westock screen condition --preset` vs `westock screen strategy` 输出差异**：condition --preset 输出**含指标列**（PE/ROE 等数值）；strategy 仅输出 **code/name**。

### 0.4 口语表述 → 命令（歧义时先澄清）

| 用户口语 | 优先路由 | 说明 |
|---------|---------|------|
| "龙头" / "强势股" | `westock screen ranking`（如 `--type limitup_days`、`--type CompScore`）或 `westock screen strategy` 技术策略 | 若指某板块，先核验该排行入口支持的范围ID；可直接限定范围时不额外查成份，未知映射不猜转换 |
| "白马" / "蓝筹" | `westock screen label` + `westock screen condition`/`westock screen ranking` | 如高 ROE → `westock screen label --type fin_high_roettm `；大市值 → `westock screen label --type marketcap_super_big ` |
| "黑马" / "妖股" | `westock screen ranking --type limitup_days` 或 `westock screen strategy` 放量突破类 | 偏主观，需结合用户是否指涨停/短线 |
| "抄底" / "低估" | `westock screen condition --preset LowPE` 或 `westock screen ranking --type fin_valuation --asc` | 技术抄底 → `westock screen strategy` 中 MACD/均线类策略 |
| "高股息" | `westock screen condition --preset HighDividend` 或 `westock screen condition --preset HighDividendLowValuation` | ETF → `westock screen label --type high_dividend --asset etf`（`high_dividend` 仅 ETF 主题池；股票高股息用 `--preset HighDividend`） |

---

## 〇、同义需求 → 推荐命令速查

| 用户表述 | 推荐命令 | 说明 |
|---------|---------|-----|
| "低估值股有哪些" / "破净股" | `westock screen label --type valuation_lowpb ` / `westock screen label --type valuation_negpe ` | 静态分类，无需阈值 |
| "PE<20 且 ROE>15 的股" | `westock screen condition --expression "intersect([PE_TTM<20, ROETTM>15])"` | 严格保留用户阈值；是否排除负PE另行明确 |
| "低 PE TOP 30" | `westock screen condition --preset LowPE --limit 30` | 参数化预设 |
| "估值最低的 10 只" | `westock screen ranking --type fin_valuation --limit 10` | 排行榜（升序） |
| "MACD金叉" | `westock screen strategy --type macd_golden ` | 策略信号 |
| "今日创一年新高" / "站上250日线" / "今日MACD金叉" / "今日首板涨停" | `westock screen strategy --type today_newhigh_in_year ` / `today_upbreak_ma250 ` / `today_macd_golden_cross ` / `today_first_limitup ` | 当日技术信号（`strategy_today_*`，仅 A 股，默认当天） |
| "MACD金叉里估值最低的" | `westock screen ranking --type fin_valuation --within-strategy macd_golden` | 范围限定 + 排序 |
| "新股有哪些" / "次新股" | `westock screen label --type listeddate_5days ` / `westock screen label --type listeddate_3mons ` | 上市时间标签 |
| "近期限售解禁" | `westock screen event --type shareunlock_next_90 ` | 事件 + 时间窗口 |
| "央企里评分最高" | `westock screen ranking --type CompScore --within-label shareholder_central_state` | 范围限定 + 排序 |
| "ETF 规模榜" / "高股息 ETF" | `westock screen ranking --type size --asset etf` / `westock screen label --type high_dividend --asset etf` | ETF 维度 |
| "板块内估值最低" | `westock screen ranking --type fin_valuation --universe <板块代码>` | 板块二次排序 |
| "评分>70 的股票" | `westock screen ranking --type CompScore --min-CompScore 70` | 阈值筛选（不是 `--limit`） |
| "看下一页" / "第二页" | 复用上次输出末尾提示的 `next offset` 作为 `--offset` | 分页 |
| "近一周名单变化" | `--start <日期> --end <日期>` | 区间查询（避免单日 × N 次） |

---

## 一、价值投资场景

### 场景 1.1：寻找低估值蓝筹

```
用户："帮我找PE低于15、ROE高于15%的白马股"
→ westock screen condition --expression "intersect([PE_TTM > 0, PE_TTM < 15, ROETTM > 15])" --date 2026-04-10 --orderby ROETTM --desc
→ 解读：PE为正说明盈利，低PE代表估值便宜，高ROE代表盈利能力强
→ 建议补充：查看行业分布，关注PE是否因周期低谷导致偏低
```

### 场景 1.2：高股息红利组合

```
用户："找股息率超过5%的高分红股票"
→ westock screen condition --expression "DividendRatioTTM > 5" --limit 30
→ 解读：仅按用户明确股息率条件筛选，注明返回范围与日期
→ 可选：用户另要求盈利或估值门槛时再增加PE/PB条件，不默认附加
```

### 场景 1.3：PEG成长股估值

```
用户："找PEG小于1的成长股"
→ westock screen condition --expression "intersect([PE_TTM > 0, PE_TTM < 40, NPParentCompanyYOY > 20, PE_TTM / NPParentCompanyYOY < 1])"
→ 解读：PEG<1意味着估值相对盈利增速便宜
→ 注意：需确保利润增长可持续，建议结合季报数据验证
```

---

## 二、技术面选股场景

### 场景 2.1：均线多头排列（趋势向上）

```
用户："找均线多头排列的强势股"
→ westock screen condition --expression "intersect([MA_5 > MA_10, MA_10 > MA_20, MA_20 > MA_60])" --limit 30
→ 解读：短期均线在上表明多头占优，适合趋势跟踪
→ 建议：叠加成交量放大 (TurnoverValue > 某阈值) 确认有效性
```

### 场景 2.2：MACD + KDJ 共振

```
用户："找MACD看多且KDJ处于低位的股票"
→ westock screen condition --expression "intersect([DIF > DEA, MACD > 0, KDJ_J < 30])"
→ 解读：这是当前截面状态，不证明当日发生金叉或已经反弹；金叉事件用 strategy 信号。
→ 注意：美股 MACD 条件字段受限，其它技术字段逐项查 fields-guide.md，不概括为全部不可用。
```

### 场景 2.3：布林带突破 + RSI 确认

```
用户："找突破布林上轨且RSI没有严重超买的股票"
→ westock screen condition --expression "intersect([ClosePrice > BOLL_UPPER, RSI_6 < 80])"
→ 解读：突破上轨为强势信号，RSI<80排除极端超买
```

### 场景 2.4：当日技术信号（免手搓表达式）

```
用户："今天创一年新高的股票"
→ westock screen strategy --type today_newhigh_in_year
→ 直接返回当日创一年新高的 A 股，无需手搓 condition 表达式

用户："分别看看今天站上250日线和 MACD 金叉的股票"
→ westock screen strategy --type today_upbreak_ma250,today_macd_golden_cross
→ 核对返回分组；若要求同时满足，应明确求交集并说明分页/截断范围，不能把并列结果直接当交集。
```

> 当日技术信号（`strategy_today_*`）共 48 个，覆盖新高新低 / 均线突破 / 布林带 / MACD / 连涨连跌 / 涨跌停 / 放量缩量。相比 2.1–2.3 手搓 `condition` 表达式，当日信号是封装好的即取即用的信号。**完整清单见 `ai_usage_guide.md` 第六章。**

---

## 三、资金面选股场景

### 场景 3.1：主力资金大幅流入

```
用户："找今天主力资金净流入超过1亿的股票"
→ westock screen condition --expression "MainNetFlow > 100000000" --date 2026-04-10 --orderby MainNetFlow --desc
→ 解读：主力大额流入可能预示机构建仓
→ 注意：本例采用沪深字段；港股 MainNetFlow 支持情况先核对当前端点。TotalNetFlow 是总净流入，不能代替主力净流入；美股不支持此资金条件。
```

### 场景 3.2：持续资金关注

```
用户："找近期持续有资金流入的股票"
→ westock screen condition --expression "intersect([MainNetFlow5D > 0, MainNetFlow10D > 0, MainNetFlow20D > 0])"
→ 解读：5日/10日/20日均为正流入，说明机构持续加仓
→ 注意：仅沪深市场支持此组合
```

---

## 四、港股/美股场景

### 场景 4.1：港股低估值高股息

```
用户："找港股中股息率高、估值低的股票"
→ westock screen condition --expression "intersect([PeTTM > 0, PeTTM < 10, DivTTM > 5])" --market hk --limit 30
→ 注意字段差异：港股用 PeTTM/PbLF/DivTTM，非 PE_TTM/PB/DividendRatioTTM
```

### 场景 4.2：美股大盘股筛选

```
用户："找美股中市值大于1000亿美元、PE低于30的股票"
→ westock screen condition --expression "intersect([TotalMV > 100000000000, PeTTM > 0, PeTTM < 30])" --market us
→ 金额阈值以 TotalMV 单位为美元原值为前提；不包含科技行业限制。美股技术字段逐项查表，资金流向不可套用沪深字段。
```

---

## 五、策略选股场景

### 场景 5.1：使用预置策略

```
用户："用MACD金叉策略帮我选股"
→ westock screen strategy --type macd_golden --date 2026-04-10
→ 返回当日满足 MACD 金叉条件的股票列表
```

### 场景 5.2：多策略对比

```
用户："对比高股息和高盈利价值两种策略的选股结果"
→ westock screen strategy --type high_dividend --date 2026-04-10
→ westock screen strategy --type pb_roe --date 2026-04-10
→ 对比两组结果中的重叠标的和差异
```

### 场景 5.3：策略回溯

```
用户："看看MACD金叉策略过去一周每天选了哪些股票"
→ westock screen strategy --type macd_golden --start 2026-04-03 --end 2026-04-10
→ 返回区间内每天的策略选股结果
```

### 场景 5.4：当日技术信号

```
用户："今天创一年新高的股票有哪些"
→ westock screen strategy --type today_newhigh_in_year
→ 返回当日（不传 --date 默认今天）创一年新高的 A 股列表

用户："把今天 MACD 金叉、站上250日线、首板涨停的都给我"
→ westock screen strategy --type today_macd_golden_cross,today_upbreak_ma250,today_first_limitup
→ 一次返回三类当日信号的结果（逗号分隔多个 type）

用户："今天 MACD 金叉里估值最低的"
→ westock screen ranking --type fin_valuation --within-strategy today_macd_golden_cross --limit 10
→ 在当日 MACD 金叉信号股里按估值升序排行
```

> 当日技术信号（`strategy_today_*`）基于当日行情，仅 A 股；历史回测用 `--start`/`--end`。完整 48 个清单（新高新低 / 均线突破 / 布林带 / MACD / 连涨连跌 / 涨跌停 / 放量缩量）见 `ai_usage_guide.md` 第六章。

---

## 六、标签选股场景

### 场景 6.1：按股东属性筛选

```
用户："找央企控股的股票"
→ westock screen label --type shareholder_central_state --date 2026-04-10
→ 返回央企控股标签下的股票列表
```

### 场景 6.2：财务特征标签

```
用户："找高ROE的公司"
→ westock screen label --type fin_high_roettm --date 2026-04-10
→ 返回 ROE(TTM) 处于高位的股票列表
```

### 场景 6.3：多标签组合

```
用户："分别查看企业属性标签和 ST 风险标签"
→ westock screen label --type shareholder_central_state,risk_st --date 2026-04-10
→ 多标签并查不保证交集；要求同时满足时核对返回分组，再明确求交并注明完整性。
```

---

## 七、排行选股场景（ranking）

### 场景 7.1：综合评分排行

```
用户："帮我找综合评分最高的10只股票"
→ westock screen ranking --type CompScore --limit 10
→ 返回按综合评分降序排列的 TOP10 股票
→ 解读：综合评分综合了资金/基本面/风险/技术四个维度，高分代表综合表现好
→ 建议：结合行业分布，避免集中在单一行业
```

### 场景 7.2：评分变动追踪

```
用户："哪些股票评分周变动最大？"
→ westock screen ranking --type CompScore --period weekly --limit 20
→ 返回评分周变动排行
→ 解读：评分大幅上升可能预示市场关注度提升
→ 进阶：用 westock score <code> 查看个股评分详细变动
```

### 场景 7.3：资金评分选股

```
用户："资金面评分最高的股票有哪些？"
→ westock screen ranking --type CapScore --limit 20
→ 返回按资金评分排序的股票列表
→ 解读：资金评分高代表主力资金关注度高
→ 建议：结合 westock fund flow <code> 查看详细资金流向
```

### 场景 7.4：高评分筛选

```
用户："找综合评分70以上的优质股票"
→ westock screen ranking --type CompScore --min-CompScore 70 --limit 20
→ 返回综合评分≥70的股票按综合评分降序排列
→ 解读：高评分代表综合表现好
→ 进阶：叠加 CapScore 等字段的阈值筛选，如 --min-CapScore 60
```

### 场景 7.5：估值排行

```
用户："A股估值最低的股票有哪些？"
→ westock screen ranking --type fin_valuation --limit 20        # 默认升序（PE最低）
→ westock screen ranking --type fin_valuation --asc             # 显式升序
→ 解读：估值排行按PE/PB/PS等指标排序
→ 建议：结合行业和基本面分析，避免单一维度判断
```

### 场景 7.6：成长指标选股

```
用户："成长能力最强的10只股票"
→ westock screen ranking --type fin_growth --limit 10
→ 返回按营收增速降序排列的 TOP10
→ 解读：成长排行包含营收增速、利润增速等指标
→ 进阶：用 westock finance <code> 查看财务详情验证
```

### 场景 7.7：涨跌停排行

```
用户："连续涨停天数最多的股票？"
→ westock screen ranking --type limitup_days --limit 20
→ 返回按连续涨停天数降序排列的股票
→ 解读：连板越多市场关注度越高
→ 风险：连板后可能面临炸板风险，需谨慎追高
```

### ⭐ 场景 7.8：范围限定（组合查询）

```
用户："央企里评分最高的10只"
→ westock screen ranking --type CompScore --within-label shareholder_central_state --limit 10
→ 在央企股票里按综合评分排行

用户："MACD金叉的股票中估值最低的"
→ westock screen ranking --type fin_valuation --within-strategy macd_golden --limit 10
→ 在 MACD 金叉信号股里按估值升序排行

用户："限售解禁股的评分排行"
→ westock screen ranking --type CompScore --within-event shareunlock_next_90 --limit 10
→ 在限售解禁股中按综合评分排行

用户："半导体板块里估值最低的股票"
→ westock screen ranking --type fin_valuation --universe 11010001 --limit 10
→ 在指定板块内按估值升序排行
```

### 场景 7.9：排行 + 阈值筛选组合

```
用户："资金评分高且综合评分≥70的股票"
→ westock screen ranking --type CapScore --min-CompScore 70 --limit 20
→ 先筛综合评分≥70，再按资金评分降序
→ 解读：多维度综合筛选，选出"综合好 + 资金强"的标的
```

### 场景 7.10：两融加仓榜（margin 指标源）

```
用户："今天两融加仓最多的股票"
→ westock screen ranking --type margin_chg_d --limit 20
→ 默认按 MChgD（两融余额日变动）降序，看加仓榜
→ 解读：MChgD > 0 = 加仓，融资盘看好；通过 --asc 切换到日减仓榜（看融资盘抛弃）

用户："近一周两融累计加仓最猛的股票"
→ westock screen ranking --type margin_chg_w --limit 10
→ 按 MChgW（周变动）降序
→ 类似指标：margin_chg_m（月）/ margin_chg_q（季）/ margin_chg_y（年）
```

### 场景 7.11：两融连续扩大筛选

```
用户："两融余额连续扩大 5 天以上的股票（融资盘持续抢筹）"
→ westock screen ranking --type margin_in_days --min-MtInDays 5 --limit 20
→ 按 MtInDays（连续扩大天数）降序，并设阈值 ≥5
→ 解读：连续多日两融扩大 = 融资盘持续看好，资金面强势信号
→ 反向指标：margin_out_days（连续缩小天数，融资盘持续撤离）
```

### 场景 7.12：主力资金净流入榜（capital 指标源）

```
用户："今天主力净流入最多的股票"
→ westock screen ranking --type cap_main_net --limit 20
→ 默认按 MainNetIn 降序看主力净流入榜
→ 解读：通过 --asc 切换看主力净流出榜（被主力抛弃）；散户净流入榜首位通常对应主力净流出榜首位（资金流转零和性）

用户："近 5 个交易日主力累计净流入最多的股票"
→ westock screen ranking --type cap_main_5d --limit 20
→ 按 MainSum5d（派生字段，= MainT0+T1+T2+T3+T4 的合计）降序
→ 不要直接看单日数据，5 日累计更能反映持续抢筹
```

### 场景 7.13：主力连续抢筹筛选

```
用户："主力连续净流入 3 天以上的股票（持续抢筹）"
→ westock screen ranking --type cap_in_days --min-MainInDays 3 --limit 20
→ 按 MainInDays（连续净流入天数）降序，阈值 ≥3
→ 解读：连续多日主力净流入 = 主力持续抢筹；
→ 反向指标：cap_out_days（连续净流出天数，主力持续撤离）
```

### 场景 7.14：标签 × 资金交叉分析（ranking --within-label + capital）

```
用户："央企里近 5 天主力累计净流入最多的股票"
→ westock screen ranking --type cap_main_5d --within-label shareholder_central_state --limit 10
→ 解读：先在央企标签内圈定股票池，再按主力 5 日累计净流入降序
→ 这是 ranking 命令的核心特色 — 范围限定 × 指标排序的二维交叉分析
→ 类似组合：板块×指标（--universe 11010001）/ 策略×指标（--within-strategy macd_golden）/ 事件×指标（--within-event shareunlock_next_90）
```

### 场景 7.15：北向活跃股榜单（ranking north_*）

```
用户："今天北向成交最活跃的股票有哪些？"
→ westock screen ranking --type north_active_d
→ 按 EndDate 分组展示近1周每日 Top20；同日内按 Rank 升序
→ 注意：固定榜单，不要加 --limit/--offset

用户："近半年哪些股票北向上榜次数最多（按月）？"
→ westock screen ranking --type north_appear_m
→ 按 AppearanceCnt 降序展示 Top20

用户："贵州茅台北向资金持仓市值多少？"
→ 技能内路由：westock fund north-holding sh600519（季度持仓明细）
```

---

## 八、组合分析场景

### 场景 8.1：多维度综合选股

```
用户："帮我找基本面好、技术面向上、资金也在流入的股票"
→ 使用预设 `westock screen condition --preset TechFundamentalCombo`：MACD看多（DIF>DEA、MACD>0）+ 均线多头 + ROE>10% + 净利增长>0 + PE<30
→ 或自定义组合:
  westock screen condition --expression "intersect([DIF > DEA, MACD > 0, MA_5 > MA_10, ROEWeighted > 10, PE_TTM > 0, PE_TTM < 30, MainNetFlow > 0])"
```

### 场景 8.2：条件选股 + 数据查询联动

```
用户："帮我选出低估值高ROE的股票，并查看前3只的详细财务数据"
→ 步骤1: westock screen condition --expression "intersect([PE_TTM > 0, PE_TTM < 15, ROETTM > 20])" --limit 3
→ 步骤2: 取返回的3个股票代码
→ 步骤3: 使用 westock finance <code1>,<code2>,<code3> 一次批量查看财务详情
→ 步骤4: 综合分析并给出推荐
```

---

## 九、ETF 选基场景

### 场景 9.1：高股息 ETF 主题筛选

```
用户："帮我找高股息的 ETF"
→ westock screen label --type high_dividend --asset etf
→ 解读：返回的是符合"高股息"主题池的 ETF 名单
→ 多池并查：westock screen label --type high_dividend,size_100 --asset etf
→ 两池分别返回，非交集；同时满足需对已返回代码显式求交，并说明截断样本不代表全量。
```

### 场景 9.2：千亿规模 ETF

```
用户："千亿规模以上的 ETF 都有哪些"
→ westock screen label --type size_1000 --asset etf
→ 解读：直接命中 KYP 主题池中的"千亿规模"分类
```

### 场景 9.3：ETF 估值最低（PB 升序）

```
用户："持仓估值 PB 最低的 ETF 有哪些"
→ westock screen ranking --type valuation --asset etf --orderby PB --asc --limit 10
→ 解读：PB 是持仓估值指标，不是 ETF 价格相对净值的折价；溢折价查询使用 disc_interval 及对应字段。
→ 注意：valuation 默认按 PE_TTM 升序；valuation_pct 看估值历史百分位。
```

### 场景 9.4：近 20 日涨幅最高的 ETF

```
用户："近20个交易日涨幅最大的 ETF"
→ westock screen ranking --type qt_chg_interval --asset etf --orderby ChgPct20D --limit 10
→ 解读：使用 20 个交易日口径，不等于自然月；其它周期字段查 etf-pools.md 并以当前返回为准，不猜字段名。
```

### 场景 9.5：ETF 选基 → 详情精查（联动）

```
用户："给我推荐一只规模大、估值低的科创 ETF"

AI 步骤：
1. 主题筛选：先确认 science_tech 在当前 ETF 主题清单中，再使用对应 label 限量查询。
2. 仅按所需维度同轮查询规模size与估值valuation排行，显式--asset etf；50条只是开放探索的初始样本建议，不是能力上限或全量证明。
3. 对返回样本求交集；这只是全市场 Top N 与主题样本的交集，不是该主题完整排名。
4. 只对实际需要解释的候选批量精查必要字段；用户要求明确范围时按其要求，不能把默认10只当固定上限。
5. 交付候选和依据、数据时点、每路截断范围及未验证条件；交集为空不能断言全市场无匹配。
```

> ⚠️ **决策入口**：
> - 用户带"标签/主题"（如"高股息 / 千亿基金 / 科创板占比高"）→ `westock screen label --asset etf`
> - 用户带"排序/榜单"（如"规模最大 / 涨幅前 10 / 估值最低"）→ `westock screen ranking --asset etf`
> - 用户给具体 ETF 代码看详情 → `westock etf profile` / `westock etf overview` 等子命令（按维度精查）

---

## 十、注意事项

1. **市场字段差异**：沪深用 `PE_TTM`/`PB`/`DividendRatioTTM`，港美用 `PeTTM`/`PbLF`/`DivTTM`
2. **功能限制**：
   - 技术指标逐字段查 [fields-guide.md](./fields-guide.md)，美股部分字段受限，不能把全部技术指标视为同一支持范围。
   - 资金流向支持因市场和指标而异；主力净流入与总净流入不可互相替代。
   - 股票策略、标签、事件和排行按沪深模式使用；ETF 标签与排行是独立资产模式，条件选股另支持港美市场。
3. **日期参数**：仅传目标命令支持的参数，event 的窗口内嵌类型；默认日期以返回为准。
4. **数据时效**：按指标族和实际返回时间区分盘中、收盘及延迟披露数据，不一概断言实时或收盘更新。
