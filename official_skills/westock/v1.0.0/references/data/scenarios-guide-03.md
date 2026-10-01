# WeStock Data - 常见分析场景详解 · 分册 03

[本手册索引](scenarios-guide.md) · [技能入口](../../SKILL.md)

> 仅查当前需要的章节；示例和分析模板不增加用户条件。遵循入口的停止规则，默认文字回答，仅明确要求文件时创建文件。

### 12.13 居民收入与消费分析（内需根基）

```
用户："老百姓收入涨了吗？"/"消费为什么疲软？"

AI 步骤：
1. 查询可支配收入：westock macro indicator cn_disposable_income --year 2025
2. 查询消费指标：westock macro indicator cn_consumption --year 2025
3. 关注核心字段：
   - PERCAP_DISP_INC_YTD_YOY（人均可支配收入累计同比）
   - PERCAP_DISP_INC_REAL_YTD_YOY（实际累计同比，剔除通胀）
   - PERCAP_DISP_INC_MED_YTD_YOY（中位数同比，反映分配公平度）
   - 收入结构：工资（WAGE）/ 经营（BIZ）/ 财产（PROP）/ 转移（TRSF）
   - PERCAP_CONS_EXP_YTD_YOY（人均消费支出同比）
   - 消费分项：食品（FOOD）/ 居住（HOUS）/ 交通通信（COMM）/ 教育文化娱乐（EDUC）/ 医疗（HLTH）
   - CONSUMP_CUR_YOY（社零当期同比）+ 各品类（汽车/化妆品/金银珠宝/家电...）
4. 专业研判：
   - 名义收入增速 > 实际收入增速差距 = 通胀侵蚀
   - 中位数增速 < 平均数增速 → 收入分化加剧
   - 工资性收入主导 → 就业稳定；财产性收入跌 → 资产价格压力
   - 消费/收入弹性：消费增速远低于收入 → 预防性储蓄上升（消费意愿弱）
   - 必选消费（食品/医疗）韧性 vs 可选消费（化妆品/金银珠宝）疲软 → 消费降级
5. 输出消费景气评估 + 受益板块（必选 vs 可选 vs 服务消费）
```

### 12.14 就业市场（含百度搜索指数高频）

```
用户："就业形势怎么样？"/"年轻人失业率高吗？"

AI 步骤：
1. 查询就业指标：westock macro indicator cn_employment --year 2025
2. 关注核心字段：
   - EMPLOY_UNEMP（城镇调查失业率）+ 同比 EMPLOY_UNEMP_YOY
   - 分年龄：EMPLOY_UNEMP_16_24（青年）/ 25_29 / 30_59
   - 分户籍：EMPLOY_UNEMP_MIGR（外来）/ EMPLOY_UNEMP_RURAL_MIGR（农民工）
   - EMPLOY_AVG_WORKHRS（周工作时长，反映用工密度）
   - EMPLOY_NEW_EMP_YTD_YOY（新增就业累计同比）
   - **高频先行指标**：百度搜索指数 EMPLOY_BDI_JOBSEEK（找工作）/ BDI_RECRUIT（招聘）/ BDI_UNEMP（失业）
3. 专业研判：
   - 16-24 岁失业率 > 整体失业率 2 倍 → 结构性失业（青年就业难）
   - 工作时长 < 47 小时 → 用工不足，警惕裁员
   - 新增就业累计同比转负 → 就业市场恶化
   - 百度搜索"找工作"指数大幅上升、"招聘"指数下降 → 求职难度加大（高频领先信号）
   - 农民工失业率 > 户籍失业率 → 灵活就业承压
4. 政策含义：
   - 失业率破阈值（5.5%/年青）→ 稳就业政策加码概率上升
   - 就业恶化 + 消费疲软 → 政策刺激窗口
5. 输出就业景气评估 + 政策预期
```

### 12.15 宏观日历驱动的事件预案

