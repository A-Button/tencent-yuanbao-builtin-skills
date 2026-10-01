# 沙箱 CLI `app`

需要 UI 或宿主集成的 App 工具通过 `app` 执行；没有此需求的普通脚本直接执行，不必声明成 App 工具。沙箱里的 `app` 即 `/data/skills/bin/app`，本仓库的实现是 [`../../bin/app`](../../bin/app)。

## 命令与运行环境

```bash
app <skill> toollist          # 列出当前 caller 可见的工具
app <skill> describe          # 工具的 inputSchema 与调用方式
app <skill> <tool> '<json>'   # 执行工具
```

`describe` 与 `toollist` 从 `app.yaml` 生成，不需要业务实现。`ONEAGENT_SKILLS_ROOT` 指定 skill 根目录（沙箱里是 `/data/skills`）；`ONEAGENT_APP_CALLER` 取 `model` 或 `app`，用于按 `visibility` 拦截，不设置则不按身份拦。

新增 skill 只需安装到约定目录，CLI 根据 manifest 动态加载，不用逐个更新 CLI。新函数契约要求 sandbox 先安装支持 `handler.type: python` 的版本。UI 的 AppGateway 也要经新版 CLI 或相同 worker 执行；仍通过旧的“执行脚本、解析 stdout”入口调用页面工具时，需要先改造该入口。

## Python handler：stdout 给模型，return 给 UI

新工具声明文件，默认调用与 `tool.name` 同名的函数。以下工具调用 `create_note(args)`，不配置 `entrypoint`：

```yaml
name: create_note
handler:
  type: python
  path: scripts/notes_api.py
```

业务文件提供对应的同步函数：

```python
import json


def create_note(args: dict) -> dict:
    note = save_note(args["title"])
    notes = read_notes()
    # 模型需要本次变更及后续操作所需的 ID。
    print(json.dumps({"note": note, "count": len(notes)}, ensure_ascii=False))
    # UI 需要完整快照，业务函数不处理传输信封。
    return {"note": note, "notes": notes, "count": len(notes)}
```

`save_note` / `read_notes` 代表业务层函数，真实工具需要导入或实现它们。只有 `handler.function` 字段不存在时，函数名才默认取 `tool.name`；需要不同名称时可以显式覆盖：

```yaml
name: create_note
handler:
  type: python
  path: scripts/notes_api.py
  function: add_note
```

此时仅调用 `add_note(args)`，即使模块有 `create_note` 也不会回退。显式 `null`、空字符串或非法名称直接报错。解析后的函数名必须是非空 Python 简单标识符（满足 `str.isidentifier()` 且不是关键字），不支持 `notes.create_note` 这样的点分路径；tool 名含连字符等不合法字符时，需显式配置合法的 function。多个 tool 可以用同一 path，通过默认同名函数或显式 function 选择入口，每个 tool 保留自己的输入 schema。

| 出口 | 契约 |
|---|---|
| stdout | 模型内容，可自然语言或精简 JSON；不要输出 UI 完整快照，除非模型确实也需要这些信息 |
| `return dict` | UI 的 `structuredContent`；须可严格 JSON 序列化，不含自定义对象、NaN、Infinity 等 |
| `return None` | 本次没有 UI 更新；stdout 仍可返回模型，`{}` 与 `None` 含义不同 |
| stderr | 日志、warning、异常诊断，不能当作结构化数据通道 |

stderr 是日志通道，但部分宿主会将它合入模型文本，因此不保证日志仅工程可见。业务 stdout / stderr 中以 `__ONEAGENT_APP_RESULT__` 开头的行会加上 `[handler]` 前缀，避免被误识别为 UI 事件；CLI 自己生成的协议行不受影响。

查询工具要在 stdout 保留模型后续筛选、修改需要的 ID 和明细，不能只说“共有 N 条”。写工具通常只输出本次变更，完整快照通过返回值给 UI。

入口接收已解析的字典，不读取 `sys.argv`，不调用 `sys.exit()`；不要在模块导入时执行读写、打印结果或解析命令行。函数必须同步完成，不返回 coroutine、generator，也不留下后台任务。第三方库若默认往 stdout 打日志，应将其日志改到 stderr。

预期业务失败可返回以下对象，同时在 stdout 输出模型可理解的失败原因；CLI 根据 `phase: error` 生成错误状态。意外异常直接抛出，由框架处理，避免吞掉后报告成功：

```json
{"phase":"error","code":"NOT_FOUND","message":"目标记录不存在。","retryable":false}
```

## 一次调用的两个边界

```text
app CLI 父进程：读 manifest → 找 tool → 检查 visibility → 校验 inputSchema
  → 启动 CLI 自带的通用 worker 子进程（不需要 skill 自带 runner）
    → cwd 为 skill 根目录，sys.path 包含 handler 所在目录和 skill 根目录
    → 解析函数名：function 字段存在则取其值，否则取 tool.name
    → 动态加载 handler.path，找到对应函数后传入参数字典调用
    → stdout 原样由父进程捕获，return 值经内部结果文件交给父进程
  → 将 stdout 作为模型内容输出
  → 将返回字典封装成旁路结果（None 不生成旁路结果）
```

