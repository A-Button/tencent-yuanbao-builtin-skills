# 排盘输入与能力边界

所有新排盘使用 [chart-flow.md](chart-flow.md) 的简短请求入口，本文件仅用于维护或诊断脚本内部接口，正常排盘无需读取。

本文件只定义 `ready_for_chart` 之后的标准化引擎输入，不定义问答轮次，也不要求重新读取会话状态。不得把原始城市文本直接喂给引擎，也不得把内部采样时刻冒充出生时间。

## 完整单盘输入 JSON

```json
{
  "calendar": "gregorian",
  "local_datetime": "1992-09-15T14:30:00",
  "timezone": "Asia/Shanghai",
  "fold": 0,
  "location": {
    "label": "杭州，中国",
    "source": "builtin-city-timezone-table",
    "precision": "city"
  },
  "time_precision": {
    "kind": "exact",
    "minutes": 0
  },
  "day_boundary_policy": "civil-midnight",
  "solar_time_policy": "civil"
 }
```

当前民用时八字和西占地心行星不使用城市中心坐标；`location.latitude` 与 `location.longitude` 因此成对选填。启用上升等实际依赖坐标的能力时，才把坐标变成该能力的硬输入，其缺失不阻塞已可计算的其他项目。准确时间的西占优先复用宿主坐标，或由流水线为内置高频城市补充 `city_coordinates.zh-CN.json` 的 GeoNames 城市参考坐标；区域级标签不映射为某个城市。原来的时区解析、同名和特殊钟制处理保持不变。

农历八字把 `calendar` 改为 `lunar`，使用 `lunar_datetime`，并显式提供 `lunar_is_leap_month`。西洋星盘只接受公历。

`gender_for_bazi` 只用于传统顺逆排运，可接受 `male|female|男|女`，不是基础四柱的必要字段。用户选择不清楚或保密时不把状态值传给引擎，也不再追问。精确时间基础受支持但顺逆未定时，八字深报投影两条匿名 `option_a|option_b` 条件分支，不暴露性别、方向或判定依据；普通盘面仍可省略大运。

## 出生时段范围输入

八字、西占、组合盘都支持两种范围输入：`birth_date` 加 `birth_time_branch`（十二地支之一）及 `time_precision={"kind":"shichen","minutes":null}`；或 `birth_date` 加 `time_ranges=[{"start":"10:00","end":"12:00"}]` 及 `time_precision={"kind":"range","minutes":null}`。对话入口仍只填写原始 `birth_time`，由脚本解析上述结构；不要求用户填写技术字段。

边界采用秒级、左闭右开，不代表选定出生秒数。明确钟表范围支持分钟或秒、上午／下午修饰、`-／–／至／到` 分隔；结束早于开始时标明次日，最多 24 小时，跨午夜的规范字段增加 `end_day_offset=1`。同一民用日期的子时固定为 `00:00–01:00` 与 `23:00–24:00` 两段，不选取中点。边界相同、格式无效或无法消歧时要求纠正，不静默扩大为全天；没有明确边界的“大约／左右”仍按日期级。

流水线分别调用 `bazi_time_range.py` 与 `western_time_range.py`，均返回 `precision=time-range`、`stable` 与 `possible`。八字四柱均不变时另提供完整 `pillars` 和确定性 `details`；不补造分钟，精确起运不可用，报告显示 `luck_cycle_focus.reason=time_range`。西占稳定行星在 `chart.stable.planet_signs`，稳定上升在 `chart.stable.ascendant.sign`；跨界项才进入 `chart.possible.planet_signs` 或 `chart.possible.ascendant`。范围报告使用 `time_range_stable_facts`，只引用已确定字段。

## 日期级初盘输入 JSON

出生年月日和城市解析完成，但时间为大概、范围、不清楚或保密时，使用：

```json
{
  "calendar": "gregorian",
  "birth_date": "1992-09-15",
  "timezone": "Asia/Shanghai",
  "location": {
    "label": "杭州，中国",
    "source": "builtin-city-timezone-table",
    "precision": "city"
  },
  "time_precision": {
    "kind": "unknown",
    "minutes": null
  },
  "day_boundary_policy": "civil-midnight",
  "solar_time_policy": "civil"
}
```

`time_precision.kind` 可为 `approximate|range|unknown|withheld|unspecified`。日期级脚本在当地日期内执行确定性采样：

