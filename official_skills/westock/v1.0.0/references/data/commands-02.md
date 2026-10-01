# WeStock Data - 详细命令用法 · 分册 02

[本手册索引](commands.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

### 资金流向（个股/板块）

```bash
# A股：主力资金（单日 / --start..--end 区间）
westock fund flow sh600000
westock fund flow sh600000,sz000001 --start 2026-05-01 --end 2026-05-20

# A股板块：资金流向（支持 pt 开头板块代码）
westock fund flow pt01801081

# 港股：资金流向
westock fund flow hk00700

# 港股：卖空数据（仅 --date 单日，不支持区间）
westock fund short hk00700
westock fund short hk00700 --date 2026-05-20

# 美股：卖空数据（仅 --date 单日，不支持区间）
westock fund short usAAPL
westock fund short usAAPL --date 2026-05-20

# 大宗交易（仅沪深）
westock fund block sh600519
westock fund block sh600519,sz000651

# 龙虎榜（仅沪深，按个股）
westock fund lhb sh600519                  # 当日（默认今天）
westock fund lhb sh600519,sz000651         # 多股同日批量
westock fund lhb sh600519 --date 2026-03-20          # 指定日期
westock fund lhb sh600519 --start 2026-05-25 --end 2026-07-24   # 时间区间（合并单表）

# 融资融券（仅沪深）
westock fund margin sh600519
westock fund margin sh600519,sz000651

# 北向资金持仓（个股季度明细 / 申万行业分布）
westock fund north-holding sh600519              # 单股：最新季 + 次新季
westock fund north-holding sh600519,sz000651    # 多股批量
westock fund north-holding pt01801080            # 板块裸码（自动识别 sw 级别）
westock fund south-holding hk00700,hk03690       # 港股南下资金持仓

```

> ⚠️ **美股限制**：美股不支持 `westock fund flow`（资金流向），只支持 `westock fund short`（卖空数据）

> ⚠️ **命令区分**：`flow` = 资金流向（主力/散户）；`short` = 卖空；`block` = 大宗交易；`margin` = 融资融券；`lhb` = 个股龙虎榜（成交统计/营业部明细）；`north-holding` = A股北向**季度持仓**；`south-holding` = 港股南下**持仓快照**

> ⚠️ **北向数据职责边界**：
> - `westock connect` = 陆股通**标的池**（哪些股票可被北向交易）
> - `westock fund flow sh600000` = 个股日度**资金流向**
> - `westock fund north-holding sh600519` = A股**季度北向资金持仓**（最新季 + 次新季）
> - `westock fund south-holding hk00700` = 港股**南下资金持仓**（持有比例/日季变动）
> - `westock fund north-holding pt…` = 申万行业**北向资金持仓分布**（**不支持**聚源概念/地域板块）
> - `westock sector ranking` = 全市场**北向热门板块**榜（当日/5日/20日）
> - 北向**成交活跃股 / 上榜频次**全市场榜单 → `westock screen ranking --type north_active_d` / `--type north_appear_m`（固定 Top20，不支持 `--limit`）

> ⚠️ **市场限制**：`block`/`margin`/`lhb` 仅支持沪深（sh/sz）；`short` 支持港股和美股；`flow` 支持沪深和港股（美股请用 `westock fund short`）

> ⚠️ **龙虎榜职责边界**：`westock lhb`（市场段）＝ 全市场龙虎榜榜**单**（机构榜/游资榜/活跃席位等，按 `--type` 筛选）；`westock fund lhb <代码>` ＝ **指定个股**的龙虎榜明细（成交统计 `LhbInfos` + 营业部买卖 `LhbTradingDetails`）。二者不要混用。

> 沪深港通成份股（北向 / 陆股通标的池）属于"市场"分组，见第二章；不在资金流量数据范围内。

---

## 十一、简况

> 公司基本信息/股东/分红/回购。

### 公司基本信息

```bash
westock profile sh600000                  # 公司简况
westock shareholder sh600519              # 股东结构（A股：十大股东/十大流通/股东户数；港股：持股股东+机构持仓）
westock disclosure sh600519               # 财报披露日历（财报发布前的预约披露日）

```

### 分红数据

```bash
westock dividend sh600519 --years 5                           # 分红派息（A股/港股/美股）
westock dividend sh600519 --all                               # 含未实施的分红方案

```

> ⚠️ **货币单位**：港股返回港元/美元，美股返回美元，展示时必须标注正确货币单位

### 公司回购

```bash
westock buyback sh600519                 # 公司回购（A股/港股）
westock buyback sh600519,hk01810         # 批量回购（A/H 混批分表输出）
westock buyback hk01810 --start 2026-03-01 --end 2026-04-14

```

---

## 十二、财务

> 三大报表/财报披露日历。

### 财务数据

**默认行为**：省略 `--type` 时拉取 `income` + `balance` + `cashflow` 三大报表（单股/批量均支持）。显式 `--type` 时只拉一张表。

| `--type` | 含义 | A股 | 港股 | 美股 |
|----------|------|-----|------|------|
| （省略） | 三大报表 | 利润表+资产负债+现金流 | 同左 | 同左 |
| `income` | 利润表 | 利润表 | 综合损益表 | Income Statement |
| `balance` | 资产负债表 | 资产负债表 | 资产负债表 | Balance Sheet |
| `cashflow` | 现金流量表 | 现金流量表 | 现金流量表 | Cash Flow |

```bash
westock finance sh600000                         # 默认三大表，最新1期
westock finance sh600519,sz000651 --limit 4        # 批量三大表
westock finance sh600000 --type income --limit 8   # 仅利润表
westock finance hk00700 --type income --limit 4

# 按日期区间（与 --limit 互斥）
westock finance sh600000 --start 2024-01-01 --end 2024-12-31              # 三大表区间
westock finance sh600000 --type income --start 2024-01-01 --end 2024-12-31

```

> 财报批量查询按**同一市场分组**，避免跨市场字段和币种混用；逐个核对返回代码，不能用请求成功数代替标的覆盖数。

> **参数说明**：`--limit`（最新期数）与 `--start`/`--end`（日期区间）互斥，请只指定其中一组。日期格式：YYYY-MM-DD。历史截止任务不能直接用最新N期；必须核对`EndDate`及必要的`InfoPublDate`，区间不自动保证“当时已知”。单股、批量、日期模式的JSON解析见[解析分支](../parsing.md)。
> **字段范围**：`--fields core`（默认，聚焦约 30 个核心指标）/ `--fields all`（全字段 100+ 列）。

### 财报披露日历

```bash
westock disclosure sh600519               # 财报披露日历（A股/港股/美股；又称业绩预约披露日）

```

---

## 十三、ETF

> 沪深场内 ETF（仅 `sh`/`sz`）。**子命令必填**（`westock profile` / `overview` / `holdings` / `nav`）。

> ⚠️ **路由**：档案/费率/分类/经理 → `westock etf profile`；收益/回撤/规模/溢折率/净申购/估值 → `westock etf overview`；净值历史 → `westock etf nav`（**不是 `westock kline`**）。

```bash
westock etf profile sh510300
westock etf overview sh510300
westock etf holdings sh510300
westock etf holdings sh510300 --limit 10   # 仅前 10 大持仓（按权重，支持 --offset）
westock etf nav sh510300 --start 2026-01-01 --end 2026-03-31

```

> `westock search --type etf`：`etfDetail=支持` 可走 `westock etf *`，`仅行情` 走 `westock quote`/`westock kline`。

> 详细字段说明见 [references/ai_usage_guide.md](./ai_usage_guide.md)

---

## 十四、发现

> 搜索/热搜/股单。这一组命令是**全市场维度**工具（非按代码查个股，也非筛选选股），用于股票、板块和 ETF 热度发现。新闻和热门报道直接使用 `web_search`。

### 股票、板块与 ETF 热搜

```bash
westock hot stock
westock hot sector
westock hot etf

```

> 板块行情榜请用 `westock sector ranking`，按代码精查请用本章节的其它 `westock sector` 子命令。
> **日韩股票搜索**：`westock search 关键词 --market jp|kr` 按市场搜日股/韩股，返回统一前缀代码（韩股 `ks*`/`kq*`，日股 `t*`，如 `ks005930`/`t7203`）；`--market` 是 `westock search` 唯一的可选参数，也支持按数字代码搜（如 `westock search 005930 --market kr`）。⚠️ **港股/美股/沪深直接 `westock search 关键词` 即可，切勿加 `--market hk/us/hs`**（仅 `jp|kr` 合法，其它值报「--market 仅支持 jp|kr」）。

---

## 十五、宏观

> 宏观经济指标。覆盖中国（GDP/CPI/PMI/货币/财政/估值/专项）+ 美/港/日/欧主题宏观日历 + 36 个地区海外预期日历。

### 子命令总览

```bash
# 列出指标（可按 region 过滤）
westock macro list                                       # 列全部
westock macro list --region cn                           # 中国（32 个）
westock macro list --region us                           # 美股（29 个）
westock macro list --region jp                           # 日本（6 个）
westock macro list --region eu                           # 欧元区（6 个）
westock macro list --region hk                           # 港股（4 个）
westock macro list --region global                       # 海外预期 36 个地区
westock macro expect list                                # 仅列 36 个地区

# 主题型指标查询（cn/us/hk/jp/eu）
westock macro indicator <短名 [短名...]> [--year Y | --date D | --start S --end E]

# 海外预期日历（按地区 iso3，按年）
westock macro expect --area <iso3> [--year Y | --start S --end E]

```

### 中国（cn）— 主题型指标

```bash
# 按年（GDP/价格/工业/消费/投资/货币/财政/预测/历史日历）
westock macro indicator cn_gdp --year 2025
westock macro indicator cn_cpi_ppi cn_pmi --year 2025                 # 多指标
westock macro indicator cn_pmi --start 2023 --end 2025                # 区间趋势
westock macro indicator cn_fiscal --year 2025                          # 财政
westock macro indicator cn_yield_curve --year 2025                     # 国债收益率曲线
westock macro indicator cn_mlf --year 2025                             # MLF 操作

# 按日期（综合 / 估值 / 中国专项）
westock macro indicator cn_core --date 2026-06-09                      # 最新核心（一键 p1+p2）
westock macro indicator cn_premium_curve --date 2026-06-09             # 溢价率曲线
westock macro indicator cn_premium_value --date 2026-06-09             # 溢价率水平（10年分位）
westock macro indicator cn_term_spread --date 2026-06-09               # 期限利差
westock macro indicator cn_calendar_future --date 2026-06-09           # 宏观日历未来
westock macro indicator cn_lpr --date 2026-06-09                       # LPR
westock macro indicator cn_caixin_pmi --date 2026-06-09                # 财新 PMI
westock macro indicator cn_installed_capacity --date 2026-06-09        # 发电装机容量

```

### 美/港/日/欧 — 主题宏观（按日期，事件日历型）

```bash
# 美股
westock macro indicator us_employment --date 2026-06-09                # 美国就业
westock macro indicator us_inflation --date 2026-06-09                 # 美国通胀
westock macro indicator us_employment us_inflation us_monetary --date 2026-06-09  # 多指标
westock macro indicator us_employment us_inflation us_monetary --date 2026-06-09 --limit 5  # 每指标仅最近 5 条

# 港股
westock macro indicator hk_eco_growth --date 2026-06-09
westock macro indicator hk_eco_growth hk_export_reserve hk_monetary hk_others --date 2026-06-09   # 港股全部 4 个

# 日本
westock macro indicator jp_inflation --date 2026-06-09
westock macro indicator jp_eco_growth jp_inflation jp_employment jp_confidence jp_monetary jp_export_reserve --date 2026-06-09   # 日本全部 6 个

# 欧元区
westock macro indicator eu_monetary --date 2026-06-09
westock macro indicator eu_eco_growth eu_inflation eu_monetary eu_confidence eu_export_reserve eu_employment --date 2026-06-09   # 欧元区全部 6 个

```

> 主题型返回 schema：`IndicatorName / OccurDate / OccurTime / ActualValue / ForecastValue / FormerValue`，按日期降序展示。

### 海外预期日历（global）— 按地区 iso3，按年

```bash
westock macro expect list                                     # 列 36 个地区 iso3 代码
westock macro expect --area chn --year 2025                # 中国
westock macro expect --area usa --year 2025                # 美国
westock macro expect --area jpn --year 2025                # 日本
westock macro expect --area usa --start 2023 --end 2025    # 区间

```

> 海外预期 schema 在主题型基础上多一列 `Importance`（1=低 / 2=中 / 3=高）。

### 短名命名规则

- 中国主题：`cn_<topic>`（如 `cn_gdp`/`cn_lpr`/`cn_premium_curve`）
- 海外主题：`<region>_<topic>`（如 `us_employment`/`jp_inflation`）
- 海外预期：`expect_<iso3>`（共 36 个地区，由 `westock macro expect list` 列出）
- 聚合短名：`cn_core` 一键拉 `cn_core_p1 + cn_core_p2`



| 分组 | 短名 | 查询方式 |
|------|------|----------|
| GDP | cn_gdp / cn_cpi_ppi / cn_pmi / cn_profit / cn_valueadded / cn_consumption / cn_investment / cn_export / cn_prosperity / cn_fiscal / cn_power_consumption / cn_disposable_income / cn_capacity_utilization / cn_product_output / cn_export_value | `--year`（后端按 YYYY-01-01） |
| 货币 | cn_financing / cn_fundquantity / cn_fundcost / cn_yield_curve / cn_mlf | `--year` |
| 估值 | **cn_premium_curve** / **cn_premium_value** / **cn_term_spread** | `--date` |
| 综合 | **cn_core**（聚合，自动展开 p1+p2） / cn_forecast / cn_calendar_hist / cn_calendar_future / cn_employment | cn_forecast/cn_calendar_hist 按 `--year`；cn_core/cn_calendar_future/cn_employment 按 `--date` |
| 中国专项 | cn_lpr / cn_caixin_pmi / cn_installed_capacity | `--date` |
| 美股主题 | us_employment / us_eco_growth / us_inflation / us_confidence / us_monetary / us_fiscal / us_energy / us_realestate | `--date`（事件日历型） |
| 港股主题 | hk_eco_growth / hk_export_reserve / hk_monetary / hk_others | `--date` |
| 日本主题 | jp_eco_growth / jp_inflation / jp_employment / jp_confidence / jp_monetary / jp_export_reserve | `--date` |
| 欧元区主题 | eu_eco_growth / eu_inflation / eu_monetary / eu_confidence / eu_export_reserve / eu_employment | `--date` |
| 海外预期 | expect_<iso3>（共 36 个地区，独立子命令 `westock macro expect --area`） | `--year` 或 `--start --end` |

> **三种查询方式**：
> 1. **按年份**（`--year` 或 `--start --end`）：cn_gdp/cn_cpi_ppi/cn_pmi 等绝大多数中国指标，后端按 `YYYY-01-01` 查询
> 2. **按日期**（`--date`）：`cn_core`/`cn_premium_*`/`cn_term_spread`/`cn_calendar_future`/`cn_employment`/`cn_lpr` 及海外事件日历型主题。并非所有海外主题都按日期；美国部分指标按年，必须先按 `macro list` 返回的 `mode` 选参。
> 3. **海外预期独立子命令**：`westock macro expect --area <iso3> --year`（按地区归档，36 个地区）
>
> **聚合短名**：`cn_core` 一键拉 `cn_core_p1 + cn_core_p2`（同时返回 7 大核心指标，不要用多次单指标查询拼凑）
>
> **拉某 region 全套**：`--region` 只属于 `macro list`；`macro indicator` 必须传短名，多个短名用**空格**分隔（先 `westock macro list --region us` 拿全部短名）
>
> **mode 校验**：传错 `--year` 给 mode=date 指标会报错；不确定时先 `westock macro list --region <r>` 查 mode

### 专业研究场景速查（指标组合）

> 按机构投研常用研究框架组织。每行对应 `scenarios-guide.md` 中的一个专业场景。

```bash
# 通胀全景（场景 59）：CPI/PPI 剪刀差、核心 CPI、上下游传导
westock macro indicator cn_cpi_ppi --start 2024 --end 2025

# 国债收益率曲线（场景 60）：期限结构 + 牛陡/熊平判断
westock macro indicator cn_yield_curve --year 2025
westock macro indicator cn_term_spread --date 2026-06-08

# 股债性价比 / 风险溢价（场景 61）：大类资产配置核心指标（含 10 年分位）
westock macro indicator cn_premium_value --date 2026-06-08
westock macro indicator cn_premium_curve --date 2026-06-08

# 流动性投放与货币市场（场景 62）：MLF 操作 + SHIBOR/回购利率
westock macro indicator cn_mlf --year 2025
westock macro indicator cn_fundcost --year 2025

# 工业景气全景（场景 63）：5 维交叉验证（量/效/能/景气/产量）
westock macro indicator cn_profit cn_valueadded cn_prosperity cn_capacity_utilization cn_power_consumption --year 2025
westock macro indicator cn_product_output --year 2025

# 财政发力强度（场景 64）：收支结构 + 专项债进度
westock macro indicator cn_fiscal --year 2025

# 进出口深度解读（场景 65）：贸易差额 + 行业出口结构
westock macro indicator cn_export --year 2025
westock macro indicator cn_export_value --year 2025

# 居民收入与消费（场景 66）：收入结构 + 消费分项
westock macro indicator cn_disposable_income --year 2025
westock macro indicator cn_consumption --year 2025

# 就业市场（场景 67）：失业率分组 + 百度搜索指数高频信号
westock macro indicator cn_employment --date 2026-06-08

# 宏观日历事件预案（场景 68）：未来事件 + 历史回放 + 机构预测
westock macro indicator cn_calendar_future --date 2026-06-08
westock macro indicator cn_calendar_hist --year 2025
westock macro indicator cn_forecast --year 2025

# 中国专项（场景 69）：LPR / 财新 PMI / 装机容量
westock macro indicator cn_lpr cn_caixin_pmi cn_installed_capacity --date 2026-06-08

# 海外宏观日历（场景 70）：美/港/日/欧 主题事件
westock macro indicator us_employment us_inflation us_monetary --date 2026-06-08   # 美股主要主题
westock macro indicator us_employment us_inflation --date 2026-06-08
westock macro indicator jp_monetary --date 2026-06-08         # 日本央行政策
westock macro indicator eu_inflation --date 2026-06-08         # 欧元区通胀

# 海外预期日历（场景 71）：按地区 iso3 查事件 actual/forecast/former
westock macro expect --area chn --year 2025                # 中国
westock macro expect --area usa --start 2023 --end 2025    # 美国（区间）
westock macro expect --area jpn --year 2025                # 日本

# 美联储降息预期跟踪（场景 72）：FFR 利率 + FOMC 一致预期
westock macro indicator us_monetary --date 2026-06-08
westock macro expect --area usa --year 2026                # 看 FOMC 事件 ForecastValue

# 美国通胀压力多维评估（场景 73）：CPI/PCE/PPI + 通胀预期
westock macro indicator us_inflation --date 2026-06-08

# 中美宏观对比（场景 74）：增长/通胀/货币三维度
westock macro indicator us_eco_growth us_inflation us_monetary --date 2026-06-08   # 美国增长/通胀/货币
westock macro indicator cn_core --date 2026-06-08             # 中国核心一键

# 港股宏观（场景 75）：联系汇率制度下的双重驱动
westock macro indicator hk_eco_growth hk_export_reserve hk_monetary hk_others --date 2026-06-08
westock macro indicator us_monetary --date 2026-06-08         # 港币随美联储

# 全球三大央行流动性对比（场景 76）：美日欧政策路径
westock macro indicator us_monetary jp_monetary eu_monetary --date 2026-06-08

```


---

## 十六、期货

> 外盘商品/金融期货（CME/COMEX/CBOT/NYMEX/LME 等）+ 港股股指期货。
> 标准代码前缀：`fu*`（外盘长版行情）、`hf_*`（LME 金属）、`r_hd*`（港股股指期货）。

### 合约搜索与资料

```bash
westock search 黄金 --type futures            # 关键词→合约代码（支持 名称/品类/交易所/代码）
westock search 贵金属 --type futures           # 按品类搜（贵金属/基本金属/能源化工/农产品/外汇/利率/股指/港股股指）
westock search 恒指 --type futures             # 港股股指期货
westock futures detail fuGC                   # 合约资料（交易所/规模/币种/最小变动/交易时间等）

```

### 期货行情（复用 quote）

```bash
westock quote fuGC                            # 黄金（COMEX，延时行情）
westock quote hf_CAD                           # 伦铜（LME）
westock quote r_hdHSImain                      # 恒生指数期货
westock quote fuGC,fuCL,fu6E                   # 批量（黄金/原油/欧元）

```

### 期货分时与 K 线（复用 minute / kline）

```bash
westock minute fuCN                            # 富时A50指数期货分时（当日）
westock minute fuCN --days 5                   # 五日分时
westock minute r_hdHSImain                     # 恒指期货分时
westock kline fuGC --period day --limit 30     # 黄金日K（含 OHLC/成交量/持仓量）
westock kline fuCN --period week --limit 20    # 周K（day/week/month/season/year）
westock kline r_hdHSImain --period day         # 恒指期货K线

```

> ⚠️ **期货限制**：外盘期货多为**延时行情**（输出 `isDelayed`）。`westock minute`/`westock kline` 仅支持带 `stockType` 的合约（`fu*` 外盘、`r_hd*` 港股股指）；`hf_*`（LME 金属/伦敦金银现货）**仅支持 `westock quote`**，不支持分时/K线。期货**不支持复权**（`--fq` 对期货无效）。相关新闻直接使用 `web_search` 检索并核验原文。合约代码请先用 `westock search --type futures` 获取，避免猜测。

---

## 十七、外汇

> 离岸人民币、主要货币对、美元指数等即期现货汇率。
> 标准代码前缀：`fx*`（如 `fxCNH` 离岸人民币、`fxUSDJPY` 美元日元、`fxDINIW` 美元指数）。

### 品种搜索与列表

```bash
westock forex list                            # 列出全部外汇品种（代码/名称）
westock search 美元 --type forex              # 关键词→品种代码（匹配 名称/代码/裸代码）
westock search 离岸 --type forex              # 离岸人民币 → fxCNH
westock search 日元 --type forex              # 含日元的货币对（fxUSDJPY/fxEURJPY 等）

```

