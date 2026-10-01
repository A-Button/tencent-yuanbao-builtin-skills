# 输出规范

每个小节含卡片结构、字段规则、来源映射、检查清单。展示对应场景前必读对应小节。

核心原则：每部影片/每家影院一张独立卡片，用 `---` 分隔。禁止数字列表（1. 2. 3.），禁止把多个字段挤到同一行（规范允许的同行组合除外）。海报必须用 `<media_info>` 标签渲染，禁止裸链接、Markdown 图片、`<img>`。脚本已对图片 URL 做 120px 缩略图，URL 原样输出。

---

## 海报图片（`<media_info>`）

当影片接口返回的 `poster` / `img` 为有效、非空的 HTTP(S) 图片地址时，必须原样使用该地址输出海报：

```
<media_info>[{"type":"image","description":"《影片名》海报","url":"{poster或img}"}]</media_info>
```

规则：

1. 海报标签必须紧跟在该影片卡片最上方（标题行之前），不得集中放到回复末尾。
2. 每个标签的 JSON 数组中只放当前影片这一张海报。
3. `url` 必须取自本次 Tool 的真实返回结果（`poster` 优先，其次 `img`），不得改写、截断、拼接或自行构造，不得使用搜索结果、历史结果或模型记忆补充。
4. **严禁**同时把海报输出为：裸链接、Markdown 图片 `![...](...)`、「点击打开海报」链接、`<img>` HTML 标签。
5. 地址为空、格式无效（非 HTTP/HTTPS）、无法展示时：跳过海报行，只展示文字卡片，不臆造 URL，不输出「海报暂无法展示」以外的技术字样。

示例（正确）：

```
<media_info>[{"type":"image","description":"《空枪》海报","url":"https://p0.pipi.cn/mediaplus/friday_image_fe/xxx.jpeg?imageMogr2/thumbnail/120x"}]</media_info>

**《空枪》** · ⭐ 9.5
```

示例（错误，禁止）：

```
https://p0.pipi.cn/...jpeg?imageMogr2/thumbnail/120x
![海报](https://p0.pipi.cn/...)
<img src="https://p0.pipi.cn/..." />
```

---

## 影片卡片（共用）

### 卡片结构

```
<media_info>[{"type":"image","description":"《影片名》海报","url":"{poster或img}"}]</media_info>

**《影片名》** · ⭐ 暂无评分

🎭 动画/喜剧/科幻 · 90分钟 | 👥 主演：詹姆斯、皮埃尔

📅 2026-07-03 | 🏛️ 276家影院 | 🔥 19.9万人想看

简介：为了拍摄心中理想的怪兽电影...
```

### 字段规则

1. 海报：按上方「海报图片（`<media_info>`）」规范输出，独占卡片第一行。无有效 URL 则整行省略。
2. 标题行：`**《片名》** · ⭐ 评分`。`score` 为 0 或空 → 「暂无评分」，不显示⭐。
3. 信息行：`🎭 类型/时长 | 👥 主演：...`
4. 数据行：`📅 日期 | 🏛️ N家影院 | 🔥 X.X万人想看`。缺影院数/想看数时从已缓存的热映结果取同 `movieId`；都无则省略该行。
5. 简介约 60 字。
6. 多卡片用 `---` 分隔。

### 字段来源

| 卡片字段 | recommend_hot_movies / search_movies | get_movie_detail |
|---|---|---|
| 海报 | `poster` / `img` | `poster` |
| 片名 | `name` | `title` |
| 评分 | `score` | `score` |
| 类型/时长 | `genre` + `duration` 分钟；搜索用 `cat` + `dur` | `genre` + `duration` |
| 主演 | `actors` / `star` 前 2-3 个 | `actors` 前 2-3 个 |
| 上映日期 | `releaseDate` / `pubDesc` | `releaseDate` |
| 影院数/想看数 | `showInfo` / `wish` | 缺省时从热映缓存取 |
| 简介 | `description` | `description` |

### 检查清单

- [ ] 海报用 `<media_info>[{"type":"image",...}]</media_info>`，不是裸链接 / `![...](...)` / `<img>`
- [ ] `url` 是接口返回的原始值，未做修改
- [ ] 每个标签只含一张当前影片海报
- [ ] 每个信息独占一行

---

## 热映榜单

`recommend_hot_movies --limit 10` 后 LLM 过滤，最终不超过 5 部。

```
🎬 **猫眼热映榜单**

---

{影片卡片}

---

{影片卡片}
```

展示完询问：「想看哪部电影，我可以帮您查附近影院排片 🎬」

同时引导用户去猫眼小程序看完整热映列表（`pages/cinema/index`，`activeTab=1` 为热映 Tab）。有 `cityId` 时拼进 query，没有则只传 `activeTab=1`：

