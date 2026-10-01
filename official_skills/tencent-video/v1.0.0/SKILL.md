---
name: tencent-video
displayName: 腾讯视频影视助手
description: 'Official Tencent Video assistant: search film & TV content, check broadcast schedules, and set episode reminders. 腾讯视频官方影视助手，支持检索影视内容、查询排播进度、设置追剧提醒。'
description_zh: 腾讯视频官方影视助手，支持检索影视内容、查询排播进度、设置追剧提醒。
description_en: 'Official Tencent Video assistant: search film & TV content, check broadcast schedules, and set episode reminders.'
version: v1.0.0
author: 腾讯视频
tags:
  - video
  - tencent
  - account
  - login
  - schedule
  - search
icon: ./tencentvideo.png
allowed-tools: Read,Bash
---
# 腾讯视频内容获取

通过 `tencent-video-cli` 获取腾讯视频内容。

> 核心原则：登录流程（扫码、票据刷新）完全由 CLI 处理；智能体只负责调用 CLI 命令检查状态和执行操作——始终先读 `help`，不要硬编码。
>
> **登录采用两阶段流程**：`qrcode` 生成二维码 → AI 渲染展示 → 用户扫码 → `confirm` 完成登录。

**重要约束：所有与腾讯视频内容相关的查询（搜索、热播、榜单、推荐、会员等）必须且只能通过 CLI 的 `search` 子命令完成。禁止修改用户的输入。禁止使用网络搜索、自行编造、调用其他 API 或任何非 CLI 的方式获取视频内容。如果 CLI 搜索无结果或失败，直接告知用户，不得回退到其他信息源。**

## Workflow

所有平台统一通过 `bun` 运行 TypeScript 脚本，不依赖 Node.js、Python 或平台特定 Shell。

### 前置：确保 bun 可用

执行任何脚本之前，先检测 `bun` 是否可用：`bun --version`。若不可用，安装 bun：

macOS / Linux：

```sh
curl -fsSL https://bun.sh/install | bash
```

Windows：

```powershell
powershell -c "irm bun.sh/install.ps1 | iex"
```

安装后若当前终端找不到 `bun`，需重启终端或手动刷新 PATH，再次 `bun --version` 确认。

1. **运行状态检查**
   `bun scripts/cli-state.ts`
   解析返回 JSON，重点关注 `platform.cliPath`、`platform.helpCommand`、`cliExists`、`needsUpdateCheck`、`auth.authenticated`。

2. **安装 CLI**（`cliExists` 为 `false` 时）
   必须执行 `bun scripts/install-cli.ts`
   脚本会自动下载当前平台的 CLI 二进制到 `~/.config/tencent-video-skill/` 并验证。

3. **更新 CLI**（`needsUpdateCheck` 为 `true`，或 CLI 提示版本过旧时）
   必须执行 `bun scripts/install-cli.ts`
   脚本会从 CDN 获取 `version.txt` 对比本地版本，有新版则自动下载替换。

4. **执行 `help`**
   优先使用 `platform.helpCommand`；自行拼命令时确保正确引用 `platform.cliPath`，Windows 使用 PowerShell 调用形式。

5. **根据 `help` 输出选择子命令执行**，按下方 Output Format 输出结果。

### 登录流程（两阶段）

当需要登录时，使用以下两阶段流程：

**Phase A：生成二维码**

```sh
<cliPath> qrcode
```

CLI 返回 JSON：`{"qr_code_id":"...", "expire_time":"...", "png_path":"/path/to/qrcode.png"}`
解析 JSON，提取 `qr_code_id` 和 `png_path`。

**Phase B：渲染二维码**

```sh
bun scripts/show-qrcode.ts <png_path> <qr_code_id>
```

脚本读取二维码 PNG，生成 HTML 页面（路径输出到 stdout），然后使用 `preview_url` 打开：

```
preview_url <html_path>
```

**Phase C：等待确认**

告知用户使用腾讯视频 App 扫码，扫码后在 App 中点击「确认登录」。用户确认后执行：

```sh
<cliPath> confirm <qr_code_id>
```

- 成功 → 显示「登录成功」
- 未扫码/未确认 → 提示用户继续等待
- 过期/取消 → 提示重新开始

