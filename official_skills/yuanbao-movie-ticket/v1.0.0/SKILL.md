---
name: maoyan-movie-ticket
description: 猫眼影讯查询。查询热映影片、搜索电影、影片详情、附近影院、影院搜索、影院排片和场次。Use when the user asks about movies, cinemas, showtimes, 热映, 排片, 场次, or nearby theaters. Do not use for login, coupons, seats, orders, or payment.
---

# 猫眼影讯查询

查询猫眼热映影片、影院和排片。不覆盖登录、优惠券、选座、下单、支付。

## 触发场景

用户提到以下任意意图时触发本技能：
- 影片查询：「最近有什么好看的电影」「搜下 XX 电影」「XX 几号上映」
- 影院查询：「附近有什么影院」「找找 XX 影院」「哪个影院放 XX」
- 排片查询：「XX 影院今天放什么」「XX 电影有几场」

用户要买票、选座、支付、领券、登录时回复：「本助手只支持查询影片、影院和排片，购票请打开猫眼 App。」

## 脚本入口

`SKILL_ROOT` = 本 `SKILL.md` 所在目录。`SCRIPTS_DIR` = `$SKILL_ROOT/scripts`。

每次对话第一次调用本技能时，先静默执行：

```bash
cd "$SCRIPTS_DIR" && node dist/run.js init
```

若 `dist/run.js` 不存在，`init` 会安装依赖并编译。失败时按 `error` 告知用户：

| error | 用户提示 |
|-------|----------|
| `NODE_VERSION_LOW` | 需要 Node.js >= 18 |
| `NPM_NOT_FOUND` | 需要 npm |
| `INSTALL_FAILED` | 依赖安装失败，确认 Node.js / npm / 内网源 |
| `BUILD_FAILED` | 脚本编译失败 |
| `ENV_NOT_FOUND` | 缺少 `scripts/.env` |

后续命令一律：

```bash
cd "$SCRIPTS_DIR" && node dist/run.js <command> [options]
```

参数格式：`--key value`（`city-id` → `cityId`）。stdout 为 JSON。

截断自愈：本文件或 references 若出现「too long, see the full content at ...」，先用 Read 读完整原文件，禁止凭残缺内容发挥。

## 能力概览

| 能力 | 涉及工具 | 说明 |
|------|---------|------|
| 影片查询 | `recommend_hot_movies` / `search_movies` / `get_movie_detail` / `get_movie_show_days` | 热映榜单、关键词搜索、影片详情、可观影日期 |
| 影院查询 | `get_nearby_cinemas` / `search_cinemas` / `get_cinema_detail` / `get_cinemas_by_movie` | 附近影院、名称搜索、影院详情、按影片查影院 |
| 排片查询 | `recommend_nearby_shows` / `get_cinema_show` | 编排查排片（影片→影院）、单影院完整排片表 |
| 工具类 | `get_location` / `get_city_by_name` / `init` | 定位城市、城市名查 cityId、环境准备 |

## 参考文档

- **对话流程编排（SOP）**：@references/query-workflow.md —— 两个必要条件、入口判定、入口 A/B/C 完整步骤。**执行查询前必须先 Read 该文件**，严禁凭记忆压缩或跳步。
- **工具完整说明（参数/返回/坑）**：@references/api-overview.md
- **输出规范（卡片结构/字段规则/检查清单）**：@references/output-formats.md。**每次展示对应场景前，必须先 Read 该文件的对应小节**。

> 本技能文档只做能力索引。具体怎么调（流程顺序、入口判定、A1 筛选）查 query-workflow.md，具体调什么（参数、返回字段）查 api-overview.md，怎么展示查 output-formats.md。

## 输出规范（索引）

| 场景 | output-formats.md 对应小节 | 触发命令 |
|------|---------------------------|---------|
| 热映榜单 / 影片卡片 | 影片卡片（共用）/ 热映榜单 | recommend_hot_movies、search_movies |
| 单部影片详情 | 单部影片详情 | get_movie_detail |
| 影院列表 / 搜索结果 | 影院卡片（共用）/ 影院列表 | get_nearby_cinemas、search_cinemas |
| 影院排片页（含兜底标志处理） | 影院排片页 | get_cinema_show、recommend_nearby_shows |
| 场次列表 | 场次列表 | 场次展示 |

## 全局铁律（违反即渲染失败，任何场景优先遵守）

1. 影片海报必须用 `<media_info>[{"type":"image","description":"《片名》海报","url":"{poster或img}"}]</media_info>` 渲染；**严禁**裸链接、Markdown 图片 `![...](...)`、`<img>` HTML；`url` 取自本次接口返回值原样输出，禁止改写
2. 每部影片/每家影院一张独立卡片，卡片间用 `---` 分隔；**绝对禁止数字列表（1. 2. 3.）、禁止把多个字段挤到同一行**（规范明确允许的同行组合除外，如「地址+距离」）
3. 影院排片页**严禁展示海报**；场次行之间必须空行（无空行会全部挤成一行）
4. 场次/影院票价带「起」字（`💰 ￥35起`）
5. 展示前先自查 output-formats.md 对应小节的「⚠️ 检查清单」
