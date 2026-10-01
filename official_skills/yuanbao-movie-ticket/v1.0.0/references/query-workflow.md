# 查询编排流程

本文件是对话流程编排（SOP）的**唯一事实源**。`SKILL.md` 只做能力索引。执行入口判定或 A/B/C 任一步骤前必须先读本文件，不要跳步、不要压缩步骤。

## 环境

每次对话首次调用：`cd "$SCRIPTS_DIR" && node dist/run.js init`，成功后再跑业务命令。

cityId：优先使用用户配置中的默认 cityId；用户说"北京/上海/..." → `get_city_by_name`；用户提供经纬度 → `get_location`；都没有 → 脚本 IP 兜底 / 默认北京。

## 查询两个必要条件

完成查询必须同时具备两个条件：
1. **影片**（movieId）— 用户要看哪部影片
2. **影院**（cinemaId）— 用户要去哪家影院

最终都要收敛到 **seqNo（场次）+ cityId**。`seqNo` 只能从 `get_cinema_show` / `recommend_nearby_shows` 的 `plist[].seqNo` 获取，不能猜测或构造。三个入口收敛到 seqNo + cityId 后，本技能结束查询流程，不再进入选座/下单/支付。购票请打开猫眼 App。

## 入口判定（每次对话开头判断）

根据用户已表达的必要条件，判定走哪个入口：

| 已有信息 | 入口 | 起点 |
|---------|------|------|
| 只有影片 | **入口 A**（缺影院） | 找放映该片的影院 |
| 只有影院 | **入口 B**（缺影片） | 看这家影院的排片选片 |
| 影院+影片都有 | **入口 C**（都不缺） | 直接查该影院该片的场次 |
| 都没有 | 兜底 | 主动询问「想看什么电影？」（不主动推热映，等用户说出影片意图再判定入口） |

> ⚠️ 入口判定贯穿多轮对话：用户首轮只说影片（入口 A），后续轮次补充了影院，即切换到入口 C 收敛；反之亦然。每轮都重新评估两个条件是否齐备。

---

## 入口 A：只有影片 → 补影院

### Step 1 确认影片（两种来源）

- **A1 泛意图**（用户未指定片名，如「推荐电影」「热映有什么」「想看 9.6 分以上的」「白敬亭主演的有什么」）
  → `cd "$SCRIPTS_DIR" && node dist/run.js recommend_hot_movies --limit 10` 拉取热映榜单
  → **LLM 按用户筛选条件过滤**（脚本返回全量，由 LLM 逐部比对，不是脚本过滤），最终展示不超过 5 部：

  | 用户意图 | 对应字段 | 比较方式 |
  |---------|---------|---------|
  | 评分（如"9分以上"） | `score`（float） | `score >= 用户指定分数`；score 为 0 / null 视为无评分，**不满足**任何评分条件 |
  | 类型（如"动画"、"悬疑"） | `genre`（string） | `genre.includes(关键词)` |
  | 时长（如"2小时以内"） | `duration`（number，分钟） | 解析为分钟后 `duration <= 上限` |
  | 版本（如"IMAX"、"CINITY"） | `version`（string） | `version.includes(关键词)`，忽略大小写 |
  | 演员（如"包含吴京"） | `actors`（array）/ `star`（string） | actors 数组或 star 字符串包含演员名 |
  | 上映时间（如"5月上映"、"最近两天"） | `releaseDate`（string） | 见下方【相对时间窗规则】 |

  **【相对时间窗规则】（严格执行）**：
  - 当前北京时间（UTC+8）为基准，**精确推算**绝对日期范围。
  - "最近两天" → 昨天 + 今天；"今明两天" → 今天 + 明天；"过去三天" → 前天 + 昨天 + 今天。
  - 逐部影片与 `releaseDate` 比对（日期字符串包含匹配）。
  - **禁止**把用户给的相对窗口扩大、缩小或替换为其他范围。
  - 窗口内无影片命中 → 回复「当前热映榜单中，[时间窗]内没有新上映的影片」，不展示其他影片。

  - 有筛选条件 → 按上表过滤，命中 0 部则告知用户无匹配、建议调整条件
  - 无筛选条件 → 直接取前 5 部展示
  → 展示卡片，等用户选择 → ✅ 记录 movieId

- **A2 精确意图**（用户指定了片名，如「看玩具总动员5」「帮我买消失的人的票」）
  → `cd "$SCRIPTS_DIR" && node dist/run.js search_movies --keyword <影片名>` → 命中影片 → ✅ 记录 movieId
  → 若搜索结果缺详情 → `cd "$SCRIPTS_DIR" && node dist/run.js get_movie_detail --movie-id <movieId>` 补充