交互层的 `time_accuracy=null` 不直接进入引擎；只有 `time_prompted=true` 表明已给过一次填写机会时，流水线才把该留空状态确定性投影为 `time_precision.kind=unspecified`。用户明确选择“不清楚”仍保存为 `unknown`，不得混淆两种语义。`approximate` 仍按整日采样。日期级脚本兼容旧 `range` 数据并明确标注未缩窄范围，但新排盘中明确起止时间必须走 `time-range`，不可调用旧日期级入口丢弃边界。

- 所有样本一致的字段写入 `chart.stable`，可用于后续解释；
- 样本之间变化的值写入 `chart.possible`，只用于说明范围；
- 内部样本时刻不写入用户摘要，也不能作为出生时间进入报告；
- 后续获得准确时间时使用新的隔离运行目录重新执行完整单盘；当前生产编排器不在同一状态上手工续接 revision。

## 八字能力

- 使用随包 `lunar-python 1.4.8`。
- 生成节令四柱、干支、藏干、十神、长生阶段、表层与藏干五行计数、明确存在的干支关系、纳音和前后节令。
- 提供 `gender_for_bazi` 时，按随包引擎 `sect=1` 计算起运和八步大运，并记录顺逆、起运日期和起止年龄；不生成随机评分或具体事件。
- 原始八字 JSON 保留完整大运供确定性盘面展示；生成式解释不得直接读取该列表自行挑选。八字深报默认在 `schema_version=1.0.0` 的 `analysis-chart.json` 中由脚本投影 `chart.details.luck_cycle_focus`，该对象的 `status=available|conditional|unavailable`；普通结论或分析只在用户明确问当前大运时才按需投影。
- `available` 包含 `cycle`、`position_band` 和 `as_of_local_date`；`conditional` 包含两个匿名 `branches`，每个 `id` 只能是 `option_a|option_b`，并各自包含 `cycle` 与 `position_band`；`unavailable` 仅包含脚本固定 `reason`，不接受模型补值。
- 当前随包节令实现只在原始盘面的 `resolved_utc_offset=+08:00` 时启用深报大运投影；其他 offset 返回 `unsupported_time_basis` 并显示固定边界，不把北京时基准直接套到其他地区。
- 默认民用当地时、午夜换日；不做真太阳时，不自动生成流年解读。
- 日期级初盘展示整日稳定的年、月、日柱及日主；若当天跨节令或其他边界，相应柱转入 `possible`。时柱和大运起点始终省略；进入八字深报时投影 `status=unavailable` 及日期级固定原因，不终止其余章节。

## 西洋能力

- 使用随包 Astronomy Engine `2.1.19`。
- 生成热带黄道十个天体、星座、度数和主要相位。
- 准确时间且地点坐标可靠时，由同一随包引擎的 ECT → EQD → 地平坐标旋转，求黄道与东方几何地平线的交点，生成 `chart.ascendant.sign|longitude_deg|degree_in_sign|frame`。不使用大气折射，不计算宫位；当前上升验收范围为南北纬 65 度以内。
- `chart.ascendant_status` 为 `available|variable|requires_coordinates|unsupported_latitude`；稳定范围上升也为 `available`，真实跨界才为 `variable`，其余为资料／能力缺口。不稳定或不可用时 `chart.ascendant=null`，不影响其他天体。日期级始终不计算上升。
- 当前不生成宫位、小行星、行运或太阳回归。
- 日期级初盘只展示整日稳定的行星星座；跨星座的天体列出可能星座。精确度数和时间敏感相位省略。

## 时间边界

- 完整单盘只接受 `time_precision.kind=exact` 且 `minutes=0`；三个模式的 `shichen` 与明确 `range` 均进入范围核验，真正无界的模糊／未知输入才进入日期级，不作为错误。
- 1949 年前的完整单盘需要宿主取得有来源的历史 UTC offset；缺失时说明能力边界，不把技术格式转嫁给普通用户。
- 新疆出生要确认出生记录使用北京时间还是新疆时间。
- 夏令时回拨导致同一当地时间出现两次时，用 `fold=0|1` 明确选择。
- 上述具体时刻边界只阻塞依赖该时刻的完整单盘；不应删除已经可确定的日期级事实。历史 offset 无法取得时，明确省略依赖 UTC 的西洋日期级字段，不要求普通用户填写技术格式。

## 解释边界

