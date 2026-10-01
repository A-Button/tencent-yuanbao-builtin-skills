# app.yaml 参考

`app.yaml` 是 App Skill 的清单。它同时被四个角色读取，字段写错的后果各不相同：

| 读取方 | 读什么 | 写错的表现 |
|---|---|---|
| `load_skill` | `resources[]` | 资源列表下发不出去，Host 无从预加载 |
| 沙箱 CLI | `tools[]` 的 `inputSchema` / `visibility` / `handler` | 入参校验失效或工具找不到 |
| AppGateway | `resources[].path` | iframe 拉不到 HTML，白屏 |
| Agent 结果拆包 | `_meta.ui.resourceUri` | 工具能跑但 UI 永远不挂载 |

## 资源 URI 命名

- A2UI（`application/a2ui+json`）：使用 `ai_apps.skills.{skill_name}_{页面名}_res`。`skill_name` 取与 app id 一致的 SKILL.md `name`，将 `-` 转为 `_`；页面名使用小写 snake_case（如 `card`、`search_results`），不同页面使用不同 URI。脚手架默认生成 `ai_apps.skills.book_recommender_card_res`。
- 默认页允许省略页面名，使用 `ai_apps.skills.{skill_name}_res`，如下面的图书推荐卡片。
- H5（`text/html;profile=mcp-app`）：保持 `ui://<app-id>/<view>`，app id 保留原来的连字符。

例如 `id: book-recommender` 的混合资源：

```yaml
resources:
  - uri: ai_apps.skills.book_recommender_res
    name: 图书推荐
    description: 搜索与推荐结果的卡片视图
    path: assets/ui/card.json
    mimeType: application/a2ui+json
  - uri: ui://book-recommender/workspace
    name: 图书推荐详情
    description: 图书搜索与推荐的全屏界面，展示搜索框、分类筛选与完整书单
    path: assets/ui/workspace.html
    mimeType: text/html;profile=mcp-app
```

绑定卡片的工具须设置 `_meta.ui.resourceUri: ai_apps.skills.book_recommender_res`；卡片的 `open_workspace` 仍指向 `ui://book-recommender/workspace`。修改已有 URI 时同步修改所有引用，不能只改资源声明。

## 完整形态（H5）

```yaml
id: my-notes                          # 目录名 / SKILL.md name / ui:// 前缀，三处一致
name: 我的笔记                         # 展示名，进 app.resource
version: v1.0
description: 一句话说明               # 可选

resources:
  - uri: ui://my-notes/main           # 资源标识，不是浏览器 URL
    name: 我的笔记
    description: 笔记列表界面          # 可选
    path: assets/ui/index.html        # Gateway 读磁盘用，不下发 Host
    mimeType: text/html;profile=mcp-app   # 必须完全一致
    _meta:                            # 可选扩展，原样透传进 app.resource
      ui:
        permissions:
          geolocation: {}

tools:                                # 一个操作一个 tool
  - name: list_notes
    title: 查看笔记                    # 可选展示名
    description: 列出全部笔记
    inputSchema:                      # CLI 据此校验入参
      type: object
      properties: {}
      additionalProperties: false
    outputSchema:                     # 可选，约束 structuredContent
      type: object
      additionalProperties: true
    handler:
      type: python
      path: scripts/notes_api.py
    _meta:
      ui:
        resourceUri: ui://my-notes/main
        visibility: [model, app]
  - name: create_note
    title: 新建笔记
    description: 新建一条笔记
    inputSchema:
      type: object
      properties:
        title: { type: string, minLength: 1 }
      required: [title]               # 每个 tool 只声明自己的必填
      additionalProperties: false
    handler:
      type: python
      path: scripts/notes_api.py
    _meta:
      ui:
        resourceUri: ui://my-notes/main
        visibility: [model, app]
```

## 字段位置：只认 `_meta.ui`

`resourceUri` 和 `visibility` **必须**放在 `tools[]._meta.ui` 下。后端 manifest 的 tool 结构只从 `_meta.ui` 读这两个字段，没有顶层入口；写在顶层不会报错，只会静默失效。仓库里已有几个包踩了这个坑。

## visibility

| 取值 | 含义 |
|---|---|
| `model` | Agent 可调 |
| `app` | iframe 可直调（不经模型） |

不声明时默认 `[model, app]` 全开放。因此**交易类、不可逆或需要用户在页面上确认的动作，必须显式写 `visibility: [app]`**，只靠 SKILL.md 的文字约束拦不住模型。

