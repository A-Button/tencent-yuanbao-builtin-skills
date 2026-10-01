# query_train 火车票查询

`ctrip_train::query_train`。`fromCity` 与 `toCity` 是必填项。

## 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `fromCity` / `toCity` | string | **必填**。出发/到达城市中文名，不带"市"。 |
| `departDate` | string | `yyyy-MM-dd`，出发日期，可选但建议必传。 |
| `departStation` / `arriveStation` | string | 出发/到达站名，各**只能传一个**，如"北京南""上海虹桥"。 |
| `timeType` | string | `DepartTime` 或 `ArriveTime`。 |
| `startTime` / `endTime` | string | `HH:mm`，配合 `timeType` 使用。 |
| `trainTypeMode` | string | `OnlyHighSpeed` 仅高铁、`ExcludeHighSpeed` 排除高铁；不传返回全部。 |
| `minPrice` / `maxPrice` | integer | 价格区间，**只能是整数**。 |
| `needTransfer` | boolean | 是否需要中转数据，默认 false（不需要）。 |

## 易错点

- 参数名是 `fromCity` / `toCity`，不是航班那套 `from` / `to` 或 `departCityCode`，别混用。
- 时间筛选三件套要对齐：先定 `timeType`（按出发还是到达时间筛），再给 `startTime` / `endTime`。
  没传 `timeType` 但传了时间，默认按出发时间处理。只传 `endTime` 是"该时间之前"，
  只传 `startTime` 是"该时间之后"。
- 价格区间只对**已开售、可预订的坐席**生效，未开售车次不会被价格条件筛掉或筛出来。
- 只传 `maxPrice` 时 `minPrice` 视为 0；只传 `minPrice` 时 `maxPrice` 视为不限。
- 用户说"高铁"用 `OnlyHighSpeed`；说"普通车/便宜的绿皮"用 `ExcludeHighSpeed`；只说"火车"就不传。
- 同一城市多车站时（北京南/北京西），用户指定站点才传 `departStation`，否则让工具返回全部。

## 结果呈现

按车次列出：车次号、出发站/到达站、出发与到达时间、历时、主要席别与余票、最低价。
余票状态以回包为准，回包没给席别余票就只报车次与时刻，不要写"有票"。

## 示例

"9 月 30 日杭州到北京的高铁，上午出发，800 以内"：

```json
{
  "fromCity": "杭州",
  "toCity": "北京",
  "departDate": "2026-09-30",
  "timeType": "DepartTime",
  "startTime": "06:00",
  "endTime": "12:00",
  "trainTypeMode": "OnlyHighSpeed",
  "maxPrice": 800
}
```