```
用户："最近有什么重要数据要公布？"/"下周经济数据怎么预期？"

AI 步骤：
1. 查询未来宏观日历：westock macro indicator cn_calendar_future --date <今天>
2. 查询历史宏观日历（参考过往同类事件反应）：westock macro indicator cn_calendar_hist --year 2025
3. 查询机构预测：westock macro indicator cn_forecast --year 2025
4. 关注核心字段：
   - calendar_future：EventDate / EventType / EventDesc / Importance / ForecastValue / PreviousValue
   - forecast：FORECAST_GDP_FC_YOY / FORECAST_CPI_FC_YOY / FORECAST_PMI_FC / FORECAST_M2_FC_YOY 等机构一致预期
5. 专业研判（事件驱动框架）：
   - **数据公布前**：当前实际值 vs 机构预测值 → 预期差大小
   - **重要程度筛选**：Importance 高的事件（PMI / CPI / 社融 / 非农等）→ 重点关注
   - **事件分类**：
     - 经济数据（PMI/CPI/PPI/工业数据）→ 影响周期股
     - 央行操作（MLF/LPR/降准）→ 影响金融股、债市
     - 财政数据（财政收支/专项债）→ 影响基建链
   - **历史反应**：用 calendar_hist 找最近 3-5 次同类事件公布后市场反应（指数涨跌、板块轮动）
6. 输出事件清单 + 预期差判断 + 板块预案：
   - 公布前布局：预测值好于历史 → 提前布局相关板块
   - 公布后策略：实际值大幅偏离预测（>1 标准差）→ 短期波动加大，等待方向确认
```

### 12.16 中国专项指标（LPR / 财新 PMI / 装机容量）

```
用户："LPR 最近调整了吗？"/"财新 PMI 最新值？"/"风电光伏装机什么节奏？"

AI 步骤：
1. 一次性拉三个专项：westock macro indicator cn_lpr cn_caixin_pmi cn_installed_capacity --date <今天>
2. 关注：
   - cn_lpr：1Y/5Y LPR 当日值 vs 前值（看 ActualValue/FormerValue 列）
   - cn_caixin_pmi：财新制造业/服务业 PMI（与官方 PMI 互证；财新更偏中小企业）
   - cn_installed_capacity：发电装机容量（火电/水电/核电/风电/光伏 装机）
3. 与中国专项指标的"高频补充"价值：
   - LPR 是货币政策直接指标（实时影响利率敏感板块：地产/银行/消费）
   - 财新 PMI 与官方 PMI 分歧时往往揭示"中小企业 vs 大型央企"景气度差异
   - 装机容量映射新能源行业景气与"双碳"政策落地节奏
```

### 12.17 美股 / 港股 / 日本 / 欧元区 主题宏观（事件日历型）

```
用户："美国非农数据最新预期？"/"美联储加息节奏？"/"日本央行政策动向？"/"欧元区通胀压力？"

AI 步骤：
1. 拉美股主要主题：westock macro indicator us_eco_growth us_inflation us_monetary --date <今天> --limit 5
   - 29 个主题：us_employment / us_eco_growth / ...（共 29 个，24 个按日期 + 5 个按年）
2. 单主题精查：
   - westock macro indicator us_employment --date <今天>     # 美国就业
   - westock macro indicator us_inflation --date <今天>       # 美国通胀（CPI/PPI/核心 CPI）
   - westock macro indicator us_monetary --date <今天>        # 美联储利率/资产负债表
   - westock macro indicator jp_monetary --date <今天>        # 日本央行
   - westock macro indicator eu_inflation --date <今天>       # 欧元区通胀
3. 关注字段（统一 schema）：
   - IndicatorName：指标名（如"美国 5 月非农就业人口"）
   - OccurDate / OccurTime：发布日期与时间
   - ActualValue / ForecastValue / FormerValue：实际值/市场预测/前值
4. 专业研判：
   - 数据公布前：观察预测值（市场一致预期）
   - 公布后：实际 vs 预测 → 预期差驱动美元/美债/A 股短期联动
   - 美联储/ECB/BoJ 政策窗口前后关注 us_monetary/eu_monetary/jp_monetary 主题
```

