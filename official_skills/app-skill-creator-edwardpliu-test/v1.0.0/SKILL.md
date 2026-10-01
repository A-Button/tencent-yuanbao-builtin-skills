---
name: app-skill-creator-edwardpliu-test
description: 创建或改造带交互式 UI 的 OneAgent App Skill。当需要新建 App Skill、给已有 Skill 加 ui:// 页面、编写或修订 assets/app.yaml、实现 iframe 侧的 MCP Apps bridge、或把一个 Web 页面改造成对话内可展示的 App 时使用。产出物是一个含 SKILL.md、app.yaml、tool handler 与单文件 HTML 的 skill 包，不是 MCP server。不带界面的普通 skill 不要用它，改用 skill-creator。桌面卡片小组件（天气、航班、番茄钟；参数由后端注入、卡片自己拉数、tool 可选）请用 widget-skill-creator。
version: v1.0.0
---

# 创建 App Skill

App Skill 是**加了 UI 和 app.yaml 的普通 skill**。iframe 那一侧遵循 MCP Apps 协议，服务端那一侧不是 MCP server，而是 `app.yaml` 里声明的沙箱脚本。

## 动手之前：先问清四件事

**在读其余章节、动任何文件之前**，按顺序把下面四件事问明白。用环境提供的提问工具
（`ask_user_question` / `AskQuestion` 之类）发问；没有这类工具就直接在回复里问，然后等回答。

**一次只问一个**，拿到回答再问下一个。这四件事都会改变整包的结构、构建链路和测试，
问一次成本很低；猜错则全部返工。

### 1. 需求本身

用户的第一句话通常只是个方向（"做个记账的"），不足以定下数据模型和界面。先把它问成一个
具体的东西。挑**当前最不确定、且会影响结构**的那一个问，答完再问下一个，别一次抛一串：

- 谁在什么场景下用？是自己随手记，还是给别人看的报表？
- 核心是哪一类记录？一条记录上有哪些字段，哪些是必填？
- 主要动作是什么？只读展示，还是要增删改？
- 卡片首屏最该看到什么？是最近几条、汇总数字，还是一个待办提醒？
- 数据从哪来？用户手输、Agent 写入，还是要调外部 API / MCP？

用户说"你看着办"时，就按最小可用的形态定下来，并把你的假设明确讲出来，让他有机会纠正——
不要沉默地替他决定。

### 2. 要不要界面

> 这个 skill 需要在对话里显示一个可交互的界面吗？

| 回答 | 怎么做 |
|---|---|
| 需要，而且是完整增删改 / 多页工作区 | 继续本 skill |
| 需要，但是桌面上扫一眼的卡片（自己拉数、tool 可选） | **本 skill 到此为止**，改用 `widget-skill-creator` |
| 不需要 | **本 skill 到此为止**，改用 `skill-creator` 创建普通 skill。不要给普通 skill 套上 `app.yaml`、`ui://` 资源和 bridge |

不要替用户推断。用户描述里出现「列表」「看板」「图表」不等于要 UI，没提界面也不等于不要。

### 3. 卡片用哪种技术

> 对话里那张卡片用 A2UI 组件描述，还是和全屏页一样用 H5？

| 回答 | `--ui-mode` | 产物 |
|---|---|---|
| 卡片 A2UI + 全屏 H5（**推荐**） | `a2ui` | `card.json`（卡片）+ `workspace.html`（全屏），卡片里用 `open_workspace` 引过去 |
| 全部用 H5 | `h5` | 一份 `index.html` 兼任卡片与全屏，形态差别由 `displayMode` 表达 |

**默认推荐 A2UI 做卡片、H5 做全屏**，因为两种形态的诉求本来就不同：

- **卡片**多是纯视觉展示加简单交互。A2UI 由端上引擎按组件树直接渲染，不起 iframe、不加载
  HTML/JS，性能更好，跨端观感也一致。
- **全屏**要放得下完整信息和复杂操作。H5 能做出更精细的界面，又能通过 bridge 和 Agent 做
  复杂交互，上限高得多。

用户明确说「都用 H5」「不想写组件树」，或者卡片本身就需要复杂交互/自定义绘制时，才选 `h5`。