worker 与父进程间的结果文件是内部实现，业务函数只管 `print` 与 `return`。CLI 向 toolProxy 的传输继续使用现有 marker / `resultFile`，没有新增沙箱 artifact API。进程隔离并非权限隔离；新增依赖仍需由部署环境提供。

工具名不自动注入参数。CLI 通过默认同名或显式覆盖的函数名选择业务操作；同一文件可暴露多个入口函数，共享逻辑也可通过 import 复用。框架层的模块加载、函数契约、序列化或执行异常会生成简短模型错误与错误旁路结果，并以非零码退出。框架错误放在模型输出头部，避免被长输出截掉；异常原文和堆栈不进入 stdout / UI 结构化错误，stderr 仍保留诊断。不要把“进程退出成功”等同于“业务成功”，业务错误还要看返回对象的 `phase`。

## 兼容旧脚本

`handler.type: script`（或省略 type）继续按旧协议执行：`python3 <handler.path> '<args_json>'`，脚本读取 `sys.argv[1]` 并将完整 JSON 写 stdout。旧脚本不支持用 Python 返回值传 UI 数据；stdout 同时承担模型内容和 UI 数据。新建工具用 `python`，迁移时同时修改 manifest 与函数入口。

## inputSchema 支持范围

| 类别 | 关键字 |
|---|---|
| 通用 | `type`（可为数组）、`enum`、`const` |
| 字符串 | `minLength`、`maxLength` |
| 数值 | `minimum`、`maximum`、`exclusiveMinimum`、`exclusiveMaximum` |
| 对象 | `properties`、`required`、`additionalProperties`（`false` 或子 schema） |
| 数组 | `minItems`、`maxItems`、`items` |

不支持 `if`/`then`/`else`、`oneOf`/`anyOf`/`allOf`/`not`、`$ref`、`pattern`、`format`。未知关键字被忽略。字段白名单、类型、枚举、长度、范围与无条件必填放 manifest；空白处理、跨字段一致性、记录存在性等由业务检查。

一个操作一个 tool，各自声明字段与 `required`，并设置 `additionalProperties: false`。不要用 `operation` 枚举把 CRUD 合进一个工具，否则 schema 难以表达每个动作不同的必填与字段白名单。

## CLI → toolProxy 的旁路结果

返回字典时 CLI 追加协议行，由 toolProxy 提取后从模型文本删除：

```text
__ONEAGENT_APP_RESULT__ {"source":"skill","app":{"id":"my-notes","name":"我的笔记","version":"v1.0"},"toolName":"create_note","arguments":{},"status":"success","resourceUri":"ui://my-notes/main","structuredContent":{"notes":[],"count":0},"content":[]}
```

这只是信封示例，真实 `arguments`、`structuredContent` 来自本次调用，资源元数据由 manifest 补齐。数据大时 CLI 将完整信封落盘，协议行只带 `resultFile` 引用；toolProxy 通过本次沙箱 session 下载文件。UI 数据不应为生成预览而重新写入模型正文。

`resourceUri` / `resource` 来自工具绑定与资源声明，无绑定时省略；业务错误的 `status` 为 `error`。handler 未执行前的入参、身份或工具查找错误不产生业务结果。`None` 不发旁路记录、不挂载或刷新 UI。

skill 不应自己拼协议行、结果文件路径、App 身份或资源路由信息。直接跑业务文件没有这些框架步骤，因此需要 UI 的工具必须经 `app`。

## 错误码

CLI 参数、清单与路径错误包括 `SKILL_NOT_FOUND`、`NO_APP_YAML`、`BAD_APP_YAML`、`UNKNOWN_TOOL`、`FORBIDDEN`、`INVALID_ARGUMENT`、`SCRIPT_MISSING`。函数执行相关错误包括：

| 错误码 | 含义 |
|---|---|
| `INVALID_HANDLER` | handler 类型、配置或模块格式不合法 |
| `HANDLER_FUNCTION_MISSING` | 解析后的目标函数不存在或不可调用，不尝试其它函数 |
| `INVALID_HANDLER_RESULT` | 非 dict / None、不可序列化、NaN 或异步入口 |
| `HANDLER_EXECUTION_FAILED` | 加载或执行异常、进程异常退出 |
| `HANDLER_RESULT_MISSING` | 未收到 worker 的有效执行结果 |
| `RESULT_WRITE_FAILED` | 完整 UI 信封保存失败 |

业务错误使用领域码，避免与框架码重名；对不可直接重试的错误将 `retryable` 设为 `false`。业务 `phase: error` 可正常退出 0，框架错误退出非零。若业务可能已经写入但结果传输失败，先查询确认，避免重复写操作。
