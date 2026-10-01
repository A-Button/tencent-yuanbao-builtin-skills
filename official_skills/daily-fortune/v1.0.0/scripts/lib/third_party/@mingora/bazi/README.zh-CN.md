<p align="center">
  <a href="https://mingora.app/">
    <img src="./assets/mingora-mark.svg" width="72" height="72" alt="Mingora" />
  </a>
</p>

<h1 align="center">@mingora/bazi</h1>

<p align="center">
  面向现代应用的、类型完整的八字计算与分析工具库。
</p>

<p align="center">
  <a href="./README.md">English</a> · <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  驱动 <a href="https://mingora.app/">Mingora</a> 生产环境的八字计算引擎。
</p>

`@mingora/bazi` 已驱动 [Mingora](https://mingora.app/) 生产环境中的八字计算，提供四柱、真太阳时、五行分布、大运起运以及确定性关系信号。底层使用 [`lunar-javascript`](https://github.com/6tail/lunar-javascript) 完成中国历法转换，同时拥有独立、稳定且可序列化的公共 API、时区处理方式、分析模型和输出协议。

你可以在 [Mingora 八字计算器](https://mingora.app/bazi-calculator) 中体验面向普通用户的产品形态。

你也可以通过 [Mingora BaZi 技术文档站](https://mingora-app.github.io/bazi/) 查看计算流程、边界处理和公共 API。

> 八字属于传统解释体系。本库提供确定性的历法和规则计算，不构成科学预测或任何专业建议。

## 为什么开发这个库

- TypeScript 优先，提供严格且可序列化的类型
- 支持 IANA 历史时区和夏令时处理
- 高精度真太阳时修正
- 明确支持午夜换日和子初换日策略
- 出生时间未知时如实返回不确定性
- 五行分析模型具备版本号且计算过程可检查
- 支持 Sect 2 的精确大运起运时间

## 安装

```bash
pnpm add @mingora/bazi
```

也可以使用 npm 或 Yarn：

```bash
npm install @mingora/bazi
```

## 计算八字命盘

```ts
import { calculateBaziChart } from "@mingora/bazi";

const chart = calculateBaziChart({
  date: { year: 1998, month: 12, day: 13 },
  time: { hour: 12, minute: 0 },
  location: {
    timeZone: "Asia/Shanghai",
    longitude: 116.39,
  },
  options: {
    solarTime: "true",
    dayBoundary: "midnight",
  },
});

console.log(chart.pillars.day.ganZhi);
console.log(chart.dayMasterProfile.label);
console.log(chart.elementProfile.percentages);
```

城市搜索和经纬度查询不属于本库职责。调用方应当通过自己的地点服务提供 IANA 时区和经度。

## 出生时间未知

```ts
const chart = calculateBaziChart({
  date: { year: 1992, month: 3, day: 14 },
  time: null,
});

console.log(chart.pillars.hour);      // null
console.log(chart.confidence.level); // "medium" 或 "low"
console.log(chart.warnings);
```

本库不会虚构时柱。它会比较记录日期开始和结束时的年柱、月柱和日柱；如果某一柱可能在当天发生变化，会降低置信等级并返回警告。

## 真太阳时

```ts
import { calculateTrueSolarTime } from "@mingora/bazi";

const solar = calculateTrueSolarTime({
  date: { year: 2023, month: 11, day: 5 },
  time: { hour: 1, minute: 30, second: 0 },
  timeZone: "America/New_York",
  longitude: -74.006,
  disambiguation: "later",
});
```

计算过程依次处理：

1. IANA 历史 UTC 偏移解析；
2. 夏令时修正；
3. 标准经线与出生地经度修正；
4. Meeus/NOAA 风格的均时差计算；
5. 修正跨越午夜时的日期变化。

对于重复或不存在的民用时间，可以选择 `compatible`、`earlier`、`later` 或 `reject`。更直观的说明可以阅读 [真太阳时如何改变八字命盘](https://mingora.app/learn/true-solar-time-bazi)。

本库会根据 IANA 时区的年度偏移推断法定标准时间。对于极少见的负夏令时制度或政治性时区变更，可以显式传入 `location.standardOffsetMinutes`。

## 换日规则

子正换日：

```ts
options: {
  dayBoundary: "midnight" // 00:00 换日，对应 lunar-javascript Sect 2
}
```

子初换日：

```ts
options: {
  dayBoundary: "zi-hour" // 23:00 更换日干，对应 Sect 1
}
```

默认策略是 `midnight`，最终采用的策略会出现在 `calculationTime.dayBoundary`。产品层面的解释参见 [八字出生时辰和边界](https://mingora.app/learn/bazi-hours)。

## 大运

```ts
import { calculateDaYun } from "@mingora/bazi";

const timing = calculateDaYun({
  birth: {
    date: { year: 2022, month: 3, day: 9 },
    time: { hour: 20, minute: 51 },
  },
  gender: "male",
});

console.log(timing.direction);
console.log(timing.startOffset);
console.log(timing.cycles);
```

大运固定使用 `lunar-javascript` Sect 2，起运偏移保留年、月、日和小时。大运年龄使用周岁式年份差值（`大运年份 - 出生年份`），精确时间以 `startOffset` 为准。你也可以使用 Mingora 的 [大运起运年龄计算器](https://mingora.app/bazi-da-yun-starting-age-calculation) 对照结果。

## 关系分析

```ts
import { calculateBaziChart } from "@mingora/bazi";
import { analyzeRelationship } from "@mingora/bazi/relationship";

const result = analyzeRelationship(chartA, chartB, "communication");
```

关系分析是确定性且基于证据编号的。它会比较双方日主、阴阳、五行分布、角色节奏以及跨命盘的地支合、冲、害、破。

## 公共 API

```ts
validateBirthInput(input)
calculateEquationOfTime(date)
calculateTrueSolarTime(input)
getStemInfo(stem)
getBranchInfo(branch)
getTenGod(dayMaster, targetStem)
calculateFourPillars(input)
analyzeElements(fourPillars)
getChartRoles(chart)
calculateBaziChart(input)
calculateDaYun(input)
analyzeRelationship(chartA, chartB, focus?)
```

## 五行分析模型

`mingora-elements-v1` 是具备版本号的应用层模型：

- 每个透出天干贡献 `1`；
- 藏干比例分别采用 `1`、`0.7/0.3` 或 `0.6/0.3/0.1`；
- 月支藏干权重为 `1.5×`；
- 归一化前应用季节乘数；
- 使用最大余数法取整，最终百分比之和始终为 `100`。

这些权重是明确的解释策略，不是天文学事实。输出会同时保留原始分数和季节调整后分数，方便调用方检查计算过程。

## 准确性与测试

测试覆盖：

- 十天干、十二地支、藏干和十神映射；
- 已知参考命盘和立春边界；
- 两种换日策略；
- 出生时间未知时的不确定性；
- IANA 夏令时空档和重叠；
- 非整点时区和国际日期变更线；
- 高精度均时差范围；
- Sect 2 精确大运起运时间；
- 确定性关系分析；
- 500 组可复现随机命盘与 `lunar-javascript` 直接结果的比较。

执行：

```bash
pnpm check
pnpm test:coverage
pnpm build
```

任何软件都无法保证历史出生记录或解释策略绝对正确。本项目的目标是在明确支持范围内提供确定性行为、透明策略和经过测试的历法一致性。

## 项目链接

- [技术文档](https://mingora-app.github.io/bazi/)
- [Mingora](https://mingora.app/)
- [在线八字计算器](https://mingora.app/bazi-calculator)
- [问题反馈](https://github.com/mingora-app/bazi/issues)

## 许可证

MIT。详见 [LICENSE](./LICENSE) 和 [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md)。
