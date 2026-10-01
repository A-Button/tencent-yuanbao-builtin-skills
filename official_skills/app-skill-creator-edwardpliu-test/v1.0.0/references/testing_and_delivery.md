# 测试与交付

## 测试矩阵

生成包自带三类测试，`npm test` 一次跑完（`python3 -m unittest discover -s tests` 加 `node tests/bridge-runtime.mjs`）。

**领域 API（`tests/test_api.py`）**：按 manifest 的 `handler.path` 加载模块，再按“function 字段存在则取其值，否则取 tool.name”选择同步函数，分别捕获 stdout 与返回字典。模板选择精简 JSON 作为模型输出，但协议本身允许自然语言；检查写操作 stdout 只有本次变更及 ID，查询 stdout 保留记录明细，返回值始终提供 UI 完整快照，并可严格 JSON 序列化。覆盖增删改查、缺库时返回空而非报错、每个 tool 都回带全量快照、错误信封稳定，以及 `app.yaml` 表达不了因而只能靠 handler 兜的那部分（例如「标题去掉空白后不能为空」）。至于 schema 本身拦得住什么（必填、字段白名单），归 `tests/test_manifest.py` 断言，不必在这里重测一遍。

**清单一致性（`tests/test_manifest.py`）**：id 与目录名一致；H5 资源使用 `ui://<id>/<view>` 与 `text/html;profile=mcp-app`，A2UI 资源使用 `ai_apps.skills.{skill_name}_{页面名}_res`（默认页可省略页面名）与 `application/a2ui+json`，skill_name 中的 `-` 转为 `_`；handler 声明 `type: python`，解析后的默认或显式函数名合法、无 `entrypoint` 且路径存在；`resourceUri`/`visibility` 在 `_meta.ui` 下且指向已声明资源；构建产物无残留占位符、无外链、且不比源文件旧。

**bridge 运行时（`tests/bridge-runtime.mjs`）**：在 jsdom 里加载构建产物，模拟完整时序 —— `ui/initialize` 握手 → 页面自发拉列表 → 增量 `host-context-changed` → Host 推 tool-result → 页面发起 `tools/call` → 结果回灌 → 转义用例。断言的是运行时行为，不是字符串包含。

写新测试时按这个标准取舍：验证可观测行为或真实不变量，不要断言生成出来的文案、标题或正则。

多视图的包，上面每一项都要按 `资源 × 声明支持的展示态` 各覆盖一遍。

## 手工验证

浏览器打开 `assets/ui/index.html?preview` 和 `?preview&theme=dark`，注入相同数据后至少检查：首屏可见、无横向溢出、文本不重叠、主要操作可点、主题切换后仍可读。

上线新函数型 handler 前，sandbox 中需先部署支持 `type: python` 的新版 CLI。若 AppGateway 仍直接执行脚本并从 stdout 解析 JSON，先升级其执行入口；不能只改 manifest 或假定 CLI 升级会自动更新另一条调用链。

在有新版 CLI 的环境，通过 `ONEAGENT_SKILLS_ROOT=<生成包的父目录> app <id> <tool> '<json>'` 做一次真实调用，确认普通输出是模型投影，旁路记录的 `structuredContent` 是完整返回值。大型 UI 数据走 `resultFile` 时，模型正文也不应包含完整 UI 数据。

真实 Host 可用时，确认这条顺序能跑通：

```text
load_skill → 资源列表下发（不挂 iframe）
模型调绑定 UI 的工具 → Host 拉 HTML → iframe 握手 → 渲染结果
iframe 上操作 → tools/call → 同一个 handler → 界面更新
```

## 产物位置

默认写在**当前工作区**的 `<app-id>/`（`init_app_skill.py --path` 指向工作区根目录，或用户指定的工作区内路径）。构建和测试都在这个目录里做。交付物就是工作区里的这份包。

**不要自主装到本机。** 下列行为都不在默认范围内：

- 执行 `register_local_app.py`
- 复制到 `~/.one-agent/skills` 或 `$ONE_AGENT_SKILL_PATH`

用户自己明确说「装到本机 / 注册到 ~/.one-agent」时，才用 `scripts/register_local_app.py <app-dir>`，并且先复述目标路径再动手。没这句话就结束。

## 汇报

说明改了哪些文件、工作区里的产物路径、数据落在哪里、依赖了哪些 Host 特有假设、跑了哪些测试。不要附上装机命令，除非用户已经要求装机。面向最终用户的回复里不要出现命令内部细节、marker、id 或原始堆栈。
