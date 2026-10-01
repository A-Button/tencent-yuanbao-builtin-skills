# 场景 10：跨会话长期记忆（远端 Hy-Memory：用户偏好 / 事实 / 经验）

> 让 LLM 跨会话「记得」用户是谁、用户的偏好、踩过的坑。
---

## 🎯 适用情况
- 多 agent 共用一个跨会话长期记忆库，按用户身份隔离
- 用户主动表达**偏好**（领域、术语、检索范围、回答风格、工作流、禁忌）
- **沉淀零碎事实 / 知识 / 经验**，并能按语义搜索召回
- **工具调用出错或多次重试仍不正确，经用户指引修正后，把纠正经验回灌到远端记忆**
---

## 🧭 数据模型
### 写入 / 检索协议
- 调用方写入**纯文本片段**，服务端用 LLM 自动解析出 `category` / `tags`，归入合适分组。
- 检索时按 `query` 做语义搜索，返回 3-key 分组结果。

### 检索分组
| 分组 | 含义 | 来源举例 |
|------|------|---------|
| **profile** | 用户画像 / 偏好 / 身份 / schema | `category` ∈ {profile, identity, schema} |
| **proactive** | 主动意图（仅 ultra 模式有内容） | `category` = intention |
| **normal** | 事实 / 知识 / 经验等通用条目 | `category` ∈ {fact, knowledge, summary, raw} |

> 调用方写入时**不需要**手动选分组，服务端会自动判定。
---
## ⚙ 调用规约（MUST，全局生效）
| 时机 | 操作 | 命令 |
|------|------|------|
| **前置 search** | 调用任何 `iwiki-cli` 子命令前，**或调用其它任何工具前** | `iwiki-cli memory search "<本任务关键词>"` |
| **同步偏好** | 用户明确表达偏好（语言、范围、风格等） | `iwiki-cli memory write --content "用户偏好：……"` |
| **错误回灌** | **任意工具**调用出错 / 多次重试仍不对，经用户指引修正后 | `iwiki-cli memory write --content "经验教训：<现象> → <指引> → <正确做法>"` |

> 「前置 search 是规约不是建议」：每次任务开始前都建议用本任务相关关键词检索一次远端记忆，把命中的偏好 / 经验注入决策；适用范围**不限于 iWiki 工具**，调用其它任何工具前也应先 search。

---
## 🛠 命令详解
### `memory write`
写入一条纯文本长期记忆。
```bash
# 直接传内容
iwiki-cli memory write --content "用户偏好：默认中文回答，代码保留英文"
# 从文件读
iwiki-cli memory write --content-file ./lesson.txt

# 输出 JSON（默认输出单行人类可读）
iwiki-cli memory write --content "..." --json
```
### `memory search`
按 `query` 语义检索长期记忆，**输出固定为 JSON**。
```bash
# 检索
iwiki-cli memory search "用户的编程偏好"

# 限制 normal 分组返回上限
iwiki-cli memory search "胰腺癌" --limit 10
```
> 失败响应：`{ "success": false, "error_code": <int>, "error_message": "..." }`，HTTP 始终 200，CLI 退出码为 1。

---

## 🧪 调用模板（脚本场景）
### 1) 前置 search
```bash
# 在任务开始前查一下相关偏好 / 经验
RESP=$(iwiki-cli memory search "代码风格偏好")
echo "$RESP" | jq '.memories.profile[]?.content'
echo "$RESP" | jq '.memories.normal[]?.content'
```

### 2) 同步偏好
```bash
iwiki-cli memory write --content "用户偏好：默认中文回答，代码与命令保留英文，禁止解释式翻译注释"
```

### 3) 错误回灌
```bash
iwiki-cli memory write --content "经验教训（iwiki-cli search 误用）：
- 现象：直接 search 关键词命中率低
- 指引：术语类查询应优先 \`iwiki-cli glossary <kw> --exact\`
- 正确做法：先 glossary 精确匹配，再退化到 search
"
```

---
## 🐛 常见错误对照
| 错误信息 | 原因 | 处置 |
|---------|------|------|
| `query 不能为空` | search 缺少位置参数 | 提供非空 query |
| `--content 与 --content-file 互斥` | write 同时传了两个内容来源 | 只保留一个 |
| `必须通过 --content 或 --content-file 指定记忆内容` | write 没传内容 | 至少提供其中一个 |
| `搜索失败 / 写入失败 code=10001` | 鉴权失败（`x-tai-identity` 未注入或解密失败） | 重新 `auth login` 登录 |
| `搜索失败 / 写入失败 code=10002` | 远端 Hy-Memory 服务异常 | 稍后重试，或联系服务方 |