### 12.18 海外预期日历（按地区 iso3，36 个地区）

```
用户："看看中国财经日历明年的关键事件"/"美国今年都公布了哪些重要数据？"

AI 步骤：
1. 列地区代码：westock macro expect list（共 36 个地区）
2. 单地区按年查：
   - westock macro expect --area chn --year 2025         # 中国
   - westock macro expect --area usa --year 2025         # 美国
   - westock macro expect --area jpn --year 2025         # 日本
3. 区间查询（多年趋势）：westock macro expect --area usa --start 2023 --end 2025
4. 关注字段（比 us_/jp_ 等主题型多一列 Importance）：
   - Importance：1=低 / 2=中 / 3=高（用于筛选重要事件）
5. 与 macro indicator 主题型差异：
   - 主题型：按 region 分主题切片（就业/通胀/货币...），适合"看美国通胀近期"
   - 海外预期：按地区分单地区全套日历，适合"看某地区某年所有重要事件"
```

### 12.19 美联储降息预期跟踪（投资视角）

```
用户："美联储最近会不会降息？"/"市场对下次 FOMC 会议的利率预期？"

AI 步骤：
1. 查询美联储利率历史 + FFR 预期：westock macro indicator us_monetary --date <今天>
   - 联邦基金利率目标上下限（当前/前值）
   - FFR 预期-当前年度 / 后面第 1/2/3 年 / 长期（点阵图含义）
2. 查询未来 FOMC 会议市场一致预期：westock macro expect --area usa --year <当年>
   - 筛 IndicatorName 含"联邦基金利率"的事件，看 ForecastValue
3. 三栏对比识别预期偏移：ActualValue（实际）vs ForecastValue（预测）vs FormerValue（前值）
4. 板块映射：
   - 鸽派偏移（降息空间打开）→ 利好成长股（科技/生科）/ 长久期资产（地产 REITs/公用）/ 黄金
   - 鹰派偏移（降息推迟）→ 利好金融股（净息差扩大）/ 价值股
5. 配合 us_inflation 综合判断：通胀粘性 → 降息空间被压缩
```

### 12.20 美国通胀压力多维评估（投资视角）

```
用户："美国通胀压力怎么样？CPI/PCE/PPI 最新数据如何？长期通胀预期上行了吗？"

AI 步骤：
1. 查询美国通胀全套：westock macro indicator us_inflation --date <今天>
2. 三层通胀拆解：
   - 当期通胀：CPI 月率/年率、核心 CPI、PCE 月率/年率、核心 PCE 月率/年率（美联储最关注）
   - 上游传导：PPI 月率（超预期跳升 = 上游成本传导风险）、核心 PPI
   - 通胀预期：纽约联储 1 年 / 密歇根大学 1 年 / 密歇根大学 5 年（脱离 2% 锚定 = 警讯）
3. 关键判断逻辑：
   - 核心 PCE 回落 + 通胀预期稳定 → 降息支撑
   - PPI 跳升 + 长期通胀预期上行（>3.5%） → 再通胀风险
4. 板块映射：
   - 通胀粘性高 → 价值股 / 能源 / 必选消费 / 银行
   - 通胀回落 → 长久期成长股 / 利率敏感板块
5. 配合 macro expect --area usa 看下一次 CPI/PPI 公布预期
```

### 12.21 中美宏观对比（跨市场配置）