```
想在小程序里看更多热映、选片购票，点这里打开猫眼 👇
[查看更多热映电影](weixin://dl/business/?appid=wxdbb4c5f1b8ee7da1&path=pages/cinema/index&query=activeTab%3D1)
```

有城市时只拼数字 `cityId`（示例北京 `cityId=1`）：

```
[查看更多热映电影](weixin://dl/business/?appid=wxdbb4c5f1b8ee7da1&path=pages/cinema/index&query=activeTab%3D1%26cityId%3D1)
```

规则：
- **直达，不经首页**。`path` 固定 `pages/cinema/index`，`activeTab=1`
- **禁止把 `cityName` 放进 Scheme**。明文 Scheme 的 query 只允许数字、英文和少量符号，中文城市名（含 `%E5%8C%97...` 这种编码）会导致「当前页面无法访问」
- 只传 `cityId` 时链接能打开。页面 `initCity` 要同时有城市名才会切城，因此小程序内城市跟用户当前定位/缓存，不保证切到 `cityId` 对应城市
- 先拼明文 query，再对整段做一次 `encodeURIComponent` 放进 `query=`
- `appid` 固定 `wxdbb4c5f1b8ee7da1`，不要带 `env_version`
- 用 Markdown 链接，禁止只输出裸 `weixin://`
- 链接紧跟在「想看哪部电影…」引导语之后

---

## 单部影片详情

用户问「介绍 XX」「XX 讲什么」→ `get_movie_detail`，只出一张影片卡片，不加热映标题。展示完询问：「想看这部吗？我可以帮您查附近影院排片 🎬」

然后给出小程序影片详情链接。**必须经首页中转**：详情页不自己切城市，首页 `pages/movie/index` 先 `initCity`，再按 `redirect` 打开 `/pages/moviedetail/movie`。

拼法：

1. `target` = `/pages/moviedetail/movie?movieId={movieId}`
2. `redirect` 值 = `encodeURIComponent(target)`
3. 明文 query = `redirect={redirect值}&cityId={cityId}`（无 cityId 则只留 redirect）。**不要拼 `cityName`**，中文会导致 Scheme 打不开
4. 对整段明文 query 再 `encodeURIComponent` 一次，作为 Scheme 的 `query`

```
想看这部影片的详情、评分和附近场次，点这里打开猫眼 👇
[查看《影片名》详情](weixin://dl/business/?appid=wxdbb4c5f1b8ee7da1&path=pages/movie/index&query={二次编码后的query})
```

示例（movieId=1545360，北京）：明文 query 为

`redirect=%2Fpages%2Fmoviedetail%2Fmovie%3FmovieId%3D1545360&cityId=1`

整段再编码后：

```
[查看《奥德赛》详情](weixin://dl/business/?appid=wxdbb4c5f1b8ee7da1&path=pages/movie/index&query=redirect%3D%252Fpages%252Fmoviedetail%252Fmovie%253FmovieId%253D1545360%26cityId%3D1)
```

`movieId` 用本次详情接口返回值，禁止编造。首页切城需要中文 `cityName`，但 Scheme 不能带中文，因此详情页城市跟小程序内定位/缓存。

---

## 影院卡片（共用）

```
影院全名[ ⭐ 已选]

💰 最低票价： 40元起

📍 地址： 详细地址 🚗 距离： 2.4km

🏷️ 🟢退  🔵改签  🟠小吃  🟣4K厅
```

1. 影院名纯文本独占一行（不加粗、不用标题）；已选定末尾追加 ` ⭐ 已选`。
2. 票价行可选：`💰 最低票价：{sellPrice}元起`。无 `sellPrice` 则省略。
3. 地址+距离同一行；无距离只展示地址。不展示电话。
4. labels：`{emoji}{name}`（中间无空格），标签之间两个空格，行首 `🏷️ `。`emoji` 空则只展示 name。无标签整行省略。禁止 HTML 内联样式。
5. 卡片间 `---`。

列表/搜索场景：名/票价/地址+距离/labels 全开。最多 5 家。

字段：列表接口用 `name`（不是 `nm`）；详情用 `name`。

### 检查清单

- [ ] 影院名纯文本
- [ ] 地址和距离同一行，其余各占一行
- [ ] emoji 与 name 无空格；无标签不留空 `🏷️`

---

## 影院列表

```
🏛️ **附近影院**

---

{影院卡片}
```

搜索场景标题改为 `🔍 **搜索结果**`。展示完询问：「请告诉我您想去哪家影院？」超出 5 家时提示缩小范围或指定店名。

然后给出小程序影院列表链接。**直达，不经首页**。`activeTab=2` 为影院 Tab。

明文 query：`activeTab=2&cityId={cityId}`，整段 `encodeURIComponent` 一次。**禁止拼 `cityName`**，中文（以及它的百分号编码）会让明文 Scheme 打不开。无 cityId 时只传 `activeTab=2`。

