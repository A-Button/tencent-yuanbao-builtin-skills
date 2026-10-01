---
name: book-recommender-bok
description: 图书搜索与推荐的本地 App Skill，基于精选书库提供关键词搜索和智能推荐。
keywords:
  - 图书推荐
  - 书籍搜索
  - 书单
packageType: app-skill
instructionOnly: false
metadata:
  version: v1.0.1
  openclaw:
    requiresNetwork: false
    dataClassification: public-data
version: v1.0.0
---

# 图书推荐

## 角色与入口

完全本地的图书搜索与推荐 Skill，无远程服务依赖。内置 20 本精选经典图书，覆盖文学、科幻、历史、科普、心理学、推理、传记、哲学 8 个类别。

Agent 入口（沙箱内 `app` 即 `/data/skills/bin/app`）：

```bash
app book-recommender <tool_name> '<json>'
```

列出当前可见工具：

```bash
app book-recommender toollist
```

查询任意工具的输入 schema 与调用方式：

```bash
app book-recommender describe
```

参数不确定时先 `app book-recommender describe`，禁止猜字段。

## 执行优先级（严格约束，单一真源）

1. **Schema 优先**：首次调用或参数不确定时，先 `app book-recommender describe`。
2. **只走统一 CLI**：禁止直接执行 `list_books.py`、`search_books.py`、`recommend_books.py`，只有 `app` 才会产出 `__ONEAGENT_APP_RESULT__`，UI 才会上屏。
3. **调用过程不可见**：回复不展示脚本名、命令、参数、原始返回或错误堆栈。

## 工具一览

| 工具名 | 用途 | 关键参数 |
|---|---|---|
| `list_books` | 查看全部图书与可用类别 | 无 |
| `search_books` | 按关键词搜索（匹配书名或作者） | `query` 必填 |
| `recommend_books` | 获取推荐（可按类别筛选） | `category` 可选，`count` 可选（默认 5） |

调用方式：

```bash
app book-recommender list_books '{}'
app book-recommender search_books '{"query": "三体"}'
app book-recommender recommend_books '{"category": "科幻", "count": 3}'
```

## Agent 使用指南

- `search_books`：用户问"有没有 XXX 书"、"搜一下 XXX"、"找 XXX 写的书"时使用。
- `recommend_books`：用户说"推荐几本书"、"有什么好书"、"推荐科幻类的"时使用。不指定 `category` 则全类别按评分推荐。
- `list_books`：首次打开或用户想浏览全部书库时使用。

## 字段说明

- `query`：搜索关键词，`search_books` 必填，同时匹配书名和作者名。
- `category`：推荐类别，可选值见 `list_books` 返回的 `categories` 数组。不传则全类别推荐。
- `count`：推荐数量，1-20，默认 5。

## 常见坑

1. 直接执行 handler 脚本不会产生 `__ONEAGENT_APP_RESULT__`，UI 不会刷新。
2. 搜索无结果时告诉用户"没有找到匹配的图书，试试换个关键词"，并给出类别建议。
3. `recommend_books` 不指定 category 时默认按评分从高到低推荐。
4. `recommend_books` 的 count 上限为 20。

## 沟通规则

- 默认简体中文，回复简洁。
- 搜索结果以书名、作者、评分、简介的形式简短呈现。
- 推荐时附带简短推荐理由（高评分、经典之作等）。
- 可主动告知用户有哪些类别可选。