选了 `a2ui` 就读 [references/a2ui_card.md](references/a2ui_card.md)，那里有组件树的写法与协议
约束。全屏那份仍是普通 H5，走本文其余章节。

### 4. 数据怎么存

> 这个 skill 需要把数据留下来吗？下次打开还要看到吗？

不需要持久化的（纯展示、纯计算、每次都从外部 API 取）就别建存储层，让 handler 保持无状态。

需要的话再问一个：

| 回答 | `--store` | 什么时候选 |
|---|---|---|
| JSON 文件（**默认**） | `json` | 记录数在几百条以内，整体读写，字段结构简单 |
| SQLite | `sqlite` | 记录会累积到几千条以上，或需要按条件筛选、排序、分页、跨表关联 |

两者都落在**持久卷** `/data/user/<app-id>/` 下，这是硬约束：Agent 沙箱与 App 沙箱各有
各的 home，只有这里是同一份。存到 `~/` 会导致「Agent 写的记录 UI 看不到」。本地模式下
没有这个挂载，脚手架会自动退到 `~/.one-agent/data/<app-id>/`——本地不存在双沙箱，共用
一个 home 反而是对的。

浏览器的 `localStorage` **不能**用来存业务数据——它只活在 iframe 里，Agent 读不到。只有折叠
状态、上次选中的 tab 这类纯 UI 偏好才可以放那里。

## 分层

```text
SKILL.md              给模型看的说明：何时用、怎么调、字段与边界
assets/app.yaml       资源与工具声明，把 tool 绑到 A2UI 或 H5 资源
scripts/<tool>.py     领域 API，确定性逻辑与持久化
assets/ui/index.html  单文件 iframe UI，内联 MCP Apps bridge
```

两条调用链应共用同一份 `app.yaml` 与同一份领域 API：

```text
模型  → app <id> <tool> '<json>' → worker 子进程 → 同名函数(args) / function 覆盖
        stdout → 模型；return dict → CLI 旁路结果 → UI
iframe → tools/call → AppGateway → 同一函数执行契约 → app.data → tool-result
```

部署新包前确认 sandbox 的 `app` 已支持 `handler.type: python`。UI 直调的 Gateway 也必须调用新版 CLI 或等价 worker；旧的“直接执行脚本并解析 stdout”入口不能执行新契约，不能仅凭 CLI 测试通过就认为页面回调已支持。

## 目录

```text
<app-id>/
├── SKILL.md
├── package.json              build:ui 与 test
├── assets/
│   ├── app.yaml
│   └── ui/
│       ├── index.template    源文件，含 /*__MCP_BRIDGE__*/ 占位
│       └── index.html        构建产物，app.yaml 指向它
├── scripts/
│   ├── <tool>.py             handler，默认函数名与 tool.name 相同
│   ├── ui_bridge_entry.js    esbuild 入口
│   └── build-ui.mjs
└── tests/
```

`--ui-mode a2ui` 只有 `assets/ui/` 这一层不同，其余完全一样：

```text
assets/
├── app.yaml                  两条 resources：a2ui 卡片 + h5 工作区
└── ui/
    ├── card.json             A2UI 组件树，对话里那张卡片
    ├── workspace.template    全屏页源文件，含 /*__MCP_BRIDGE__*/ 占位
    └── workspace.html        构建产物
```

卡片不进 iframe、不参与构建，所以 `build:ui` 这时构建的是 `workspace.html`。

沙箱 CLI `app` 的调用形式、校验顺序与它产出的旁路记录见 [references/cli.md](references/cli.md)。

## 起步

产物**默认落在当前工作区**，不要装到用户本机。`--path` 指向工作区根目录（用户指定了工作区内子目录则用那个）；不要用本 creator 自己的目录，也不要写到 `~/.one-agent`、`/tmp` 或其它工作区之外的位置。

```bash
scripts/init_app_skill.py <app-id> --path <工作区根目录> --name "<展示名>" --entity <实体单数> \
  --ui-mode <h5|a2ui> --store <json|sqlite>
cd <工作区>/<app-id> && npm install && npm run build:ui && npm test
```

生成的是一份可运行但业务是占位的骨架（title/notes 的增删改查）。**先替换领域模型再动 UI**：改各 handler 与共享存储层，再同步 `app.yaml` 的 `inputSchema`。