```
用户："对比一下中美宏观经济基本面"/"中美周期错位还是共振？"

AI 步骤：
1. 并行查询：
   - 美股：westock macro indicator us_eco_growth us_inflation us_monetary --date <今天> --limit 5（每指标仅最近 5 条）
   - 中国：westock macro indicator cn_core --date <今天>（一键 7 大核心）
   - 补充：westock macro indicator cn_gdp cn_cpi_ppi cn_pmi --year <当年>
2. 三维度对比：
   - 增长：us_eco_growth（GDP/工厂订单/营建）vs cn_gdp + cn_pmi
   - 通胀：us_inflation（PCE/CPI/PPI）vs cn_cpi_ppi（CPI/PPI/核心 CPI）
   - 货币：us_monetary（联邦基金利率）vs cn_mlf + cn_fundcost（MLF/SHIBOR/LPR）
3. 周期识别：
   - 美强中弱（美 PMI>50 + 中 PMI<50）→ 美元强势 / 北向流出
   - 双弱 → 全球衰退风险，避险（美债/黄金/日元）
   - 中强美弱 → 人民币升值 / 北向回流 / 新兴市场跑赢
4. 跨市场资产含义：
   - 人民币汇率（USD/CNH）
   - 北向资金净流入趋势
   - A 股相对美股估值（恒生科技 PE vs 纳指 PE / EprPct10Y）
```

### 12.22 港股宏观环境（联系汇率制度下的双重驱动）

```
用户："港股的宏观环境怎么样？"/"香港经济和外储情况？"

AI 步骤：
1. 拉港股全部 4 个主题：westock macro indicator hk_eco_growth hk_export_reserve hk_monetary hk_others --date <今天>
   - hk_eco_growth（GDP/零售）/ hk_export_reserve（贸易/外储）/ hk_monetary（利率）/ hk_others
2. 联系汇率制度核心逻辑：
   - 港币挂钩美元（7.75-7.85 区间），HKMA 货币政策被动跟随美联储
   - 因此 hk_monetary（HIBOR/贴现窗）通常与 us_monetary 联动
3. 双重驱动：
   - 流动性端：受美联储影响（美降息 → 港股流动性宽松 → 估值修复）
   - 基本面端：受中国大陆影响（中国 PMI/出口 → 港股盈利）
4. 推荐组合查询：
   - westock macro indicator us_monetary --date <今天>（看美联储路径）
   - westock macro indicator cn_pmi --start <去年> --end <当年>（看中国基本面）
5. 板块映射：
   - 美降息 + 中复苏 → 港股双击（互联网科技/地产/银行）
   - 美鹰派 + 中弱 → 港股双杀（避险）
```

### 12.23 全球三大央行流动性对比

```
用户："全球主要央行流动性环境怎么样？"/"美日欧政策路径有什么差异？"

AI 步骤：
1. 并行调用三大央行政策：
   - westock macro indicator us_monetary --date <今天>（联邦基金利率 ~3.5-3.75%）
   - westock macro indicator jp_monetary --date <今天>（日本央行政策利率 ~0.5%）
   - westock macro indicator eu_monetary --date <今天>（ECB 政策利率 ~3-3.5%）
2. 政策方向识别：加息 / 持平 / 降息（看 ActualValue vs FormerValue）
3. 政策分化场景：
   - 美降日加：美日利差收窄 → 日元升值 → Carry trade 平仓 → 全球流动性回流日本
   - 美降欧降：协同宽松 → 全球流动性整体宽松 → 利好风险资产
   - 美鹰其它鸽：美元独强 → 新兴市场承压
4. 跨资产含义：
   - 美元指数（DXY）：三大央行利差驱动
   - 黄金：实际利率（名义利率 - 通胀预期）反向
   - 新兴市场流动性：美元强势→流出，弱势→流入
5. 配合 expect 看未来政策窗口：
   - westock macro expect --area usa（FOMC）
   - westock macro expect --area jpn（BoJ）
   - westock macro expect --area deu（代表欧元区，ECB）
```

---

## 十五、期货（外盘商品/金融期货 + 港股股指期货）

> 命令：`westock futures detail` + `westock search --type futures` + `westock quote`（支持期货代码）

### 13.1 期货行情查询（关键词→代码→行情）

```
用户："现在国际金价多少？"

AI 步骤：
1. 关键词找代码：westock search 黄金 --type futures → fuGC（COMEX黄金）
2. 查询行情：westock quote fuGC
3. 解析最新价、涨跌幅、货币单位（USD）
4. 说明为延时行情（isDelayed），并给出生成时间
```

