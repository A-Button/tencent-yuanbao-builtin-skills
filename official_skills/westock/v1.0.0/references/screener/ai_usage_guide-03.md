# WeStock Screener - AI 深度参考指南 · 分册 03

[本手册索引](ai_usage_guide.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

## 七、标签选股完整列表

| 分类 | 标签代码 | 名称 |
|------|---------|------|
| 股东属性 | `shareholder_central_state` | 央企公司 |
| 股东属性 | `shareholder_local_state` | 国企公司 |
| 股东属性 | `shareholder_private` | 民企公司 |
| 股东属性 | `shareholder_qfii` | 含外资 |
| 股东属性 | `shareholder_nicf_phase1` | 大基金一期 |
| 股东属性 | `shareholder_nicf_phase2` | 大基金二期 |
| 股东属性 | `shareholder_nicf_phase3` | 大基金三期 |
| 股东属性 | `shareholder_hkfund` | 陆股通持股 |
| 股东属性 | `shareholder_huijin` | 汇金持股 |
| 股东属性 | `shareholder_mof` | 财政部持股 |
| 股东属性 | `shareholder_csf` | 证金持股 |
| 风险标签 | `risk_st` | ST与*ST股 |
| 风险标签 | `risk_delisting` | 退市整理期股票 |
| 风险标签 | `risk_remove_st` | 摘星脱帽股 |
| 风险标签 | `risk_broken_ipo` | 破发股 |
| 估值水平 | `valuation_abs_high` | 估值绝对高位股 |
| 估值水平 | `valuation_abs_low` | 估值绝对低位股 |
| 估值水平 | `valuation_rel_high` | 估值相对高位股 |
| 估值水平 | `valuation_rel_low` | 估值相对低位股 |
| 估值水平 | `valuation_lowpb` | 破净股 |
| 估值水平 | `valuation_negpe` | 亏损股 |
| 资产结构 | `fin_asset_high_cash` | 资产结构多现金 |
| 资产结构 | `fin_asset_high_inventory` | 资产结构多库存 |
| 资产结构 | `fin_asset_high_receivable` | 资产结构多应收 |
| 资产结构 | `fin_asset_high_longequity` | 资产结构多长股投 |
| 资产结构 | `fin_asset_high_investprop` | 资产结构多投资性房地产 |
| 资产结构 | `fin_asset_high_fixedasset` | 资产结构多固定资产 |
| 资产结构 | `fin_asset_high_bubble1` | 资产结构多泡沫资产1 |
| 资产结构 | `fin_asset_high_bubble2` | 资产结构多泡沫资产2 |
| 负债结构 | `fin_liability_high_shortdebt` | 负债结构多短债 |
| 负债结构 | `fin_liability_high_estimateliab` | 负债结构多预计负债 |
| 负债结构 | `fin_liability_high_advance` | 负债结构多预收 |
| 利润结构 | `fin_profit_high_cost_sales` | 成本结构多销售费用 |
| 利润结构 | `fin_profit_high_cost_admin` | 成本结构多管理费用 |
| 利润结构 | `fin_profit_high_cost_dev` | 成本结构多研发费用 |
| 利润结构 | `fin_profit_high_cost_financing` | 成本结构多财务费用 |
| 利润结构 | `fin_profit_high_assetimpair` | 利润结构多资产减值 |
| 利润结构 | `fin_profit_high_creditimpair` | 利润结构多信用减值 |
| 利润结构 | `fin_profit_high_assetsell` | 利润结构多资产处置 |
| 利润结构 | `fin_profit_high_discontinue` | 利润结构多终止经营净利润 |
| 利润结构 | `fin_profit_high_oci` | 利润结构多其他综合收益 |
| 利润结构 | `fin_profit_high_nonopincome` | 利润结构多营业外收入 |
| 现金流结构 | `fin_cash_high_cash` | 现金流结构多现金 |
| 现金流结构 | `fin_cash_high_cfo` | 现金流结构多经营现金 |
| 现金流结构 | `fin_cash_high_cfi` | 现金流结构多投资现金 |
| 现金流结构 | `fin_cash_high_cff` | 现金流结构多筹资现金 |
| 现金流结构 | `fin_cash_neg_cfo` | 现金流结构负经营现金 |
| 现金流结构 | `fin_cash_neg_cfi` | 现金流结构负投资现金 |
| 现金流结构 | `fin_cash_neg_cff` | 现金流结构负筹资现金 |
| 财务排名 | `fin_profitablity_high_rk_epsttm` | 盈利能力EPSttm高排序 |
| 财务排名 | `fin_profitablity_high_rk_roettm` | 盈利能力ROEttm高排序 |
| 财务排名 | `fin_profitablity_high_rk_roattm` | 盈利能力ROAttm高排序 |
| 财务排名 | `fin_profitablity_high_rk_gpttm` | 盈利能力毛利率ttm高排序 |
| 财务排名 | `fin_profitablity_high_rk_npttm` | 盈利能力净利率ttm高排序 |
| 财务排名 | `fin_operating_high_rk_receivable_turn` | 营运能力应收周转高排序 |
| 财务排名 | `fin_operating_high_rk_inventory_turn` | 营运能力存货周转高排序 |
| 财务排名 | `fin_operating_high_rk_asset_turn` | 营运能力资产周转高排序 |
| 财务排名 | `fin_growth_high_rk_rev_growth` | 成长能力营收增速高排序 |
| 财务排名 | `fin_growth_high_rk_profit_growth` | 成长能力利润增速高排序 |
| 财务排名 | `fin_growth_high_rk_asset_growth` | 成长能力资产增速高排序 |
| 财务排名 | `fin_liquidity_high_rk_current_ratio` | 偿债能力流动比率高排序 |
| 财务排名 | `fin_liquidity_high_rk_liability_ratio` | 偿债能力负债率高排序 |
| 财务排名 | `fin_liquidity_high_rk_interest_cover` | 偿债能力利息保障倍数高排序 |
| 财务排名 | `fin_profitablity_low_rk_epsttm` | 盈利能力EPSttm低排序 |
| 财务排名 | `fin_profitablity_low_rk_roettm` | 盈利能力ROEttm低排序 |
| 财务排名 | `fin_profitablity_low_rk_roattm` | 盈利能力ROAttm低排序 |
| 财务排名 | `fin_profitablity_low_rk_gpttm` | 盈利能力毛利率ttm低排序 |
| 财务排名 | `fin_profitablity_low_rk_npttm` | 盈利能力净利率ttm低排序 |
| 财务排名 | `fin_operating_low_rk_receivable_turn` | 营运能力应收周转低排序 |
| 财务排名 | `fin_operating_low_rk_inventory_turn` | 营运能力存货周转低排序 |
| 财务排名 | `fin_operating_low_rk_asset_turn` | 营运能力资产周转低排序 |
| 财务排名 | `fin_growth_low_rk_rev_growth` | 成长能力营收增速低排序 |
| 财务排名 | `fin_growth_low_rk_profit_growth` | 成长能力利润增速低排序 |
| 财务排名 | `fin_growth_low_rk_asset_growth` | 成长能力资产增速低排序 |
| 财务排名 | `fin_liquidity_low_rk_current_ratio` | 偿债能力流动比率低排序 |
| 财务排名 | `fin_liquidity_low_rk_liability_ratio` | 偿债能力负债率低排序 |
| 财务排名 | `fin_liquidity_low_rk_interest_cover` | 偿债能力利息保障倍数低排序 |
| 财务特征 | `fin_high_roettm` | 高ROEttm |
| 财务特征 | `fin_high_gpttm` | 高销售毛利率ttm |
| 财务特征 | `fin_high_npttm` | 高销售净利率ttm |
| 财务特征 | `fin_neg_rev_growth` | 营收负增长 |
| 财务特征 | `fin_neg_profit_growth` | 利润负增长 |
| 财务特征 | `fin_neg_asset_growth` | 资产负增长 |
| 财务特征 | `fin_unhealthy_growth` | 增收不增利 |
| 财务特征 | `fin_healthy_growth` | 降本增效股 |
| 财务特征 | `fin_forecast_inc` | 业绩预盈预增股 |
| 财务特征 | `fin_forecast_dec` | 业绩预亏预降股 |
| 财务特征 | `fin_forecast_slower_dec` | 业绩减亏减降股 |
| 财务特征 | `fin_forecast_slower_inc` | 业绩减增股 |
| 上市时间 | `listeddate_5days` | 新股5日内 |
| 上市时间 | `listeddate_3mons` | 近端次新股 |
| 上市时间 | `listeddate_1year` | 远端次新股 |
| 上市时间 | `listeddate_3year` | 上市1年以上3年以内 |
| 上市时间 | `listeddate_3yearplus` | 上市3年以上 |
| 价格与市值 | `price_below1` | 1元股 |
| 价格与市值 | `price_between_1_10` | 1到10元股 |
| 价格与市值 | `price_between_10_100` | 10到100元股 |
| 价格与市值 | `price_between_100_500` | 100到500元股 |
| 价格与市值 | `price_between_500_1000` | 500到1000元股 |
| 价格与市值 | `price_up1000` | 千元股 |
| 价格与市值 | `marketcap_below10` | 10亿以下股 |
| 价格与市值 | `marketcap_between_10_50` | 10到50亿股 |
| 价格与市值 | `marketcap_between_50_100` | 50到100亿股 |
| 价格与市值 | `marketcap_between_100_1000` | 100到1000亿股 |
| 价格与市值 | `marketcap_between_1000_10000` | 1000到10000亿股 |
| 价格与市值 | `marketcap_up10000` | 10000亿以上股 |
| 价格与市值 | `marketcap_super_big` | 超大盘 |
| 价格与市值 | `marketcap_super_small` | 超小盘 |

---

## 八、事件选股完整列表

| 分类 | 事件代码 | 名称 |
|------|---------|------|
| 分红 | `dividend_plan` | 分红预案公告后一月 |
| 分红 | `dividend_solution` | 分红决案公告后一月 |
| 分红 | `dividend_detail` | 分红实施公告后一月 |
| 分红 | `dividend_exdiv` | 分红除权后三日 |
| 业绩 | `earnings_schedule` | 业绩预约一月内披露 |
| 业绩 | `earnings_forecast` | 业绩预告后一月 |
| 业绩 | `earnings_express` | 业绩快报后一月 |
| 业绩 | `earnings_release` | 业绩披露后一周 |
| 定增 | `seo_past_7` | 定增上市前一周 |
| 定增 | `seo_past_30` | 定增上市前一月 |
| 定增 | `seo_next_30` | 定增上市后一月 |
| 定增 | `seo_next_90` | 定增上市后三月 |
| 股东大会 | `meeting_held` | 股东大会一月内召开 |
| 停复牌 | `suspension_now` | 停牌中 |
| 停复牌 | `suspension_over_30` | 停牌超一月 |
| 停复牌 | `resumption_next_3` | 复牌前三日 |
| 停复牌 | `resumption_past_7` | 复牌后一周 |
| 公司变更 | `rename_incoming` | 即将更名 |
| 公司变更 | `rename_past_90` | 更名后三月 |
| 董监高变动 | `manager_change` | 董监高变动 |
| 董监高变动 | `westock screen event --type manager_sharechg ` | 董监高增减持 |
| 董监高变动 | `manager_shareplan_sell_incoming` | 计划减持未实施 |
| 董监高变动 | `manager_shareplan_buy_incoming` | 计划增持未实施 |
| 董监高变动 | `manager_shareplan_sell_implementing` | 计划减持实施中 |
| 董监高变动 | `manager_shareplan_buy_implementing` | 计划增持实施中 |
| 回购 | `westock buyback` | 回购一月内 |
| 限售解禁 | `shareunlock_next_90` | 预计解禁三月内 |
| 限售解禁 | `shareunlock_incoming` | 实际解禁公告后 |
| 限售解禁 | `shareunlock_next_15` | 实际解禁两周内 |
| 法律与处罚 | `suitcase` | 诉讼后一月 |
| 法律与处罚 | `deregulation_incoming` | 重大处罚将生效 |
| 法律与处罚 | `deregulation_past_30` | 重大处罚生效一月内 |
| 重大事项 | `merger_unclosed` | 重大吸收合并 |
| 重大事项 | `tender_offer_unclosed` | 重大要约收购 |
| 重大事项 | `regroup_unclosed` | 重大资产重组 |
| 指数变动 | `index_add_incoming` | 将加入重要指数 |
| 指数变动 | `index_add_implemented_prev_7` | 已加入重要指数一周 |
| 指数变动 | `index_del_incoming` | 将踢出重要指数 |
| 指数变动 | `index_del_implemented_prev_7` | 已踢出重要指数一周 |
| 交易异动 | `block_past_30` | 大宗交易一月内 |
| 交易异动 | `westock screen event --type longhu_statis_past_15 ` | 龙虎榜上榜统计两周内 |
| 交易异动 | `longhu_detail_past_15` | 龙虎榜上榜详情两周内 |

---

## 九、排行选股（ranking）完整指标列表

`westock screen ranking` 命令支持**六类指标源，共 36 个指标**（完整速查见 [ranking-indicators.md](./ranking-indicators.md)）：

### 9.1 涨跌停指标（market）

| 分类 | 指标代码 | 名称 | 排序字段 |
|------|---------|------|---------|
| 涨停 | `limitup_days` | 连续涨停天数 | LimitUpDays |
| 涨停 | `limitup_seal_volume` | 收盘涨停封单量 | LimitUpVolume |
| 跌停 | `limitdn_days` | 连续跌停天数 | LimitDnDays |
| 跌停 | `limitdn_seal_volume` | 收盘跌停封单量 | LimitDnVolume |

### 9.2 财务排行指标（financial）

| 指标代码 | 名称 | 默认排序字段 | 默认方向 |
|---------|------|-------------|---------|
| `fin_valuation` | 估值排行 | PE_TTM | 升序（PE低优先） |
| `fin_growth` | 成长能力 | RevenueGrowth | 降序 |
| `fin_profit` | 盈利能力 | RoeTTM | 降序 |
| `fin_pershare` | 每股指标 | EpsTTM | 降序 |
| `fin_cash_size` | 现金流规模 | CFOTTM | 降序 |
| `fin_operation` | 营运能力 | - | 降序 |
| `fin_liquidity` | 偿债能力 | - | 降序 |
| `fin_profit_structure` | 收入结构 | - | 降序 |

### 9.3 评分指标（score）

| 指标代码 | 名称 | 说明 |
|---------|------|------|
| `CompScore` | 综合评分 | 综合资金/基本面/风险/技术四个维度 |
| `CapScore` | 资金评分 | 反映主力资金关注度 |
| `FunmScore` | 基本面评分 | 反映公司财务基本面 |
| `RiskScore` | 风险评分 | 反映风险程度（高分代表低风险） |
| `TecScore` | 技术评分 | 反映技术面状况 |

> 评分指标支持 `--period cur/weekly/monthly` 查看当前值或周/月变动值。

### 9.4 两融排行指标（margin）

| 指标代码 | 名称 | 默认排序字段 | 默认方向 |
|---------|------|-------------|---------|
| `margin_balance` | 两融余额 | MarginTrade | 降序 |
| `margin_chg_d` | 两融日变动 | MChgD | 降序 |
| `margin_chg_w` | 两融周变动 | MChgW | 降序 |
| `margin_chg_m` | 两融月变动 | MChgM | 降序 |
| `margin_chg_q` | 两融季变动 | MChgQ | 降序 |
| `margin_chg_y` | 两融年变动 | MChgY | 降序 |
| `margin_in_days` | 两融连续扩大天数 | MtInDays | 降序 |
| `margin_out_days` | 两融连续缩小天数 | MtOutDays | 降序 |

### 9.5 资金流入指标（capital）

| 指标代码 | 名称 | 默认排序字段 | 默认方向 |
|---------|------|-------------|---------|
| `cap_main_net` | 主力净流入 | MainNetIn | 降序 |
| `cap_retail_net` | 散户净流入 | RetailNetOut | 降序 |
| `cap_main_5d` | 主力5日合计净流入 | MainSum5d | 降序 |
| `cap_in_days` | 主力连续净流入天数 | MainInDays | 降序 |
| `cap_out_days` | 主力连续净流出天数 | MainOutDays | 降序 |

### 9.6 范围限定参数（所有指标通用）

| 参数 | 作用 |
|------|------|
| `--universe <板块代码>` | 限定在板块内排行 |
| `--within-label <标签短名>` | 限定在标签结果内排行（如 `shareholder_central_state`） |
| `--within-strategy <策略短名>` | 限定在策略结果内排行（如 `macd_golden`） |
| `--within-event <事件短名>` | 限定在事件结果内排行（如 `shareunlock_next_90`） |

> ⚠️ `--within-label` / `--within-strategy` / `--within-event` **三者互斥**。

### 9.7 北向活跃指标（north）

> 后端固定 Top20 预排序榜单；`--limit`/`--offset`/`--asc`/`--desc` 不适用；不支持 `--within-*` / `--universe`。

| 指标代码 | 名称 | 排序规则 |
|---------|------|---------|
| `north_active_d` | 北向成交活跃股（近1周按日 Top20） | EndDate 降序，同日内 Rank 升序 |
| `north_active_m` | 北向成交活跃股（近半年按月 Top20） | EndDate 降序，同月内 Rank 升序 |
| `north_appear_w` | 北向活跃股上榜次数（周） | AppearanceCnt 降序 |
| `north_appear_m` | 北向活跃股上榜次数（月） | AppearanceCnt 降序 |
| `north_appear_q` | 北向活跃股上榜次数（季） | AppearanceCnt 降序 |
| `north_appear_y` | 北向活跃股上榜次数（年） | AppearanceCnt 降序 |

> 个股/行业**北向季度持仓**不在 ranking 范围，请用 `westock fund north-holding <代码>`。

---

## 十、数据更新频率

| 类型 | 频率 |
|------|------|
| 条件 / 策略 | 每日收盘后 |
| 标签 / 事件 | 跟随财报/公告基础数据 |
| 排行（涨跌停 / 资金流入） | 盘中实时 |
| 排行（财务 / 评分 / 两融） | 每日收盘后（两融 T+1） |

> **日期格式**：支持日期的命令使用 `YYYY-MM-DD`；默认时点按命令区分，event 的窗口由类型决定。
> **数据时效**：上表仅作更新频率参考，不同指标可能盘中更新、收盘更新或延迟披露。交付以实际返回时间为准，不能一律宣称实时或收盘后数据。