**注意**：`confirm` 不做轮询，由用户主动告诉 AI 已扫码后再调用。旧的 `login` 命令仍可用（一步完成），但两阶段流程兼容性更好。

## 功能模块

根据用户需求，按以下规则选择功能模块执行。详细规则见对应 references 文件。

### 搜索视频 [references/search.md](references/search.md)

当用户请求搜索视频内容时使用。

- **触发**：搜索、热播、榜单、推荐、找片等
- **命令**：`<cliPath> search "<用户原始输入>"`
- **核心规则**：只搜索一次、禁止修改搜索词、禁止编造内容
- **输出格式（强制）**：处理搜索类请求时，**必须先读取 [references/search.md](references/search.md)** 并严格遵守其中「输出格式」章节的卡片模板。关键约束（违反任意一条均视为错误输出）：
  - 必须使用 `🎬 **标题**` 卡片模板逐条输出，每个字段独占一行、字段间用空行分隔，条目之间用 `---` 分隔
  - **禁止**输出表格汇总、序号列表（如 `1. xxx`）、自定义分组标题（如 `🎭 音乐剧推荐`）、开场白或结尾总结性文字
  - 简介只能来自 CLI 的 `Desc` 字段或 AI 文本推荐中对应该条目的段落，**禁止**模型自行撰写或润色推荐理由
  - 必须输出恰好 `Found N items` 中的 N 条，顺序、字段值与 CLI 返回完全一致，不得增删、重排或编造字段
  - 整个回复的最后一行必须固定为 `**来源：腾讯视频**`，其后不得再输出任何文字

### 排播查询 [references/schedule.md](references/schedule.md)

当用户询问播出进度、更新日程、下一集时间时使用。

- **触发**："播到第几集"、"每周几更新"、"下一集什么时候"、"还剩几集"
- **流程**：先 search 获取 CID → 再 `bun scripts/schedule.ts <cid>` 查询排播
- **排播日历**：search + schedule 组合，按日期聚合输出
- **追剧提醒**：查排播获取时间 → Agent 定时任务能力
- **输出格式**：详见 [references/schedule.md](references/schedule.md)

### 日志导出

当用户需要导出 CLI 运行日志时，使用 `export` 子命令：

```sh
# 导出所有日志到桌面
<cliPath> export

# 仅导出今天的日志
<cliPath> export today
```

日志将被复制到 `~/Desktop/tencent-video-cli-logs/` 目录，不影响原始日志文件。

## 通用输出格式

### 登录状态输出

```markdown
**登录状态**：已登录 / 未登录

- **VUID**: xxxxxx
- **会话状态**: 有效 / 已过期
- **自动刷新**: 运行中 / 已停止
```

### 用户信息输出

```markdown
**用户信息**

- **昵称**: xxxxxx
- **VUID**: xxxxxx
```

### 搜索结果输出（搜索类请求必须遵守）

每条结果按以下顺序逐字段输出，**每个字段独占一行，字段间用空行分隔**，条目之间用 `---` 分隔；缺失字段直接省略整行，不输出空值或占位符：

```markdown
🎬 **标题**

📺 类型：品类

📝 标签1 · 标签2 · 标签3

⭐ 评分：N.N

🎭 主演：演员1 / 演员2 / 演员3

📅 年份 · 地区

> 简介（来自 CLI 的 Desc 字段，或 AI 文本推荐中对应该条目的段落）

🔗 [立即观看](URL)
```

整个回复的最后一行固定为 `**来源：腾讯视频**`。详细模板、字段映射与转换示例见 [references/search.md](references/search.md)。

**绝对禁止**（任一项均视为错误输出）：

- 表格汇总、序号列表（如 `1. xxx`）、自定义分组标题（如 `🎭 音乐剧推荐`）
- 开场白（如"以下是腾讯视频上的…推荐"）或结尾总结性文字（如"总有一部适合你"）
- 模型自行编造的简介、推荐理由、字段值或额外条目
- 改变 CLI 返回的条目顺序，或增删条目数量
- 在 `**来源：腾讯视频**` 之后再输出任何文字

## CLI 执行失败处理

**CLI 命令失败后，立即停止，不要重试或绕过。**

