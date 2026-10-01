---
name: sw-index-query
description: 查询和分析申万行业板块的行情、日周月K线、技术指标、成分名单、估值、热力轮动、排名、收益风险、相关性和指数级组合，并生成交互式HTML图表或研报。支持登记的外部常用指数对比，并可通过网页检索补充经核实的行情、公告和说明。
---

# 申万指数查询与分析

优先通过 **westock CLI** 获取行情，复用本技能的计算和 ECharts/HTML 报告。需要补充行情、估值、公告或编制说明时，可使用当前环境的网页搜索与页面读取工具。

## 数据与分析范围

查询前阅读 [references/DATA_SOURCE.md](references/DATA_SOURCE.md)，再按下表读取对应任务参考。

- 内部及脚本参数统一使用六位申万代码，如 `801010`。仅 `scripts/datasource.py` 转换为 `pt01801010`；不要让用户手工加前缀。
- 市场参照路由涉及**申万50（801001）**时，直接使用**中证A50（930050）**；用户关注沪市大型龙头时可用**上证50（000016）**。`sw_common.resolve_market_reference` 给出实际代码与名称，风格研报采用这两项宽基参照。查询参数、标题、图例、摘要均使用替代指数的真实名称和代码，不把其点位/成分/历史标为申万50。日K与对比走 `external_indices`；其余需求按 westock skill/websearch 核实对应指数，不加申万板块前缀。用户明确核验原申万50的成分或历史时，替代参照不代表已完成原指数核验。
- 行业数据是**板块口径**，不保证等同申万官方指数点位。交付包含：**“数据来源：腾讯自选股（申万行业板块口径），行情可能有延迟，以交易所披露为准。”** 显示真实数据截止日期，不将查询日等同数据日。
- 成分查询优先交付名单。只有具备经核实的权重时才展示集中度、权重饼图和行业分布，不默认声称等权。
- 估值使用行业 `PeTTM` / `PbLF`，不能与实时行情的 `pe_ratio` / `pb_ratio` 混写。供应商历史百分位的窗口未指定，不可标成“近5年分位”。用户指定年数时必须核验实际日期覆盖。
- 基金指数 `807xxx/808xxx`、大类风格 `801271–801276`、金创 `802608–802612`：优先通过网页检索核实对应指数的名称、行情和日期，不用普通行业替代。其他类别同样以实际可核实的对应指数数据为准。
- 官方公告、编制说明和行业权重：通过网页检索查找发布机构或可核实的原文，交付标题、日期和原文链接；不把新闻改称官方公告。
- 分时展示分钟粒度。仅展示实际具备的成交额，不补0或插值成10秒。
- 风格研报可结合可用金融工具或网页检索核实的市场广度/两融 JSON。未能核实的维度不作推断，回复聚焦本次已覆盖的板块与观察范围。

## 数据补充与最终回复

- **优先 westock，必要时网页补充。** 脚本执行异常、所需字段或品种未覆盖时，在内部记录诊断，再搜索对应指数的最新或指定日期行情。优先发布机构、交易所或有清晰来源及时间的金融数据页面；记录来源名称、链接、实际交易日期、单位和口径。
- 网页数字须打开原页面核实，不只凭搜索摘要。区分盘中价格、收盘价、发布日期和交易日期；来源间口径不同的结果分列，不拼成同一序列。
- 只有获得完整、可核实的 OHLC 时间序列，才能补入技术指标图、收益和回测计算。零散点位只能用于文字或表格快照，不插值、不编造 K 线，不计算缺乏依据的 MACD。
- **最终回复及交付页面不讲内部执行过程。** 不出现“接口”“API”“数据取不到”“取数失败”“服务不可用”、错误码、额度、安装/授权排查或服务背景说明；不把脚本 stdout/stderr 的报错原样转发给用户。只有用户明确要求技术排查时，才在该排查答复中提供必要诊断。
- 回复给出结论、实际截止日期、分析范围、已核实的数据和产物；来源用机构/产品名称及网页链接表达，不称“某某接口”。
- 仍无法核实某项时，客观说明结果范围或结论边界，不掩盖重要限制。例如：“本次展示成分名单，未计算权重集中度。”“这组样本覆盖2026年6月至9月，适合观察近期变化，不能据此判断5年分位。”“目前可核实的资料尚不能支持这一结论。” 不假装已完成用户要求的完整历史分析。

## 任务路由

识别意图、指数名称和时间/范围 → 阅读相应参考 → 执行脚本 → 检查 JSON 摘要和产物 → 交付。