### Step 2 找影院排片

⚠️ 必须在同一次回复中，**先输出文案、再调用接口**，两步缺一不可：

第一步 — 立即输出文案（不等用户回复，文案出现在接口结果之前）：
「正在为您寻找[城市名/当前城市]附近《影片名》的排片信息，请稍候 🎬」

第二步 — 调用 `cd "$SCRIPTS_DIR" && node dist/run.js recommend_nearby_shows --movie-id <movieId> [--city-id N | --city-name 北京 | --lat N --lng N]`（参数详见 api-overview.md）

回退标志处理（脚本返回后追加说明，标志含义详见 api-overview.md）：
- `movieChanged=true` → 「附近暂无该影片排片，已为您推荐《xx》」
- `dateChanged=true` → 「今日暂无场次，已为您展示 [日期] 的排片」
- `noDateAvailable=true` → 「该影片附近暂无排片，已为您推荐《xx》」

### Step 3 选场次

→ 展示 `recommend_nearby_shows` 返回的影院列表（JSON 的 `cinemas[]`），**每家影院用「影院排片页」格式**（见输出规范），多家影院之间用 `---` 分隔。
  - 每家影院只含**用户已选定的那一部影片**（`recommend_nearby_shows` 已按 movieId 过滤，返回的 `movies[]` 只有这一部）
  - 影院标题统一用 `🏛️ **{cinemaName}** 排片表` + 地址距离行，与入口 B/C 完全一致
  - 日期分组 + 影片块 + 场次列表，完全复用排片页字段规则
  - ⚠️ 检查每个影院的兜底标志（`movieChanged`/`dateChanged`/`timeRangeRelaxed`）并据实告知
→ 等用户回复想看的放映时间 → 匹配对应场次 → ✅ 记录 **seqNo + cinemaId + cityId**

---

## 入口 B：只有影院 → 补影片

### Step 1 确认影院（两种来源）

- **B1 泛意图**（用户未指定影院，如「附近有什么影院」「推荐个影院」）
  → `cd "$SCRIPTS_DIR" && node dist/run.js get_nearby_cinemas [--city-id N | --city-name 北京 | --lat N --lng N]` → 按距离返回附近影院
  → 展示影院列表，等用户选择 → ✅ 记录 cinemaId

- **B2 精确意图**（用户指定了影院名，如「万达五月花」「横店影城」）
  → `cd "$SCRIPTS_DIR" && node dist/run.js search_cinemas --keyword <影院名>` 搜索
  → ⚠️ **可能返回多家同名/相关影院**（如「万达」在多个商场都有分店）
  → 展示全部匹配结果（名称/地址/距离），**让用户选择具体哪一家** → ✅ 记录 cinemaId
  → 若仅 1 家命中可直接采用，但仍展示确认信息

### Step 2 看排片选片

→ `cd "$SCRIPTS_DIR" && node dist/run.js get_cinema_show --cinema-id <cinemaId> [--city-id N]` 获取该影院今日排片（**脚本默认过滤今天**，无需 LLM 过滤）
  ⚠️ **观影日期处理**：用户未明确日期时**不传 --show-date**（脚本默认今天）并告知用户「已为您查询今日排片，如需其他日期请告知」；用户指定日期则传 `--show-date`。
  ⚠️ 用户提到时段（如「晚上」「19点后」）则传 `--time-range`，脚本按时段过滤。
→ 展示影片列表（按影片分组，每部影片带场次，格式见输出规范「影院排片页」）
  ⚠️ 检查返回的兜底标志并告知用户（见影院排片页「兜底标志处理」）
→ 等用户选择影片 + 场次 → ✅ 记录 **seqNo + movieId**

---

## 入口 C：影院+影片都有 → 直接查场次

→ `cd "$SCRIPTS_DIR" && node dist/run.js get_cinema_show --cinema-id <cinemaId> [--city-id N] --movie-id <movieId>` 获取该影院该影片的场次（**脚本按 movieId 过滤**，无需 LLM 匹配）
  ⚠️ **观影日期处理**：用户未明确日期时不传 `--show-date`（脚本默认今天）并告知「已为您查询今日场次，如需其他日期请告知」；指定日期则传 `--show-date`。
  ⚠️ 用户提到时段则传 `--time-range`。
→ 展示该影片在该影院的场次列表（格式见输出规范「影院排片页」）
  ⚠️ 检查返回的兜底标志并告知用户（见影院排片页「兜底标志处理」）
→ 等用户选择场次 → ✅ 记录 **seqNo**

> 若返回 `movieChanged: true`（该影院无此影片，已切换为其他影片）→ 告知用户，并提示可换影院（切换到入口 A）或换影片（切换到入口 B）