- 五行计数只是组成事实，不能单独决定日主强弱、格局或喜忌。
- 天干合、地支合冲刑害只表示关系在原局中出现，不自动等于合化、吉凶或现实事件。
- 强弱、格局和喜忌按 `bazi-judgment.md` 综合月令、根气、生扶耗泄与结构关系。普通分析直接保留少量有区分度的发现；只有深度报告进入 `report-hypotheses.md` 的候选校验链路。
- 大运是传统排盘周期，不是事业、情感、财富或健康评分。
- 顺逆未定的 `option_a|option_b` 只是条件分支；不得选边、按用户反馈倒推、暴露性别或方向依据，也不得将其叠加成一条预测。
- 固定大运模块只看当前大运；用户没有另行明确请求时，不增加流年或流月。
- 日期级报告只能引用 `chart.stable`；`chart.possible` 中的值必须保留为范围，不能挑选最符合用户反馈的一项写成命中。

## 盘面呈现与盘外解释

`render_chart_html.py` 的八字部分只展示确定性排盘事实，不生成字段解释、强弱、格局、喜忌或现实映射。HTML 保留四柱、十神、藏干、十二长生、五行计数、节令和按需生成的大运；纳音、显式干支关系和重复拆写的天干地支只保留在 JSON，并可进入去身份化分析。日期级时柱候选过多时，页面只显示“待定”和候选数量，不把全部候选塞入主卡。

`chart_pipeline.py` 按 `request.artifact` 决定是否准备盘外解释上下文：`chart|null|report` 的首屏快路径不写分析盘，响应和 manifest 的 `artifacts.analysis_charts` 为空；只有用户明确请求 `conclusion|analysis` 时，才在同次原子提交中为每个体系写出 `analysis-<system>.json`。任何情况下都先展示 `chart.html`；普通排盘不自动调用模型，也不输出“命盘速览”或大运解读，但展示成功后可以按交互契约提供一次可跳过的深度报告主题多选。显式结论或分析只读取对应的 `analysis_charts`；用户明确请求报告或在盘后选择主题时，由 `report_pipeline.py prepare` 准备自己的去身份化输入和固定大运上下文，并复用两阶段模型调用。旧盘、导入盘或明确要求当前大运时才单独运行 `prepare_analysis_chart.py`。日期级八字分析盘不包含候选干支值，只保留稳定事实和各变量柱的候选数量；深报的大运模块改用 `status=unavailable` 的固定边界。去身份化准备失败时仍交付已验证 HTML，不回读原始出生资料临场补写，也不把内部失败转成用户问题。

西占首屏由 `western_profile.py` 索引 `western_profiles.json`，上方结构化展示太阳、上升、月亮、金星、水星五项及短注，下方只展开太阳、上升、月亮三段预置解释，详见 [western-presentation.md](western-presentation.md)。日期级只读取 `chart.stable.planet_signs`，候选保留并列范围且不分配正文。原 `chart_guidance.py` 仅留作离线诊断。原始 JSON 保留十天体和相位供另行明确的技术分析；深报则通过 `--western-five` 只投影五项的已确定星座，不含候选值、度数或相位，也不含地点坐标。组合盘中八字解释仍放在 HTML 外；脚本不做跨体系综合结论。

## 出生时段范围实现与维护


脚本把丑时作为当地 `01:00 ≤ 时间 < 03:00` 的范围，按区间端点与节气边界验证；通常几次引擎计算即可确认包括时柱在内的四柱。子时按用户给定民用日期的 `00:00–01:00` 与 `23:00–24:00` 核验，保留换日、时干或节气造成的候选。不能选择范围中点冒充出生时刻。

范围内四柱一致时，展示完整四柱和由它们确定的十神、藏干等事实；跨界时展示稳定柱与候选，不追问分钟来阻塞首盘。`precision=time-range` 始终保留范围语义；精确起运日期和当前大运不由探测时刻补出。范围盘分析仅使用脚本提供的稳定事实，报告大运模块显示 `time_range` 的固定说明。

八字范围计算沿用民用时间、午夜换日，显式范围同时切分时辰、午夜和节气边界。非 UTC+8 的八字范围尚未支持可靠节气换算，脚本明确返回能力边界；不把已知时段改成整日绕过限制。

西占范围在 1800—2200 年内复用随包星历，上升保持南北纬 65 度以内的能力边界。范围时区逐秒校验 UTC 往返与偏移一致性；DST 跳变／回拨范围停止，不任选一边，1949 年前仍需已核验历史偏移。星座核验按角速度宽裕上界做自适应区间细分，接近交界时核验到秒，不因起止星座相同就判为稳定，覆盖逆行跨界后返回与 360° 回绕。输出说明其秒级分辨率，不声称连续无限精度；不输出探测时间、代表度数、相位或宫位。所有未跨界的项目继续正常预置文案，候选项仅给简短原因。维护时运行 `test_birth_time_range.py`、`test_western_time_range.py` 和既有时辰回归。