选 `--store sqlite` 时 handler 走行级 SQL（建表在首次连接时自动完成），出参形状与 JSON 版
完全一致，所以 UI、卡片和包内测试都不用区分。改领域模型时记得连 `CREATE TABLE` 的列一起改。
记录很多时把 `_rows()` 换成带 `WHERE` / `LIMIT` 的查询，别把整表都塞进快照。

## 硬约束

以下每一条都对应一类「装进去才发现」的故障，不要在具体项目里放宽。

**1. id 三处必须一致**：目录名 = `app.yaml` 的 `id` = `SKILL.md` frontmatter 的 `name`。`id` 还是挂载目录 `/data/skills/<id>` 和 `ui://<id>/...` 的键。`id` 不能含连续下划线 `__`。

**2. `resourceUri` 与 `visibility` 必须写在 `_meta.ui` 下**：

```yaml
tools:
  - name: create_note
    handler: { type: python, path: scripts/create_note.py }
    _meta:
      ui:
        resourceUri: ui://my-notes/main
        visibility: [model, app]
```

写在 tool 顶层会被后端 manifest 解析静默忽略，表现为「工具能跑但 UI 永远不挂载」。

**3. 需要 UI 或宿主集成的 App 工具走统一 CLI**：`app <id> <tool> '<json>'`。直接执行 handler 脚本，UI 拿不到数据、界面不会刷新。SKILL.md 必须说明这些工具通过 `app` 调用。普通业务辅助、构建、迁移和测试脚本按各自的命令直接执行，不要求出现在 `app.yaml.tools` 中，也不要求通过 `app`。

**4. 一个操作一个 tool**：查询、新增、更新、删除各自是一个 tool（`list_notes`、`create_note`、`update_note`、`delete_note`），**不要**合成一个 `notes_api` 再用 `operation` 参数分派动作。合起来写会连锁地毁掉校验：`inputSchema` 只能取所有操作字段的并集，`required` 退化成只能要求 `operation` 自己，`additionalProperties: false` 也拦不住「删除时传了 title」——因为 `title` 确实声明过；而按操作变化的必填又没法表达，CLI 的校验器不实现 `if`/`then`/`oneOf`。于是校验只能整块塞回 handler，模型面前也只剩一个语义模糊的工具。拆开之后每个 tool 各自声明字段与必填，CLI 就能替你把绝大多数错误入参拦在 handler 之前。

`app <id> <tool>` 按 `handler.path` 加载模块，默认调用与 `tool.name` 同名的函数；有 `handler.function` 时严格使用其值，传入参数字典。多个 tool 可以共用一个文件，通过默认同名函数或 function 覆盖指向独立入口；每个操作仍有独立的 inputSchema。共享存储、加锁、错误信封可放在同一模块或单独的共享模块中。

**5. 入参校验尽量交给 `app.yaml`，handler 只补它表达不了的**：字段白名单（`additionalProperties: false`）、类型、枚举、长度与数值范围都写进 `app.yaml`，不要在脚本里重写一遍；按上一条拆开 tool 之后，必填也交给各自的 `required`。CLI 不实现 `pattern`/`format`，未知关键字被静默忽略，所以「去掉空白后不能为空」「跨字段一致性」「记录是否存在」这类仍然留在 handler。校验能力清单见 [references/cli.md](references/cli.md)。

**6. 数据放持久卷，不放 home**：Agent 沙箱与 App 沙箱是两个沙箱、各有各的 home，但挂同一份 `/data/user`。写到 `Path.home()` 下会导致「Agent 建的记录 UI 看不到」。只有本地模式（没有这个挂载、也不存在双沙箱）才退到 `~/.one-agent/data/`，这条回退由存储层自己判断，不要写死路径。

**7. UI 必须是单文件且完全自包含**：Host 通过 `GET /app/resource` 整份取走 HTML 塞进 iframe，页面没有同源服务器，CSP 也会拦掉 CDN。第三方库一律在构建期内联。

