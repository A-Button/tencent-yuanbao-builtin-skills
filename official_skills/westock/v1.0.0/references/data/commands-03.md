# WeStock Data - 详细命令用法 · 分册 03

[本手册索引](commands.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

### 外汇行情/K线/分时（复用 quote / kline / minute）

```bash
westock quote fxUSDJPY                         # 美元日元即期汇率
westock quote fxCNH,fxEURUSD,fxDINIW           # 批量（离岸人民币/欧元美元/美元指数）
westock kline fxCNH --period day --limit 30    # 离岸人民币日K（day/week/month/season/year）
westock minute fxCNH                           # 离岸人民币当日分时

```

> ⚠️ **外汇限制**：外汇**仅提供当日分时**，`westock minute` 的 `--days 5` 对外汇无效（数据源不支持五日分时，参数会被忽略并返回当日数据）。外汇**不支持复权**（`--fq` 对外汇无效）。相关新闻直接使用 `web_search` 检索并核验原文。品种代码请先用 `westock search --type forex` 或 `westock forex list` 获取，避免猜测。

## 十八、债券（可转债 / 可交换债）

> 沪深可转债/可交换债。标准代码：沪市 `sh11xxxx`（110/111/113 可转债、118 科创板可转债）、`sh13xxxx`（132 可交换债）；深市 `sz12xxxx`（123/127/128 可转债、120 可交换债）。
> 行情/分时/K线沿用 sh/sz 前缀，直接复用个股通道，无需特殊命令。

### 可转债行情/分时/K线（复用 quote / minute / kline）

```bash
westock quote sh113052                         # 可转债行情（价格/涨跌/涨跌停价 + 转债维度，竖排展示）
westock quote sh113052,sh113044                # 批量
westock minute sh113052                        # 当日分时
westock kline sh113052 --period day --limit 30 # 可转债K线（日/周/月/季/年及分钟K均支持）

```

> 可转债行情在通用价格/成交字段之外，额外返回**转债维度**：转股价值、纯债价值、转股/纯债溢价率、双低、总规模/剩余规模、评级、期限/剩余期限/到期日、到期收益率、是否转股、转股价/转股起始日、到期赎回价/强赎价/强赎触发价、回售触发价/回售起始日、正股 PB/正股代码。单只查询时以竖排「项目/内容」表展示，规模换算为亿元、日期规整为 `YYYY-MM-DD`。

### 可转债详情（bond）

```bash
westock bond sh113052                   # 核心要素：发行/规模/评级/期限利率/转股/赎回回售/关键日期/利率变动/现金流明细
westock bond sh113052,sz123245          # 批量查询

```

> ⚠️ **可转债说明**：行情接口**不返回债券简称**（`westock quote` 的 `name` 为空），可借 `bond` 的发行人/正股代码识别标的。可交换债及临近到期的老券可能缺失部分转股相关（`Kzz_*`）字段。规模金额已统一换算为「亿元」，日期已规整为 `YYYY-MM-DD`。