### 13.2 期货合约资料查询

```
用户："WTI原油期货的合约规格是怎样的？"

AI 步骤：
1. 关键词找代码：westock search 原油 --type futures → fuCL（WTI原油，NYMEX）
2. 查询合约资料：westock futures detail fuCL
3. 解析交易所、合约规模、货币币种、最小变动单位、交易时间、所在时区
4. 输出合约规格说明
```

---

## 十六、外汇（离岸人民币/主要货币对/美元指数）

> 命令：`westock forex list` + `westock search --type forex` + `westock quote`/`westock kline`/`westock minute`（支持外汇代码 `fx*`）

### 14.1 外汇行情查询（关键词→代码→行情）

```
用户："离岸人民币现在多少？"

AI 步骤：
1. 关键词找代码：westock search 离岸 --type forex → fxCNH（离岸人民币）
2. 查询行情：westock quote fxCNH
3. 解析最新价、涨跌幅
4. 给出生成时间
```

### 14.2 外汇走势查询（K线/分时）

```
用户："美元日元近一个月走势如何？"

AI 步骤：
1. 关键词找代码：westock search 美元日元 --type forex → fxUSDJPY
2. 查询日K：westock kline fxUSDJPY --period day --limit 30
3. 解析区间高低点、涨跌幅，描述趋势
4. 提示：外汇仅提供当日分时（minute），不支持五日分时
```

---

## 十七、债券（可转债 / 可交换债）

> 命令：`westock quote`/`westock minute`/`westock kline`（支持可转债代码 沪 `sh11xxxx`/`sh13xxxx`、深 `sz12xxxx`）+ `bond`（发行要素/条款/现金流）

### 15.1 可转债行情查询（价格 + 转债维度）

```
用户："兴业转债现在行情怎么样？转股价值和溢价率高不高？"

AI 步骤：
1. 查询行情：westock quote sh113052
   （可转债走专属字段集，除价格/成交外额外返回转债维度，单只竖排「项目/内容」表展示）
2. 解析通用字段：最新价、涨跌幅、成交额
3. 解析转债维度：转股价值（bond_equity_value）、转股溢价率（bond_equity_premium）、
   双低（bond_double_low）、转股价（bond_convert_price）、正股代码（bond_stock_code）
4. 结合溢价率高低、双低值给出客观描述（不做投资建议）
5. 提示：行情接口不返回债券简称（name 为空），如需发行人/评级/条款用 bond
```

### 15.2 可转债基本面与条款（行情 + 详情联动）

```
用户："兴业转债的规模、到期日和赎回回售条款是什么？"

AI 步骤：
1. 行情快照看规模/期限：westock quote sh113052
   → 总规模（bond_total_size）、剩余规模（bond_undue_size）、到期日（bond_due_date）、
     到期收益率（bond_ytm）、强赎触发价/回售触发价
2. 详情看完整发行要素与条款：westock bond sh113052
   → 发行人、票面利率、期限、利率变动/现金流/赎回回售明细（默认输出）
3. 综合行情与详情，客观说明规模、到期安排与赎回/回售触发条件
```

---

## 复合分析工作流

> 以下是可选的原子命令组合，不是每次任务的必经流程。优先采用[短工作流](../workflows.md)，程序消费JSON时使用[解析分支](../parsing.md)；不改CLI、不安装新解析工具。
> 1. **批量与覆盖**：支持批量时一次多代码，按市场和模式限制分组；核对实际返回标的。日历只取目标窗口，不默认全年。
> 2. **并行与缓存**：无依赖且必要的请求同轮执行，同一结果本轮复用；不以并行为理由无限扩大日期组数。
> 3. **范围**：开放探索可以先取20–30条；明确要求全量时先验证范围与完整性，不能用Top N代替完整要求。
> 4. **早停**：同一缺口最多一次有依据的修正；能力不足如实说明，不无依据扩池。必要数据已足够即回答，不继续增加研究维度。
>
> 使用样本时明确注明样本边界；默认文字回答，只有用户要求文件才进入文件交付流程。