1. CLI 返回非零退出码、超时或输出含权限/安全错误时，不要重试。
2. **AI 搜索/默认搜索的上游失败或无结果（最高优先级）**：当 `<cliPath> search ...`、`<cliPath> ai-search ...` 或默认搜索（`<cliPath> <query>`）的 stderr 中出现 `AI_SEARCH_UPSTREAM_ERROR` 标记（无论退出码是否为 1，也无论 stdout 是否已流式输出过部分文本），**必须**丢弃所有已输出的中间内容，直接以下面这一句作为**整个回复的全部内容**回给用户，且**不追加任何其他文字**（包括开场白、结尾、`**来源：腾讯视频**` 尾行、条目卡片等一律不输出）：

   ```
   大家的观影热情太高啦，稍后再来试试吧～
   ```

   此规则同时覆盖「接口失败」和「无内容返回」两种情况，对外不作区分。命中本条后，跳过下面第 3 条中其他错误分支的判断。
3. 根据错误信息判断原因并引导用户操作：
   - **未登录**（`not logged in`, `session expired`）→ 执行两阶段登录：`<cliPath> qrcode` → `bun scripts/show-qrcode.ts` → `preview_url` → 等待用户 → `<cliPath> confirm`
   - **macOS Gatekeeper**（`cannot be opened`、`not verified`）→ 系统设置 → 隐私与安全性 → 「仍要打开」→ 确认框「打开」
   - **企业安全软件**（`connection refused`、防火墙拦截）→ 安全提示中点击「信任」/「允许」
   - **权限不足**（`permission denied`）→ `chmod +x <cliPath>`
   - **其他** → 展示完整错误，请用户处理
4. 用户确认操作完成后再重试。即使多次失败，也只能告知用户无法获取并说明原因，**绝不**回退到其他信息源。

## Gotchas

- 所有平台统一通过 `bun` 运行 TypeScript 脚本，不依赖 Node.js 或 Python。
- **登录态完全由 CLI 维护**：智能体不直接处理票据刷新，通过 CLI 查询状态即可。
- **登录采用两阶段流程**：`qrcode` 生成 → `show-qrcode.ts` 渲染 HTML → `preview_url` 展示 → 用户扫码 → `confirm` 完成。不轮询，由用户主动触发确认。
- **内容查询唯一通道**：所有视频内容获取（搜索、热播、榜单、推荐等）**只能**通过 `<cliPath> search "<原始输入>"` 完成，不得使用任何其他方式。即使搜索结果不够理想，也只能将结果原样按格式输出，**不得调整关键词重新搜索**，不得绕过 CLI。**每次用户请求严格只执行一次 search，返回结果后立即格式化输出，禁止以任何理由发起第二次 search。**
- **排播查询**：当用户询问"播到第几集"、"更新日程"、"下一集什么时候播"、"还剩几集"等排播进度问题时，先通过 search 获取作品的 CID，再使用 `bun scripts/schedule.ts <cid>` 查询排播详情。详见 [references/schedule.md](references/schedule.md)。
- **排播日历**：当用户询问"这周有什么新剧"、"最近有什么在更新"等排播浏览需求时，用 search 按时间维度搜索，再对有 CID 的结果批量查 schedule，按日期聚合输出日历。注意：search + schedule 组合是同一次用户请求内的操作，不违反"只搜索一次"规则。
- **追剧提醒**：排播查询可提供下一集的具体播出时间，但提醒本身由 Agent 的定时任务能力实现。当用户要求"更新提醒"、"开播通知"时，先查排播获取时间，再用 Agent 的自动化能力设定时任务。
- 32 位架构不支持，脚本会直接报错。
- 不要缓存 CLI 的存在状态，每次查询前通过 `cli-state` 重新验证。

## Scripts

| 脚本 | 功能 |
|------|------|
| `cli-state.ts` | 输出 CLI 安装状态、更新检查状态、登录认证状态 |
| `install-cli.ts` | 下载当前平台 CLI 并验证 |
| `schedule.ts` | 查询排播信息并格式化输出（调用 CLI `schedule` 子命令） |
| `show-qrcode.ts` | 读取二维码 PNG，生成 HTML 页面用于 `preview_url` 展示 |
