# 宏观经济指标字段说明 · 分册 01

[本手册索引](macro-fields.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

# 宏观经济指标字段说明

本文档列出 `westock macro` 命令返回的所有字段及其含义。

> 数据来源：腾讯自选股宏观经济数据接口

## 子命令总览

```bash
westock macro list [--region cn|us|hk|jp|eu|global]    # 列出指标
westock macro indicator <短名 [短名...]> [...]          # 查主题型指标（多指标用空格分隔）
westock macro expect list                               # 列 36 个地区
westock macro expect --area <iso3> [--year Y | --start --end]  # 海外预期日历

```

每个 entry 在注册表里声明 `region` + `mode`：
- `mode=date` → 用 `--date`（默认今天），底层 `query_list_data_by_date(实际日期)`
- `mode=year` → 用 `--year`/`--start --end`，底层 `query_list_data_by_date(YYYY-01-01)`

## 指标清单（短名表）

### 中国 (cn) — 按年查询指标（22 个）

| 短名 | 完整代码 | 名称 | 分类 |
| --- | --- | --- | --- |
| `cn_gdp` | `macro_gdp` | GDP数量指标 | GDP |
| `cn_cpi_ppi` | `macro_cpi_ppi` | GDP价格指标(CPI/PPI) | GDP |
| `cn_pmi` | `macro_pmi` | GDP供给指标(PMI) | GDP |
| `cn_profit` | `macro_profit` | GDP供给指标(工业企业利润) | GDP |
| `cn_valueadded` | `macro_valueadded` | GDP供给指标(工业增加值) | GDP |
| `cn_consumption` | `macro_consumption` | GDP需求指标(消费) | GDP |
| `cn_investment` | `macro_investment` | GDP需求指标(投资) | GDP |
| `cn_export` | `macro_export` | GDP需求指标(进出口) | GDP |
| `cn_export_value` | `macro_export_value` | GDP需求指标(出口交货值) | GDP |
| `cn_prosperity` | `macro_prosperity` | GDP供给指标(企业景气指数) | GDP |
| `cn_fiscal` | `macro_fiscal` | GDP财政指标 | GDP |
| `cn_power_consumption` | `macro_power_consumption` | GDP供给指标(用电量) | GDP |
| `cn_disposable_income` | `macro_disposable_income` | GDP需求指标(可支配收入) | GDP |
| `cn_capacity_utilization` | `macro_capacity_utilization` | GDP供给指标(产能利用率) | GDP |
| `cn_product_output` | `macro_product_output` | GDP供给指标(宏观产量) | GDP |
| `cn_financing` | `macro_financing` | 货币需求指标(社融) | 货币 |
| `cn_fundquantity` | `macro_fundquantity` | 货币供给指标(数量) | 货币 |
| `cn_fundcost` | `macro_fundcost` | 货币供给指标(利率) | 货币 |
| `cn_yield_curve` | `macro_yield_curve` | 货币供给指标(国债收益率曲线) | 货币 |
| `cn_mlf` | `macro_mlf` | 货币供给指标(公开市场操作/MLF) | 货币 |
| `cn_forecast` | `macro_forecast` | 宏观预测 | 综合 |
| `cn_calendar_hist` | `macro_calendar_hist` | 宏观日历历史 | 综合 |

### 中国 (cn) — 按日期查询指标（11 个）

| 短名 | 完整代码 | 名称 | 分类 |
| --- | --- | --- | --- |
| `cn_core` | `macro_core_indicators_cur_p1/p2` | 最新核心宏观指标（聚合短名，一键拉 p1+p2） | 综合 |
| `cn_core_p1` | `macro_core_indicators_cur_p1` | 最新核心宏观指标(1) | 综合 |
| `cn_core_p2` | `macro_core_indicators_cur_p2` | 最新核心宏观指标(2) | 综合 |
| `cn_employment` | `macro_employment` | 就业情况 | 综合 |
| `cn_calendar_future` | `macro_calendar_future` | 宏观日历未来 | 综合 |
| `cn_premium_curve` | `macro_premium_curve` | 溢价率曲线(红利/股债) | 估值 |
| `cn_premium_value` | `macro_premium_value` | 溢价率水平(含10年分位) | 估值 |
| `cn_term_spread` | `macro_term_spread` | 期限利差与曲线形态 | 估值 |
| `cn_lpr` | `macro_lpr` | 贷款市场报价利率(LPR) | 中国专项 |
| `cn_caixin_pmi` | `macro_caixin_pmi` | 财新PMI | 中国专项 |
| `cn_installed_capacity` | `macro_installed_capacity` | 发电装机容量 | 中国专项 |

### 美股 (us) — 按日期主题指标（24 个）

| 短名 | 完整代码 | 名称 |
| --- | --- | --- |
| `us_employment` | `macro_us_employment` | 美股宏观(就业) |
| `us_eco_growth` | `macro_us_eco_growth` | 美股宏观(经济增长) |
| `us_inflation` | `macro_us_inflation` | 美股宏观(通胀) |
| `us_confidence` | `macro_us_confidence` | 美股宏观(景气指数) |
| `us_monetary` | `macro_us_monetary` | 美股宏观(货币政策) |
| `us_fiscal` | `macro_us_fiscal` | 美股宏观(财政政策) |
| `us_energy` | `macro_us_energy` | 美股宏观(能源板块) |
| `us_realestate` | `macro_us_realestate` | 美股宏观(地产板块) |
| `us_consumption` | `macro_us_consumption` | 美股宏观(消费) |
| `us_manufacturing` | `macro_us_manufacturing` | 美股宏观(工业生产) |
| `us_trade` | `macro_us_trade` | 美股宏观(对外贸易) |
| `us_treasury_holders` | `macro_us_treasury_holders` | 美股宏观(国债持有分布) |
| `us_fiscal_p2` | `macro_us_fiscal_p2` | 美股宏观(财政政策P2) |
| `us_monetary_p2` | `macro_us_monetary_p2` | 美股宏观(货币政策P2) |
| `us_fed_asset` | `macro_us_fed_asset` | 美股宏观(美联储资产结构) |
| `us_fed_liability` | `macro_us_fed_liability` | 美股宏观(美联储负债结构) |
| `us_fed_netliquidity` | `macro_us_fed_netliquidity` | 美股宏观(美联储净流动性) |
| `us_fed_qe_qt_status` | `macro_us_fed_qe_qt_status` | 美股宏观(美联储QE/QT状态) |
| `us_vix` | `macro_us_vix` | 美股宏观(VIX) |
| `us_usd_index` | `macro_us_usd_index` | 美股宏观(美元指数) |
| `us_key_index` | `macro_us_key_index` | 美股宏观(三大股指) |
| `us_debt_size` | `macro_us_debt_size` | 美股宏观(债务规模) |
| `us_term_spread_10y2y` | `macro_us_term_spread_10y2y` | 美股宏观(期限利差-10y2y) |
| `us_term_spread_10y3m` | `macro_us_term_spread_10y3m` | 美股宏观(期限利差-10y3m) |

### 美股 (us) — 按年主题指标（5 个）

| 短名 | 完整代码 | 名称 |
| --- | --- | --- |
| `us_yield_curve` | `macro_us_yield_curve` | 美股宏观(国债收益率曲线) |
| `us_policy_rate_anchor` | `macro_us_policy_rate_anchor` | 美股宏观(政策利率锚) |
| `us_sofr_real_rate` | `macro_us_sofr_real_rate` | 美股宏观(SOFR实际利率) |
| `us_sofr_exp_rate` | `macro_us_sofr_exp_rate` | 美股宏观(SOFR市场预期利率) |
| `us_broad_rate` | `macro_us_broad_rate` | 美股宏观(广义短端与长端利率) |

### 港股 / 日本 / 欧元区 — 按日期主题指标

| 区域 | 数量 | 短名 |
| --- | --- | --- |
| 港股 (hk) | 4 个 | `hk_eco_growth` / `hk_export_reserve` / `hk_monetary` / `hk_others` |
| 日本 (jp) | 6 个 | `jp_eco_growth` / `jp_inflation` / `jp_employment` / `jp_confidence` / `jp_monetary` / `jp_export_reserve` |
| 欧元区 (eu) | 6 个 | `eu_eco_growth` / `eu_inflation` / `eu_monetary` / `eu_confidence` / `eu_export_reserve` / `eu_employment` |

> 这些主题指标返回**事件日历型数据**：每条记录对应一次具体的指标发布（如"美国 5 月 ISM 制造业 PMI"）。统一 schema：`IndicatorName / OccurDate / OccurTime / ActualValue / ForecastValue / FormerValue`。

### 海外预期日历 (global) — 按年（按地区 iso3）

通过 `westock macro expect --area <地区标识>` 查询，合法值先用 `westock macro expect list` 获取。旧表头中的 `iso3` 是后端地区标识的历史叫法，包含 `hk/eu/uk/efta/glo` 等非标准三字母代码，禁止擅自标准化替换。下表为离线示例：

| iso3 | 国家/地区 | iso3 | 国家/地区 | iso3 | 国家/地区 |
| --- | --- | --- | --- | --- | --- |
| `chn` | 中国 | `usa` | 美国 | `jpn` | 日本 |
| `hk` | 中国香港 | `twn` | 中国台湾 | `kor` | 韩国 |
| `sgp` | 新加坡 | `aus` | 澳大利亚 | `nzl` | 新西兰 |
| `ind` | 印度 | `idn` | 印度尼西亚 | `mys` | 马来西亚 |
| `tha` | 泰国 | `phl` | 菲律宾 | `vnm` | 越南 |
| `eu` | 欧洲联盟 | `euz` | 欧元区 | `efta` | 欧英EFTA |
| `uk` | 英国 | `fra` | 法国 | `deu` | 德国 |
| `ita` | 意大利 | `esp` | 西班牙 | `grc` | 希腊 |
| `che` | 瑞士 | `swe` | 瑞典 | `nor` | 挪威 |
| `rus` | 俄罗斯 | `ukr` | 乌克兰 | `tur` | 土耳其 |
| `can` | 加拿大 | `mex` | 墨西哥 | `bra` | 巴西 |
| `chl` | 智利 | `zaf` | 南非 | `glo` | 全球 |

> 海外预期 schema：`IndicatorName / OccurDate / OccurTime / ActualValue / ForecastValue / FormerValue / Importance`（`Importance` 为重要程度 1~3）。

---

## 统一字段说明（主题型 + 海外预期共用）

| 字段 | 说明 |
| --- | --- |
| `IndicatorName` | 指标名（中文，如"美国 5 月非农就业"） |
| `OccurDate` | 数据发生/发布日期（YYYYMMDD） |
| `OccurTime` | 发布时间（HH:MM） |
| `ActualValue` | 实际值（已发布） |
| `ForecastValue` | 市场预测值 |
| `FormerValue` | 前值 |
| `Importance` | 重要程度（仅海外预期，1=低 / 2=中 / 3=高） |



## GDP数量指标

| 字段 | 说明 |
| ---- | ---- |
| `CONTRI_ALGRICULTURE_CUM` | GDP贡献率:农林牧渔业:累计值:季(%) |
| `CONTRI_BUILD_CUM` | GDP贡献率:建筑业:累计值:季(%) |
| `CONTRI_CAPITAL_CUM` | GDP贡献率:资本形成总额:累计值:季(%) |
| `CONTRI_CAPITAL_CUR` | GDP贡献率:资本形成总额:当期值:季(%) |
| `CONTRI_CONSUME_CUM` | GDP贡献率:最终消费支出:累计值:季(%) |
| `CONTRI_CONSUME_CUR` | GDP贡献率:最终消费支出:当期值:季(%) |
| `CONTRI_FINANCE_CUM` | GDP贡献率:金融业:累计值:季(%) |
| `CONTRI_FIRST_CUM` | GDP贡献率:第一产业:累计值:季(%) |
| `CONTRI_FIRST_CUR` | GDP贡献率:第一产业:当期值:季(%) |
| `CONTRI_IMPORT_CUM` | GDP贡献率:货物和服务净出口:累计值:季(%) |
| `CONTRI_IMPORT_CUR` | GDP贡献率:货物和服务净出口:当期值:季(%) |
| `CONTRI_IT_CUM` | GDP贡献率:信息传输、软件和信息技术服务业:累计值:季(%) |
| `CONTRI_MANUFACTURE_CUM` | GDP贡献率:工业:累计值:季(%) |
| `CONTRI_OTHER_CUM` | GDP贡献率:其他服务业:累计值:季(%) |
| `CONTRI_REALESTATE_CUM` | GDP贡献率:房地产业:累计值:季(%) |
| `CONTRI_RENT_CUM` | GDP贡献率:租赁和商务服务业:累计值:季(%) |
| `CONTRI_RESTERAUNT_CUM` | GDP贡献率:住宿和餐饮业:累计值:季(%) |
| `CONTRI_RETAIL_CUM` | GDP贡献率:批发和零售业:累计值:季(%) |
| `CONTRI_SECOND_CUM` | GDP贡献率:第二产业:累计值:季(%) |
| `CONTRI_SECOND_CUR` | GDP贡献率:第二产业:当期值:季(%) |
| `CONTRI_THIRD_CUM` | GDP贡献率:第三产业:累计值:季(%) |
| `CONTRI_THIRD_CUR` | GDP贡献率:第三产业:当期值:季(%) |
| `CONTRI_TRANSPORT_CUM` | GDP贡献率:交通运输、仓储和邮政业:累计值:季(%) |
| `GDP_ENDDATE` | GDP指标截止日期 |
| `GDP_INFOPUBLDATE` | GDP指标发布日期 |
| `NOMINAL_GDP_CUM` | GDP(现价):累计值:季(亿) |
| `NOMINAL_GDP_CUM_YOY` | GDP(现价):累计同比:季(亿) |
| `NOMINAL_GDP_CUR` | GDP(现价):当期值:季(亿) |
| `NOMINAL_GDP_CUR_YOY` | GDP(现价):当期同比:季(亿) |
| `PULL_ALGRICULTURE_CUM` | GDP拉动率:农林牧渔业:累计值:季(%) |
| `PULL_BUILD_CUM` | GDP拉动率:建筑业:累计值:季(%) |
| `PULL_CAPITAL_CUM` | GDP拉动率:资本形成总额:累计值:季(%) |
| `PULL_CAPITAL_CUR` | GDP拉动率:资本形成总额:当期值:季(%) |
| `PULL_CONSUME_CUM` | GDP拉动率:最终消费支出:累计值:季(%) |
| `PULL_CONSUME_CUR` | GDP拉动率:最终消费支出:当期值:季(%) |
| `PULL_FINANCE_CUM` | GDP拉动率:金融业:累计值:季(%) |
| `PULL_FIRST_CUM` | GDP拉动率:第一产业:累计值:季(%) |
| `PULL_FIRST_CUR` | GDP拉动率:第一产业:当期值:季(%) |
| `PULL_IMPORT_CUM` | GDP拉动率:货物和服务净出口:累计值:季(%) |
| `PULL_IMPORT_CUR` | GDP拉动率:货物和服务净出口:当期值:季(%) |
| `PULL_IT_CUM` | GDP拉动率:信息传输、软件和信息技术服务业:累计值:季(%) |
| `PULL_MANUFACTURE_CUM` | GDP拉动率:工业:累计值:季(%) |
| `PULL_OTHER_CUM` | GDP拉动率:其他服务业:累计值:季(%) |
| `PULL_REALESTATE_CUM` | GDP拉动率:房地产业:累计值:季(%) |
| `PULL_RENT_CUM` | GDP拉动率:租赁和商务服务业:累计值:季(%) |
| `PULL_RESTERAUNT_CUM` | GDP拉动率:住宿和餐饮业:累计值:季(%) |
| `PULL_RETAIL_CUM` | GDP拉动率:批发和零售业:累计值:季(%) |
| `PULL_SECOND_CUM` | GDP拉动率:第二产业:累计值:季(%) |
| `PULL_SECOND_CUR` | GDP拉动率:第二产业:当期值:季(%) |
| `PULL_THIRD_CUM` | GDP拉动率:第三产业:累计值:季(%) |
| `PULL_THIRD_CUR` | GDP拉动率:第三产业:当期值:季(%) |
| `PULL_TRANSPORT_CUM` | GDP拉动率:交通运输、仓储和邮政业:累计值:季(%) |
| `REAL_GDP_CUM` | GDP(不变价):累计值:季(亿) |
| `REAL_GDP_CUM_YOY` | GDP(不变价):累计同比:季(%) |
| `REAL_GDP_CUR` | GDP(不变价):当期值:季(亿) |
| `REAL_GDP_CUR_YOY` | GDP(不变价):当期同比:季(%) |

## CPI/PPI（GDP价格指标）

| 字段 | 说明 |
| ---- | ---- |
| `CPI_PPI_ENDDATE` | CPI-PPI指标截止日期 |
| `CPI_PPI_INFOPUBLDATE` | CPI-PPI指标发布日期 |
| `CPI_YOY` | CPI:当期同比:月(%) |
| `CPI_YOY_CORE` | CPI:不包括食品和能源:当期同比:月(%) |
| `CPI_YOY_FOOD` | CPI:食品类:当期同比:月(%) |
| `CPI_YOY_JTTX` | CPI:交通和通信类:当期同比:月(%) |
| `CPI_YOY_JYWY` | CPI:教育文化和娱乐类:当期同比:月(%) |
| `CPI_YOY_JZ` | CPI:居住类:当期同比:月(%) |
| `CPI_YOY_NON_FOOD` | CPI:非食品类:当期同比:月(%) |
| `CPI_YOY_OTHER` | CPI:其他用品和服务类:当期同比:月(%) |
| `CPI_YOY_SHYP` | CPI:生活用品及服务类:当期同比:月(%) |
| `CPI_YOY_SPYJ` | CPI:食品烟酒类:当期同比:月(%) |
| `CPI_YOY_YLBJ` | CPI:医疗保健类:当期同比:月(%) |
| `CPI_YOY_YZ` | CPI:衣着类:当期同比:月(%) |
| `PPIRM_MOM` | 工业生产者购进价格指数PPIRM:环比:月(%) |
| `PPIRM_MOM_AGRICULTURE` | 工业生产者购进价格指数PPIRM:农副产品类:环比:月(%) |
| `PPIRM_MOM_BLACK_METAL` | 工业生产者购进价格指数PPIRM:黑色金属材料类:环比:月(%) |
| `PPIRM_MOM_BUILDING` | 工业生产者购进价格指数PPIRM:建筑材料类:环比:月(%) |
| `PPIRM_MOM_CHEMICAL_METAL` | 工业生产者购进价格指数PPIRM:化工原料类:环比:月(%) |
| `PPIRM_MOM_FUEL` | 工业生产者购进价格指数PPIRM:燃料、动力类:环比:月(%) |
| `PPIRM_MOM_INDUSTRIAL` | 工业生产者购进价格指数PPIRM:其他工业原材料及半成品类:环比:月(%) |
| `PPIRM_MOM_NONFERROUS_METAL` | 工业生产者购进价格指数PPIRM:有色金属材料类:环比:月(%) |
| `PPIRM_MOM_TEXTILE` | 工业生产者购进价格指数PPIRM:纺织原料类:环比:月(%) |
| `PPIRM_MOM_TIMBER` | 工业生产者购进价格指数PPIRM:木材及纸浆类:环比:月(%) |
| `PPIRM_YOY` | 工业生产者购进价格指数PPIRM:当期同比:月(%) |
| `PPIRM_YOY_AGRICULTURE` | 工业生产者购进价格指数PPIRM:农副产品类:当期同比:月(%) |
| `PPIRM_YOY_BLACK_METAL` | 工业生产者购进价格指数PPIRM:黑色金属材料类:当期同比:月(%) |
| `PPIRM_YOY_BUILDING` | 工业生产者购进价格指数PPIRM:建筑材料类:当期同比:月(%) |
| `PPIRM_YOY_CHEMICAL_METAL` | 工业生产者购进价格指数PPIRM:化工原料类:当期同比:月(%) |
| `PPIRM_YOY_FUEL` | 工业生产者购进价格指数PPIRM:燃料、动力类:当期同比:月(%) |
| `PPIRM_YOY_INDUSTRIAL` | 工业生产者购进价格指数PPIRM:其他工业原材料及半成品类:当期同比:月(%) |
| `PPIRM_YOY_NONFERROUS_METAL` | 工业生产者购进价格指数PPIRM:有色金属材料类:当期同比:月(%) |
| `PPIRM_YOY_TEXTILE` | 工业生产者购进价格指数PPIRM:纺织原料类:当期同比:月(%) |
| `PPIRM_YOY_TIMBER` | 工业生产者购进价格指数PPIRM:木材及纸浆类:当期同比:月(%) |
| `PPI_YOY` | PPI:当期同比:月(%) |
| `PPI_YOY_CONSUM` | PPI:耐用消费品类:当期同比:月(%) |
| `PPI_YOY_FOOD` | PPI:食品类:当期同比:月(%) |
| `PPI_YOY_LIVE` | PPI:生活资料:当期同比:月(%) |
| `PPI_YOY_PRODUCE` | PPI:生产资料:当期同比:月(%) |
| `PPI_YOY_USE` | PPI:一般日用品类:当期同比:月(%) |
| `PPI_YOY_WEAR` | PPI:衣着类:当期同比:月(%) |
| `PRICE_SCISSORS_CPI_PPI` | CPI-PPI:当期同比:月(%) |
| `PRICE_SCISSORS_CPI_PPI_FOOD` | CPI-PPI:食品类:当期同比:月(%) |
| `PRICE_SCISSORS_PPI_PPIRM` | PPI-PPIRM:当期同比:月(%) |

## PMI（GDP供给指标）

| 字段 | 说明 |
| ---- | ---- |
| `PMI_COMPREHENSIVE_CCZS` | 综合PMI:产出指数:季调:月 |
| `PMI_COMPREHENSIVE_CCZS_MOM` | 综合PMI:产出指数:季调:环比:月(%) |
| `PMI_ENDDATE` | PMI指标截止日期 |
| `PMI_INFOPUBLDATE` | PMI指标发布日期 |
| `PMI_MANU` | 制造业PMI:季调:月 |
| `PMI_MANU_CUR_YOY` | 制造业PMI:当期同比:月(%) |
| `PMI_MANU_IMPORT` | 制造业PMI:进口:季调:月 |
| `PMI_MANU_MOM` | 制造业PMI:季调:环比:月(%) |
| `PMI_MANU_ORDER_EXPORT` | 制造业PMI:新出口订单:季调:月 |
| `PMI_MANU_ORDER_INHAND` | 制造业PMI:在手订单:季调:月 |
| `PMI_MANU_ORDER_NEW` | 制造业PMI:新订单:季调:月 |
| `PMI_MANU_PRODUCE` | 制造业PMI:生产:季调:月 |
| `PMI_MANU_PRODUCT_INVENTORY` | 制造业PMI:产成品库存:季调:月 |
| `PMI_MANU_PURCHASE` | 制造业PMI:采购量:季调:月 |
| `PMI_MANU_RAWMATERIAL_INVENTORY` | 制造业PMI:原材料库存:季调:月 |
| `PMI_MANU_RAWMATERIAL_PURCHASE` | 制造业PMI:主要原材料购进价格:季调:月 |
| `PMI_NON_MANU_BUSINESS_ACTIVITY` | 非制造业PMI:商务活动:季调:月 |
| `PMI_NON_MANU_MATERIAL_PRICE` | 非制造业PMI:投入品价格:季调:月 |
| `PMI_NON_MANU_ORDER_EXPORT` | 非制造业PMI:新出口订单:季调:月 |
| `PMI_NON_MANU_ORDER_NEW` | 非制造业PMI:新订单:季调:月 |

## 工业企业利润（GDP供给指标）

| 字段 | 说明 |
| ---- | ---- |
| `ENTERPRISE_PROFIT_CUM` | 规模以上工业企业利润总额:累计值:月 |
| `ENTERPRISE_PROFIT_CUM_YOY` | 规模以上工业企业利润总额:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_CHEMICAL` | 规模以上工业企业利润总额:化学原料和化学制品制造业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_COAL` | 规模以上工业企业利润总额:煤炭开采和洗选业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_COMMON_EQUIP` | 规模以上工业企业利润总额:通用设备制造业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_DEDICATED_EQUIP` | 规模以上工业企业利润总额:专用设备制造业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_ELECTRIC` | 规模以上工业企业利润总额:电力、热力生产和供应业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_ELECTRIC_EQUIP` | 规模以上工业企业利润总额:电气机械和器材制造业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_FOOD` | 规模以上工业企业利润总额:食品制造业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_FURNITURE` | 规模以上工业企业利润总额:家具制造业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_INSTRUMENTATION` | 规模以上工业企业利润总额:仪器仪表制造业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_MEDICINE` | 规模以上工业企业利润总额:医药制造业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_METAL` | 规模以上工业企业利润总额:有色金属冶炼和压延加工业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_OIL` | 规模以上工业企业利润总额:石油和天然气开采业:累计同比:月(%) |
| `ENTERPRISE_PROFIT_CUM_YOY_PLASTIC` | 规模以上工业企业利润总额:橡胶和塑料制品业:累计同比:月(%) |
| `PROFIT_ENDDATE` | 工业企业利润指标截止日期 |
| `PROFIT_INFOPUBLDATE` | 工业企业利润指标发布日期 |