### 16.1 事件后收益统计（如"回购披露后普遍表现"）

**候选池来源（技能内编排）**：
- 用户**已给定股票池** → 从第 2 步开始。
- **开放式筛选** → 先用 `westock screen event` 筛出并限量，再批量查详情。事件类型的内置窗口必须满足任务；最近一个月候选池不能代表全年全部回购事件。

```
调用链（研究近期回购候选的 2026 年披露记录，按披露日期分组控制调用量）：
1. 出池并限量（仅开放筛选时）：
   westock screen event --type buyback --limit 30
2. 批量补披露日（data，1 次）：
   westock buyback code1,code2,...,code30 --start 2026-01-01 --end 2026-12-31
3. 一次拿全年交易日（data，1 次）：
   westock trade-calendar --year 2026 --trading-only
4. 按披露日分组批量查前复权收盘（data，同一披露日一批，可并行）：
   westock quote codeA,codeB --date <披露日基准交易日>
   westock quote codeC     --date <下一交易日>
5. 本地聚合统计：中位数 / 上涨占比 / 分布
```

**收益口径红线**：
- 基准价 = **披露日当日或此前最近交易日**收盘价；收益 = `(下一交易日收盘 / 基准收盘 − 1)`。
- 用 `quote --date` 取值（指定日期已自动取**前复权**价，`change/change_percent` 亦按前复权重算）；**禁止**用下一交易日 quote 的 `change_percent` 直接代替上述口径。
- **禁止**用自然日/工作日近似替代 `trade-calendar` 定交易日。
- 回购事件取**披露日**（公告日），不用回购实施区间的 `StartDate`/`EndDate`。

### 16.2 多年 ROE 验证（如"连续 5 年 ROE≥15%"）

**候选池来源**：开放筛选先用 `westock screen condition` 初筛；已给定池直接从第 2 步开始，全部在本技能内完成。

```
调用链：
1. 初筛并限量（仅开放筛选时）：
   westock screen condition --expression 'intersect([ROETTM >= 15, PE_TTM > 0])' --limit 20
2. 批量取财报序列：
   westock finance code1,...,code20 --fields all --limit 24
3. 按财年、报表类型和披露字段逐只验证年报 ROE，按连续/最低/平均 N 年判定。
```

**口径红线**：
- 单期 `ROETTM` 不等于多年连续 ROE；上述初筛还会遗漏当前 TTM 未达标但历史年报达标的股票，不能代表全市场完整结果。
- 直读 `ROEWeighted` 等实际披露字段；禁止用净利润除期末权益替代加权 ROE。
- 使用 `--fields all` 获取必要字段；`--limit 24` 不能保证覆盖所需全部年报，按返回财年核验，缺失则注明未验证。非自然年财年不能仅按日期后缀识别。
- 若仅做单期初筛而未验证年报，明确标注「ROETTM 单期初筛，未验证多年连续达标」。

### 16.3 板块 / 指数成份对比（交集 / 差集 / 重合占比）

在本技能内查询成份并做集合比较；先确认两边是否完整返回，截断结果只能说明样本重合度。

```
调用链（2 次查询，可并行）：
1. 代码类型判断：
   pt* / sw*_* → 板块，用 sector constituent
   sh/sz 6 位、cs*、hk 字母开头 → 指数，用 index constituent
2. 并行取两边成份（--raw 便于本地做集合运算）：
   westock sector constituent pt02003578 --raw
   westock index  constituent sh000300   --raw
3. 本地对成份代码集合求：交集 / 仅 A / 仅 B / 重合占比（占 A、占 B 各一个百分比）
```

> 只有板块/指数名称时：先 `westock search <关键词> --type sector`（或 `--type index`）取 code；多个关键词可**一轮并行** search，合并去重后再取 code。

---

**记住**：westock 是数据查询工具，AI 负责数据分析和洞察！