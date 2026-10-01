# query_ticket 景点门票查询

`ctrip_ticket::query_ticket`。

## 参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `scenicSpotName` | string | 具体景区/景点名，能确定就一定要传。 |
| `cityName` | string | 城市中文名，不带"市"，用于限定城市。 |
| `provinceName` | string | 省份名，用于限定省份。 |
| `keyword` | string | 口语化模糊检索，**与其他所有参数互斥**。 |
| `tag` | string | 主题标签，单值。必打卡、城市亲子、城市赏花踏青、玩水避暑、城市赏秋、城市滑雪、城市温泉、特色体验、园林。 |
| `group` | string | 适用人群，见下表。 |
| `longitude` / `latitude` | number | 经纬度查询。 |
| `resourceSize` | number | 每个景点返回门票数量上限，不传默认 10。 |
| `sortType` | number | 1 默认/推荐、2 高价优先、3 低价优先、4 好评优先。 |

### group 取值

成人票、儿童票、婴幼儿票、老人票、学生票、青少年票、青年票、女士票、男士票、教师票、
军人票、残疾票、医护人员票、优待票、不限人群、亲子票1大1小、亲子票1大2小、家庭票2大1小、
家庭票2大2小、双人票、情侣票、三人票、团队票。

## tag 生效规则

1. 传了 `scenicSpotName`，`tag` 不参与查询逻辑。
2. 没传 `scenicSpotName`：有 `tag` 走标签榜单逻辑（同时有 `cityName` 则带上目的地 id），
   没有 `tag` 走默认查询逻辑。
3. 只传 `tag` 时只走标签榜单逻辑。

## 易错点

- 传 `keyword` 只返回检索页 H5 与 APP 地址，不是结构化票务结果；能用 `scenicSpotName`
  + `cityName` 就别用 `keyword`。
- 用户说"杭州有什么值得玩的"这类没有具体景点的问题，才用 `tag`（如"必打卡"）+ `cityName` 查榜单；
  已经点名景点时不要加 `tag`。
- 票价与人群强相关，用户提到儿童、老人、学生时要传 `group`；没提就按默认结果呈现，
  不要替用户假定人群。
- 同名景点跨城市时（如"西湖""故宫"类同名），补 `cityName` 或 `provinceName` 限定。

## 示例

"杭州必打卡景点"：

```json
{ "cityName": "杭州", "tag": "必打卡" }
```

"故宫成人票"：

```json
{ "cityName": "北京", "scenicSpotName": "故宫", "group": "成人票" }
```
