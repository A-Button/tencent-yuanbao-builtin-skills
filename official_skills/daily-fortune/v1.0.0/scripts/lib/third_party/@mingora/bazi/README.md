<p align="center">
  <a href="https://mingora.app/">
    <img src="./assets/mingora-mark.svg" width="72" height="72" alt="Mingora" />
  </a>
</p>

<h1 align="center">@mingora/bazi</h1>

<p align="center">
  A focused, typed BaZi calculation and analysis toolkit for modern applications.
</p>

<p align="center">
  <a href="./README.md">English</a> · <a href="./README.zh-CN.md">简体中文</a>
</p>

<p align="center">
  The production BaZi calculation engine behind <a href="https://mingora.app/">Mingora</a>.
</p>

`@mingora/bazi` powers BaZi calculations in production at [Mingora](https://mingora.app/). It calculates Four Pillars, true solar time, Five Element profiles, Da Yun timing, and deterministic relationship signals. It uses [`lunar-javascript`](https://github.com/6tail/lunar-javascript) for low-level Chinese calendar conversion while keeping its public API, time-zone behavior, analysis model, and output contract independent and JSON-safe.

Try the user-facing experience with the [Mingora BaZi Calculator](https://mingora.app/bazi-calculator).

Explore the calculation method, boundary behavior, and public API on the [Mingora BaZi documentation site](https://mingora-app.github.io/bazi/).

> BaZi is a traditional interpretive system. This library provides deterministic calendar and rule calculations, not scientific predictions or professional advice.

## Why this library

- TypeScript-first public API with strict, serializable types
- IANA historical time-zone and DST handling
- High-precision true-solar-time correction
- Explicit midnight and Zi-hour day-boundary policies
- Honest uncertainty when birth time is unknown
- Versioned, inspectable Five Element analysis
- Precise Sect 2 Da Yun starting offsets

## Install

```bash
pnpm add @mingora/bazi
```

You can also use npm or Yarn:

```bash
npm install @mingora/bazi
```

## Calculate a chart

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

City lookup and geocoding are deliberately outside this package. Supply an IANA time zone and longitude from your own location provider.

## Unknown birth time

```ts
const chart = calculateBaziChart({
  date: { year: 1992, month: 3, day: 14 },
  time: null,
});

console.log(chart.pillars.hour);      // null
console.log(chart.confidence.level); // "medium" or "low"
console.log(chart.warnings);
```

The library never invents an hour pillar. It compares the beginning and end of the recorded date and lowers confidence when a year, month, or day pillar could change within that day.

## True solar time

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

The calculation applies:

1. historical IANA UTC-offset resolution;
2. DST removal;
3. standard-meridian longitude correction;
4. a Meeus/NOAA-style equation of time;
5. safe date rollover when the correction crosses midnight.

Ambiguous and nonexistent civil times support `compatible`, `earlier`, `later`, and `reject`. For a visual explanation, see [How true solar time changes a BaZi chart](https://mingora.app/learn/true-solar-time-bazi).

The legal standard offset is inferred from the IANA zone's yearly offsets. For rare negative-DST regimes or political offset changes, provide `location.standardOffsetMinutes` explicitly.

## Day boundary

```ts
options: {
  dayBoundary: "midnight" // day changes at 00:00, lunar-javascript Sect 2
}
```

or:

```ts
options: {
  dayBoundary: "zi-hour" // day stem changes at 23:00, Sect 1
}
```

The default is `midnight`. The selected policy is returned in `calculationTime.dayBoundary`. See [BaZi birth-hour boundaries](https://mingora.app/learn/bazi-hours) for the product-facing explanation.

## Da Yun

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

Da Yun uses `lunar-javascript` calculation Sect 2, preserving year, month, day, and hour in the starting offset. Cycle ages use an elapsed-year convention (`cycle year - birth year`), while `startOffset` is the precise timing result. You can compare the output with Mingora's [Da Yun starting-age calculator](https://mingora.app/bazi-da-yun-starting-age-calculation).

## Relationship analysis

```ts
import { calculateBaziChart } from "@mingora/bazi";
import { analyzeRelationship } from "@mingora/bazi/relationship";

const result = analyzeRelationship(chartA, chartB, "communication");
```

Relationship output is deterministic and evidence-based. It compares Day Masters, polarity, element distribution, role rhythm, and cross-chart branch combinations, clashes, harms, and destructions.

## Public API

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

## Analysis model

`mingora-elements-v1` is a versioned application-level model:

- each visible stem contributes `1`;
- hidden stems use `1`, `0.7/0.3`, or `0.6/0.3/0.1` proportions;
- the month branch has `1.5×` hidden-stem weight;
- seasonal multipliers are applied before normalization;
- percentages use largest-remainder rounding and always total `100`.

These weights are an explicit interpretive policy, not an astronomical fact. Raw and season-adjusted scores are returned so consumers can audit the result.

## Accuracy and tests

The test suite covers:

- all ten stems, twelve branches, hidden stems, and Ten God mappings;
- known reference charts and the Li Chun boundary;
- both supported day-boundary policies;
- unknown-time uncertainty;
- IANA DST gaps and overlaps;
- fractional time zones and international-date-line rollover;
- high-precision equation-of-time bounds;
- precise Sect 2 Da Yun starting offsets;
- deterministic relationship output;
- a reproducible 500-chart randomized comparison against direct `lunar-javascript` results.

Run:

```bash
pnpm check
pnpm test:coverage
pnpm build
```

No software can guarantee the correctness of historical birth records or interpretive choices. This project targets deterministic behavior, explicit policies, and tested calendar parity within its documented range.

## Project links

- [Documentation](https://mingora-app.github.io/bazi/)
- [Mingora](https://mingora.app/)
- [Live BaZi Calculator](https://mingora.app/bazi-calculator)
- [Issue tracker](https://github.com/mingora-app/bazi/issues)

## License

MIT. See [LICENSE](./LICENSE) and [THIRD_PARTY_NOTICES.md](./THIRD_PARTY_NOTICES.md).