至少要有一个 tool 含 `model`，否则 Agent 无从触发首次挂载。

## inputSchema

CLI 按它校验入参，所以它是防止模型瞎传字段的第一道闸。能写进 schema 的就别在脚本里重写一遍。

- `additionalProperties: false` 能让模型的错别字立刻失败而不是被静默丢弃，推荐保留。
- `required` 只能表达无条件必填。这正是**一个操作一个 tool** 的理由：`create_note` 要 `title`、`update_note` 要 `id`，各自成 tool 就都是无条件必填，写进各自的 `required` 即可；挤在一个 tool 里就只能靠 `if`/`then`、`oneOf` 表达，而 CLI 的校验器不实现它们，写了会被静默忽略，校验只能整块塞回 handler。
- CLI 不实现 `pattern`/`format`，所以「去掉空白后不能为空」这类仍要 handler 自己兜。
- 完整的支持范围与职责分界见 [cli.md](cli.md)。

## 单视图还是多视图

先回答一个问题：**悬浮态和全屏态是同一个界面的不同密度，还是两个不同的任务界面？**

**同一界面**：声明一个 `ui://<id>/main`，由 `hostContext.displayMode` 驱动布局，UI 在 `new App(..., { availableDisplayModes: [...] })` 里声明实际支持的展示态。这是默认选择。

**不同任务界面**：例如摘要卡片与完整编辑器。声明两个资源并各配一个入口 tool：

```yaml
resources:
  - uri: ui://my-trip/inline
    path: assets/ui/inline.html
    mimeType: text/html;profile=mcp-app
  - uri: ui://my-trip/fullscreen
    path: assets/ui/fullscreen.html
    mimeType: text/html;profile=mcp-app

tools:
  - name: show_trip_summary
    handler: { type: python, path: scripts/trip_api.py }
    _meta:
      ui: { resourceUri: ui://my-trip/inline, visibility: [model, app] }
  - name: open_trip_planner
    handler: { type: python, path: scripts/trip_api.py }
    _meta:
      ui: { resourceUri: ui://my-trip/fullscreen, visibility: [model, app] }
```

两个入口可以放在同一个 `scripts/trip_api.py` 中，分别默认调用 `show_trip_summary(args)` 与 `open_trip_planner(args)`；也可用 `handler.function` 覆盖函数名；也可拆分文件并 import 共享领域逻辑。`displayMode` 只描述**已挂载视图**的容器形态，不能在 iframe 内把当前资源换成另一个 uri —— 选哪个资源发生在 Host 读取 HTML 之前。

## 一个操作一个 tool

查询、新增、更新、删除各自是一个 tool，**不要**合成一个 `notes_api` 再用 `operation` 参数分派。合起来写会连锁地毁掉校验：`inputSchema` 只能取所有操作字段的并集，`required` 退化成只能要求 `operation` 自己，`additionalProperties: false` 也拦不住「删除时传了 `title`」——因为 `title` 确实声明过。模型面前也只剩一个语义模糊的工具，选错动作的概率更高。

一个操作一个 tool 不等于一个 tool 一个文件。每个 Python handler 的 `path` 定位模块，默认调用与 `tool.name` 同名的同步函数。`function` 可选：只有字段未出现时采用默认值，显式提供时严格使用其值，`null`、空字符串或非法标识符均报错。解析后的函数名必须是非关键字的 Python 简单标识符，不接受点分路径；tool 名不是合法函数名时，必须用合法 function 覆盖。目标函数不存在或不可调用也不会回退。多个 tool 可共用 path，通过默认同名函数或显式覆盖分开入口。CLI 的 worker 只把参数字典传给函数，不自动注入 tool 名；共享存储、加锁与错误信封可在同模块复用，也可从 `scripts/_store.py` 导入。handler 所在目录及 skill 根目录都在 worker 的 `sys.path` 中。辅助脚本不需要注册为 tool。

`handler.type: python` 使用新函数契约：stdout 给模型，`return dict` 给 UI，`None` 不产生 UI 更新；不支持 `entrypoint` 配置。省略 type 或 `type: script` 保留旧协议（子进程执行脚本，stdout 是完整 JSON），仅用于兼容现有工具。新包使用 `python`，先升级 sandbox CLI 与页面回调执行入口。不要把现有脚本只改 type 就迁移，必须同时实现对应同步函数；函数名不同于 tool.name 时填写 `handler.function`。

真正需要合并的只有一种情况：两个动作除了名字之外，入参、必填和返回完全一致。那说明它们本来就是一个操作。