| 用户意图 | 参考 | 脚本 |
|---|---|---|
| 实时分时、MA/MACD/BOLL/KDJ图、多指数对比 | [SW_CHART](references/SW_CHART.md) | `sw_chart.py --mode realtime/indicator/compare` |
| 单指数日/周/月K线、技术研报（含外部指数） | [SW_KLINE_REPORT](references/SW_KLINE_REPORT.md) | `sw_kline_report.py` |
| 31行业或指定范围市场全景 | [SW_DASH](references/SW_DASH.md) | `sw_dashboard.py` |
| 行业热力、轮动四象限、内部分化 | [SW_HEAT](references/SW_HEAT.md) | `sw_heatmap.py`，分化加 `--show-dispersion` |
| 风格研报 | [SW_STYLE_REPORT](references/SW_STYLE_REPORT.md) | `sw_style_report.py --breadth-json ...`，先核验数据完整性 |
| 深度分析、技术诊断/事件后验 | [SW_DEEP](references/SW_DEEP.md)、[SW_TECH](references/SW_TECH.md) | `sw_deep.py`、`sw_tech.py` |
| 收益风险矩阵、单指数全指标 | [SW_RISK](references/SW_RISK.md)、[SW_STATS](references/SW_STATS.md) | `sw_risk_matrix.py`、`sw_stats.py` |
| 双指数回归/Beta/Alpha | [SW_REGRESSION](references/SW_REGRESSION.md) | `sw_regression.py` |
| ≥3指数相关矩阵 | [SW_CORR](references/SW_CORR.md) | `sw_corr_matrix.py`，31行业用 `--scope l1` |
| 指数级加权组合 | [SW_PORTFOLIO](references/SW_PORTFOLIO.md) | `sw_portfolio_agg.py`，个股组合不在本技能范围 |
| 收益/风险排名 | [SW_RANK](references/SW_RANK.md) | `sw_rank.py`，其他指数类别可网页补充 |
| PE/PB/股息率估值排行 | [SW_VAL](references/SW_VAL.md) | `sw_valuation.py` |
| 已完成周/月排行、排名反转 | [SW_PRANK](references/SW_PRANK.md) | `sw_period_rank.py`，默认只支持涨跌幅，历史估值字段不补0 |
| 估值历史百分位、指定年数分位 | [SW_QUANTILE](references/SW_QUANTILE.md) | `sw_quantile.py`，区分供应商窗口与指定年数 |
| 成分查询 | [SW_COMP](references/SW_COMP.md) | `sw_comp.py`，先交付可核实的成分名单 |
| 自定义行业群组 | [SW_GRP](references/SW_GRP.md) | `sw_group.py`；其他类别可网页补充 |
| 官方公告、编制说明 | [SW_ANN_LATEST](references/SW_ANN_LATEST.md) | 通过网页检索核实发布机构原文，不执行此类取数脚本 |

[指数代码表](references/index-codes.md) 只用于名称识别，不代表每个代码均有对应数据。不明确的名称或范围用自然语言澄清，可参考 [clarification-patterns](references/clarification-patterns.md)，不依赖特定平台提问工具。

## 参数与执行

脚本使用技能根目录的绝对路径；用户未指定时间时采用脚本默认值。需要自定义计算时阅读 [custom-script-guide](references/custom-script-guide.md)，复用 `datasource`/`sw_common` 和 `indicators`，行情优先复用上述模块，网页补充遵循上方核实规则。

- `--period DAY/WEEK/MONTH`：K线周期；近一周/一月/半年/一年约为 `--days 5/22/125/250`，但技术图应留足指标预热数据。
- `--date YYYYMMDD`：市场全景指定日，脚本定位不晚于该日期的最近交易日。
- `sw_chart.py indicator --start YYYYMMDD --end YYYYMMDD`：自然区间；不与 `--days` 同用。单指数研报使用自身参考中的日期参数。
- `--scope consumer/tmt/cyclical/finance/mfg/defensive`：预设板块；热力/风险可用 `--codes 801030,801080`。dashboard 不支持 `--codes`。
- K线批量每批最多6代码、最多3批并发。单次 CLI 超时 `SW_CLI_TIMEOUT` 默认90秒；遇 `LOCAL_RATE_LIMITED` 停止重复调用，按数据补充流程处理；执行31行业任务应给工具约400秒整轮预算（这是工具超时，不是 westock 参数）。
- `SW_WORKSPACE` 指定工作目录，默认 `./workspace/`；产物在 `.swi/render/`，摘要 `render_files` 返回实际路径。
- `WESTOCK_BIN` 可指定 CLI 路径；运行使用默认 westock 数据源。

## 完整性与计算口径

- 批量封装按 `Data[].Symbol` 分配，核验 `Metadata.ErrorCount`；单代码可返回扁平列表。不能按返回顺序配代码。
- K线按日期升序、去重并校验 OHLC/正收盘价。空结果对缺失代码重试一次，仍缺失则报错；不能输出“完整31行业”的部分结果。
- YTD 至少请求250根日K，使用最新数据年份前一年末的最后交易日收盘作为基准。250根不保证覆盖，缺基准须报错；不以年内第一条数据或0替代。
- 不将不足一年的样本标为“一年收益”。只按实际样本计算窗口年化/波动等指标，所需历史不足的1/3/5年字段保留缺失。
- 多指数图表/回归/相关性/组合按共同交易日期对齐，不按行号对齐。共同样本不足或最新日期不一致须说明或报错。
- 财务字段缺失返回 `null`，榜单按该指标的有效行排序；不把缺失值排成“最低估值”。

## 产物交付

- 脚本 stdout 最后一行是 Agent 可读 JSON 摘要；失败时也检查 stderr 和退出码。仅 `status=ok` 或已明确说明的 `degraded` 可用于交付。出现错误不得引用上一次运行残留文件。
- 图表/研报请求必须展示 `render_files` 对应 HTML，使用当前平台可用的预览/文件展示工具；没有展示工具时提供可点击文件链接。Markdown 表格可直接放回复中。保留原 ECharts/报告版式，不新增绘图库依赖。
- 当前平台提供 `present_files` 时，必须调用 `present_files` 展示产物。
- 当前平台没有 `present_files` 时，必须为 `render_files` 中的每个产物输出符合平台格式要求的 `media_info`，不只打印本地文件路径。
- 回复先给结论和真实截止日期，再给必要数据及图表链接。使用摘要中的数据；未覆盖项按“数据补充与最终回复”描述分析范围，不展示内部原因，也不编造分析或指标。脚本没有生成分析结论时，基于已核实的数据组织客观说明。

### Python 生成图片的展示

当模型需要 present（展示）Python 脚本生成的图片时，必须在最终回复正文后输出指向该图片的 `<media_info>` 标签；即使已经调用 `present_files`，也需要输出对应标签。若脚本或展示工具返回了 `media_info`，原样使用.