**8. 模型输出与 UI 返回值分开**：新 handler 声明 `type: python`，默认调用与 tool 同名的同步函数，也可用 `function` 覆盖，如 `create_note(args: dict) -> dict | None`。仅当 `function` 字段不存在时使用 tool.name；显式 null、空值或非法名称均报错。有效函数名须为非关键字的 Python 简单标识符，不支持点分路径或 `entrypoint`；tool 名不合法时需显式 function 覆盖，函数找不到不尝试其它名称。stdout 给模型，`return` 给 UI，stderr 写日志；函数返回字典必须可严格 JSON 序列化，`None` 表示无 UI 更新，`{}` 仍是有效 UI 结果。写操作返回 UI 全量快照，stdout 只保留本次变更及必要 ID；查询 stdout 要保留模型后续操作需要的记录明细。不要在导入模块时执行业务、解析 `sys.argv` 或打印；入口不要 `sys.exit()`。共享模块可从 handler 所在目录或 skill 根目录导入。worker 管理结果文件与进程隔离，业务不拼 marker、不读写内部结果文件。完整契约见 [references/cli.md](references/cli.md)。

**9. bridge 必须先注册 handler 再 `connect()`**：`connect()` 期间到达的首个 tool-result 会丢。

**10. 产物只留在当前工作区，禁止自行装机**：默认生成到工作区里的 `<app-id>/`。交付就是报告这条路径。不要执行 `register_local_app.py`，不要复制到 `~/.one-agent/skills`。用户自己明确说「装到本机」之前，装机不在范围内。

**11. 资源 URI 按类型命名**：`mimeType: application/a2ui+json` 的资源必须使用 `ai_apps.skills.{skill_name}_{页面名}_res`。`skill_name` 取 frontmatter 的 `name`（与 app id 一致），将 `-` 转为 `_`；页面名用小写 snake_case，脚手架卡片默认为 `card`。默认页也允许省略页面名，如 `ai_apps.skills.book_recommender_res`。H5 仍使用 `ui://<app-id>/<view>`。所有工具的 `_meta.ui.resourceUri` 必须与对应资源 URI 完全一致。混合资源示例见 [references/app_yaml.md](references/app_yaml.md#资源-uri-命名)。

## 工作流

1. **先看目标仓库**。复用其中的命名、构建方式、测试约定与持久化路径，不要另起一套。
2. **定视图与工具边界**。列清每个 A2UI / H5 资源对应什么用户任务、由哪个 tool 触发挂载、iframe 能调哪些 tool。多视图选型见 [references/app_yaml.md](references/app_yaml.md)。
3. **定领域模型与 tool 清单**：一个操作一个 tool，每个 tool 在 `app.yaml` 里声明只属于自己的 `inputSchema`，通过 `handler.path` 与 tool 同名函数（或 `handler.function` 覆盖）指定入口，允许多个工具共用文件。
4. **实现 handler**：实现默认同名或 `handler.function` 指定的同步函数，接收一个参数字典，stdout 输出模型结果并返回 UI 字典。所有改数据的路径都经领域 API；预期业务错误返回 `{"phase":"error","code","message","retryable"}` 并向 stdout 说明，意外异常交给 worker，不能吞掉后报告成功。
5. **实现 UI 与 bridge**，细节见 [references/ui_bridge.md](references/ui_bridge.md)。
6. **构建并测试**：`npm run build:ui && npm test`，再跑校验。
7. **交付**：报告工作区里的产物路径与测试结果，到此结束。不要装到本机。见 [references/testing_and_delivery.md](references/testing_and_delivery.md)。

## 校验

```bash
scripts/validate_app_skill.py <app-dir>
```

检查 id 一致性、按 MIME 类型区分的 URI 命名、`resourceUri` 闭环与字段位置、handler 与资源路径存在、python handler 声明的同步函数入口、构建产物是否过期或残留外链、SKILL.md 是否教了正确的调用方式。它不验证业务正确性，业务用生成包里的 `tests/`。

## 交付前自检

- [ ] `validate_app_skill.py` 无 error
- [ ] `npm run build:ui && npm test` 通过
- [ ] 浏览器打开 `assets/ui/index.html?preview` 与 `?preview&theme=dark`：首屏可见、无横向溢出、文本不重叠、主要操作可点
- [ ] 产物在当前工作区的 `<app-id>/` 下
- [ ] 面向用户的回复里没有出现命令、marker、id 或堆栈
