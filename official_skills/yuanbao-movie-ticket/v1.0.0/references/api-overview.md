# 影讯查询子命令 API 总览

通过 `scripts/dist/run.js` 子命令调用。接口域名：`https://api.maoyan.com`（TA 签名，由 `ENV` 切换 test/st/prod）。

---

## 影片（4）

### `recommend_hot_movies`

热映榜单，并发补全每部影片详情。

**参数**：`cityId?` number（默认环境 `CITY_ID`，1=北京）；`limit?` number（默认 8，最多 10）

**返回**：`{ total, movies[] }`，每项含 `movieId` / `name` / `poster` / `score` / `scoreLabel` / `genre` / `duration` / `description` / `director` / `actors[]` / `releaseDate` / `showInfo` / `wish` / `version` / `showStateButton`

### `search_movies`

按关键词搜索影片（只返回 showst=3/4，正在/即将上映）。

**参数**：`keyword` 必填；`cityId?`；`lat?`；`lng?`

**返回**：`{ total, movies[] }` — `movieId` / `name` / `img` / `score` / `cat` / `dur` / `pubDesc` / `wish` / `star`

### `get_movie_detail`

**参数**：`movieId` 必填

**返回**：`movieId` / `title` / `genre` / `duration` / `score` / `description` / `director` / `actors[]` / `poster` / `releaseDate`

### `get_movie_show_days`

影片在当前城市的可观影日期。

**参数**：`movieId` 必填；`cityId?`；`channelId?`

**返回**：`{ total, dates: [{ date, isPredate, labelResource }] }`

---

## 影院（4）

所有影院接口的 `labels[]`：`name`、`color`、`borderColor`、`emoji`（脚本按 color 映射 🟢🟡🟠🔴🟣🔵🟤⚪⚫）。

三个列表工具共用城市/经纬度三级解析 + IP 兜底。

### `get_nearby_cinemas`

**参数**：`cityId?`；`cityName?`；`lat?`；`lng?`；`sort?`（distance | price）；`offset?`（默认 0）；`limit?`（默认 20）

**返回**：`{ total, hasMore, offset, cinemas[] }`，每项 `cinemaId` / `name` / `addr` / `distance` / `sellPrice` / `priceDesc` / `labels[]`

### `search_cinemas`

**参数**：`keyword` 必填（脚本会去掉「电影院/影城」等后缀再搜）；`cityId?`；`cityName?`；`lat?`；`lng?`

**返回**：`{ total, cinemas[] }`，字段同上

### `get_cinema_detail`

**参数**：`cinemaId` 必填

**返回**：`cinemaId` / `name` / `addr` / `phone` / `lat` / `lng` / `sellPrice` / `poiId` / `labels[]`

### `get_cinemas_by_movie`

指定影片在指定日期有排片的影院。

**参数**：`movieId` 必填；`showDate?`（默认今天北京时间）；`cityId?`；`lat?`；`lng?`；`sort?`；`offset?`；`limit?`

---

## 排片（2）

过滤走 `filterCinemaShow`（服务端确定性执行，含已开场过滤 + 5 级兜底）。LLM 不要自行再过滤日期/时段。

**timeRange 格式**（解析失败则忽略）：

- 时段词：`上午`(0-12) / `下午`(12-18) / `晚上`(18-24)
- 中文点：`19点后` / `晚上7点后` / `下午3点半以后` / `上午9点前` / `19点到21点`
- HH:mm：`19:30后` / `19:30以前` / `19:30到21:30` / `19:30`（前后 30 分钟）

**兜底标志**（展示前必须据实告知）：

| 标志 | 含义 |
|------|------|
| `empty: true` | 全影院无排片 |
| `movieChanged: true` | 请求影片不存在，已切到 `appliedMovieId` |
| `noDateAvailable: true` | 影片无任何日期，已切影片+日期 |
| `dateChanged: true` | 目标日期无场次，已切到 `appliedShowDate` |
| `timeRangeRelaxed: true` | 时段过滤为空，已放宽，`appliedTimeRange` 为 null |

### `recommend_nearby_shows`

编排：定位城市 → 最近 2 家有该片排片的影院 → 拉排片 → 过滤。用户已选定影片后优先用。

**参数**：`movieId` 必填；`showDate?`（默认今天）；`timeRange?`；`cityId?`；`cityName?`；`lat?`；`lng?`

**返回**：`{ success, cityId, lat, lng, cinemas[] }`。每家含 `cinemaId` / `cinemaName` / `cinemaAddr` / `distance` / `movies[]` / 兜底标志 / `requested*` / `applied*`。

`movies[].shows[].plist[]` 场次字段：`seqNo` / `startTime` / `date` / `language` / `dimension` / `hall` / `sellPrice` / `originalPrice` / `discountPrice`

> `plist[].seqNo` 是场次主键。本技能不继续选座/下单，选定后只记录并告知用户去猫眼 App 购票。

### `get_cinema_show`

单影院排片。不传 `showDate` 默认今天；传 `movieId` 只返回该片；传 `timeRange` 按时段过滤。

**参数**：`cinemaId` 必填；`cityId?`；`channelId?`；`movieId?`；`showDate?`；`timeRange?`

**返回**：`{ success, cinemaName, cinemaAddr, movies[], empty, movieChanged, dateChanged, noDateAvailable, timeRangeRelaxed, appliedMovieId, appliedShowDate, appliedTimeRange }`

> 不返回 `distance`。入口 A 用 `recommend_nearby_shows` 的 `cinemas[].distance`；入口 B/C 用上一步影院查询结果里记住的距离。

---

## 工具（2）+ init

### `get_location`

经纬度查城市；不传则 IP 定位。

**返回**：`{ success, cityId, cityName, lat, lng }`

### `get_city_by_name`

**参数**：`cityName` 必填（汉字或拼音）

**返回**：`{ success, cityId, cityName, pinyin }`

### `init`

环境准备：Node >= 18 → npm → install → tsc → `.env` → CLIGuard。返回 `{ success, scripts_dir, node }` 或 `{ success: false, error, message }`。