```
想看更多影院，点这里打开猫眼 👇
[查看影院列表](weixin://dl/business/?appid=wxdbb4c5f1b8ee7da1&path=pages/cinema/index&query=activeTab%3D2%26cityId%3D1)
```

只传 `cityId` 时页面能打开，但 `initCity` 没有中文城市名不会强制切城，列表城市跟用户微信里的定位或缓存。

---

## 场次列表

```
🎭 **《影片名》场次** — 2026-07-02

🕐 14:30
🏛️ 1号厅
🗣️ 国语 2D
💰 ￥35起

---

🕐 17:00
🏛️ IMAX厅
🗣️ 国语 IMAX
💰 ￥85起
```

每个场次 4 行竖排：时间 / 影厅 / 语言+格式 / 价格（必须带「起」）。场次之间 `---`。结束后询问想看哪个时间。

---

## 影院排片页

`get_cinema_show` / `recommend_nearby_shows` 后使用。

**严禁海报**：不要 `<media_info>`、不要裸链接、不要 `![海报](url)`，不要影片卡片格式。影片信息一行文字。每个场次一行，场次之间必须空行。

```
🏛️ **{cinemaName}** 排片表

📍 地址： {cinemaAddr} 🚗 距离： 2.4km

---

📅 **2026-07-13**（今日）

---

🎬 **《功夫女足》** ⭐9.4 · 106分钟 | 喜剧 | 张小斐,迪丽热巴,张艺兴

🕐 18:00 🏛️ 2号-激光厅 🗣️ 国语 2D 💰 ￥48.9

🕐 19:30 🏛️ 9号IMAX厅 🗣️ 国语 IMAX2D 💰 ￥62.9

---

🎬 **《八仙！》** 预售 · 144分钟 | 神话 | 李绍哲,陈浩,立冬

🕐 19:40 🏛️ 7号-激光2D厅 🗣️ 国语 2D 💰 ￥52.9
```

### 字段规则

1. 标题 `🏛️ **{cinemaName}** 排片表`，下一行地址+距离。`get_cinema_show` 无 distance：入口 A 用 `recommend_nearby_shows.cinemas[].distance`；入口 B/C 用上一步影院查询记住的距离。无距离则省略距离段。
2. 日期分组：`📅 **{showDate}**（今日/明日/周X）`。未指定日期默认当天，并告知「已为您查询今日排片，如需其他日期请告知」。
3. 影片块：`🎬 **《{name}》** {状态} · {desc}`
   - `globalReleased=true` → `⭐{score}`（0 显示「暂无评分」）；否则「预售」
   - `desc` 用接口原值
   - 场次行：`🕐 {startTime} 🏛️ {hall} 🗣️ {language} {dimension} 💰 ￥{sellPrice}`
   - **场次行之间必须空行**，否则 Markdown 会挤成一行
4. 同影片内场次只用空行；影片块之间用 `---`。
5. 结束后询问：「请告诉我您想看哪天的哪场？回复时请说「日期+时间」，如「今天 19:30」。」
6. 排片内容展示完后，给出小程序影院排片链接。**直达，不经首页**。排片页用 `cinemaId` 拉场次，不依赖首页切城。`day` 用实际展示的 `appliedShowDate`（兜底后的日期），有选定影片时带 `movieId`。

明文 query：`cinemaId={cinemaId}&movieId={movieId}&day={YYYY-MM-DD}`，没有 movieId 就去掉该项。整段 `encodeURIComponent` 一次。`path` 固定 `pages/cinemasub/cinema`。

```
想在小程序里看这家影院的完整排片并选座，点这里打开猫眼 👇
[查看{cinemaName}排片](weixin://dl/business/?appid=wxdbb4c5f1b8ee7da1&path=pages/cinemasub/cinema&query=cinemaId%3D26902%26movieId%3D1545360%26day%3D2026-09-23)
```

`cinemaId` / `movieId` / `day` 必须来自本次排片结果，禁止编造。多家影院（入口 A 的 `recommend_nearby_shows`）每家各出一条链接，紧跟该影院排片块，不要汇总到文末。

### 兜底标志

展示排片内容前先输出说明。展示用 `appliedShowDate` / `appliedMovieId`，不用用户原始请求值。

| 标志 | 向用户说明 |
|------|-----------|
| `empty: true` | 「该影院暂无排片信息」 |
| `movieChanged: true` | 「该影院暂无《原影片》排片，已为您展示《切换后影片》」 |
| `noDateAvailable: true` | 「《原影片》近期无排片，已为您展示《切换后影片》{appliedShowDate}的场次」 |
| `dateChanged: true` | 「《影片名》今日暂无场次，已为您展示 {appliedShowDate} 的排片」 |
| `timeRangeRelaxed: true` | 「{原时段}暂无场次，已为您展示全部时段」 |

### 检查清单

- [ ] 没有海报
- [ ] 影片信息一行
- [ ] 场次之间有空行
- [ ] 影片块之间用 `---`
