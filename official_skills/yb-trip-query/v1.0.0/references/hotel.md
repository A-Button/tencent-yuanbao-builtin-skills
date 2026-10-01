# query_hotel 酒店查询

`ctrip_hotel::query_hotel`。房价与日期强相关，查房价时 `checkInDate` / `checkOutDate` 都要传。

## 查询方式优先级

从高到低，命中靠前的组合就别再拼后面的：

1. `keyword` 关键字（与其他所有参数互斥）
2. `cityName` + `landmarkName` + `hotelName`
3. `cityName` + `hotelName`
4. `cityName` + `landmarkName`
5. `hotelName` + `landmarkName`
6. `hotelName`
7. `cityName`
8. `landmarkName`
9. `longitude` + `latitude`
10. `tags`

## 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `checkInDate` / `checkOutDate` | string | `yyyy-MM-dd` 入住/离店日期。 |
| `cityName` | string | 城市中文名，不带"市"。 |
| `hotelName` | string | 具体酒店名。 |
| `landmarkName` | string | 知名地标。 |
| `keyword` | string | 口语化模糊检索，**与其他参数互斥**。 |
| `longitude` / `latitude` | number | 经纬度，必须成对使用。 |
| `minPrice` / `maxPrice` | number | 价格区间。 |
| `stars` | string | 星级，多个用英文逗号分隔，取值 `[0,1,2,3,4,5]`，如 `"4,5"`。 |
| `sortType` | string | `"1"` 默认排序、`"2"` 低价优先。是字符串不是数字。 |
| `tags` | string | 单标签。取值：农庄、奢华、设计感、豪华、亲子乐园、城市美食、当地风情、别墅、古镇、美景、高档、滑雪、温泉泡汤、精品民宿。 |

## 易错点

- 传 `keyword` 时**只有检索页 H5 和携程 APP 地址会返回**，拿不到结构化酒店与房型数据。
  用户说的是口语化描述（"西湖边能看到断桥的民宿"）才用它，否则优先走 2–9 的结构化组合。
- 传 `tags` 时，除 `cityName` 外的其他参数全部失效。只支持「`cityName` + `tags`」或单独 `tags`，
  且一次只能一个标签。
- `sortType` 是字符串 `"1"` / `"2"`，不要写成数字 1 / 2。
- 经纬度必须两个都传，只传一个无效。
- `stars` 是逗号分隔的字符串 `"3,4,5"`，不是数组。
- 用户只给城市不给日期时，先问入住/离店日期；不给日期查到的价格没有意义。

## 示例

"10 月 2 日到 10 月 5 日，杭州西湖附近，四星和五星，便宜的排前面"：

```json
{
  "cityName": "杭州",
  "landmarkName": "西湖",
  "checkInDate": "2026-10-02",
  "checkOutDate": "2026-10-05",
  "stars": "4,5",
  "sortType": "2"
}
```
