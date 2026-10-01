# query_flight 机票查询

`ctrip_flight::query_flight`。出发日期不传时按无日期查询处理，实际使用中几乎总是要传 `departDate`。

## 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `fromCity` / `toCity` | string | 出发/到达城市中文名，不带"市"。与三字码至少传一组。 |
| `departCityCode` / `arriveCityCode` | string | 城市三字码，如 `PEK`、`SHA`。与中文名至少传一组。 |
| `departDate` | string | `yyyy-MM-dd`，出发日期。 |
| `fromAirport` / `toAirport` | string | 标准机场名，去掉城市前缀，如"浦东国际机场"。**必须与对应的 fromCity / toCity 同时传**，传了就以机场优先。 |
| `departTimeStart` / `departTimeEnd` | string | `HH:mm` 出发时间窗。 |
| `arriveTimeStart` / `arriveTimeEnd` | string | `HH:mm` 到达时间窗，同样配对使用。 |
| `directFlight` | boolean | true 只返回直飞；不传或 false 全部返回。 |
| `airLine` | string | 航司二字码，用于精确筛选，如 `CA`、`MU`。 |
| `airSpace` | string | 舱位筛选：`Y,S` 优先经济舱（无经济舱则超轻舱）、`C,F` 优先公务舱（无公务舱则头等舱）、`C` 公务舱、`F` 头等舱。 |
| `maxPrice` | number | 价格上限。 |
| `sortType` | number | 1 价格从低到高，2 出发从早到晚，3 出发从晚到早，4 价格从高到低。 |
| `allFlights` | boolean | true 返回全部结果；不传或 false 约 10 条。 |
| `locale` | string | 返回语言，默认 `zh-CN`。 |

## 易错点

- 中文名和三字码是"至少一组"，不是"两种都传"。用户给了中文名就只传中文名。
- 三字码只填有把握的。拿不准就用 `fromCity` / `toCity`，猜错会查到另一个城市。
  常用码：`PEK` 北京首都、`PKX` 北京大兴、`SHA` 上海（城市码）、`PVG` 上海浦东、`CAN` 广州、
  `SZX` 深圳、`CTU` 成都、`TFU` 成都天府、`HGH` 杭州、`XIY` 西安、`CKG` 重庆、`NKG` 南京、
  `WUH` 武汉、`CSX` 长沙、`XMN` 厦门、`KMG` 昆明、`KWE` 贵阳、`TAO` 青岛、`TSN` 天津、
  `SYX` 三亚、`HAK` 海口、`URC` 乌鲁木齐、`LXA` 拉萨、`HET` 呼和浩特、`SHE` 沈阳、
  `HRB` 哈尔滨、`DLC` 大连、`TNA` 济南、`CGO` 郑州、`FOC` 福州、`NNG` 南宁、`LHW` 兰州、
  `TYN` 太原、`SJW` 石家庄、`KHN` 南昌、`HFE` 合肥、`WUX` 无锡、`NGB` 宁波、`WNZ` 温州、
  `ZUH` 珠海、`KWL` 桂林、`LJG` 丽江、`JHG` 西双版纳、`HKG` 香港、`TPE` 台北桃园、`MFM` 澳门、
  `NRT` 东京成田、`HND` 东京羽田、`ICN` 首尔、`SIN` 新加坡、`BKK` 曼谷、`KUL` 吉隆坡。
- 时间窗两个参数配对使用。只传 `departTimeEnd` 表示"该时间之前出发"，只传 `departTimeStart`
  表示"该时间之后出发"，这跟"区间"不是一回事。
- 查不到结果时先看是否误开了 `directFlight`、`airLine`、`airSpace`、`maxPrice` 这类收窄条件。

## 示例

"10 月 1 日北京飞上海，早上出发，只看直飞，便宜的排前面"：

```json
{
  "fromCity": "北京",
  "toCity": "上海",
  "departDate": "2026-10-01",
  "departTimeStart": "06:00",
  "departTimeEnd": "12:00",
  "directFlight": true,
  "sortType": 1
}
```
