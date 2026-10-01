# iframe UI 与 bridge 参考

iframe 这一侧是标准 MCP Apps：用 `@modelcontextprotocol/ext-apps` 的 `App` 与 Host 通信。SDK 在 `app.connect()` 背后自己用 `postMessage` 跑 JSON-RPC，**不要**自造消息格式，也不要用 `fetch` 去取本地数据。

## 构建

UI 必须是一个完全自包含的 HTML 文件：Host 把它整份取走塞进 iframe，页面没有同源服务器，CSP 也会拦掉外链 CDN。

```text
scripts/ui_bridge_entry.js   →  esbuild bundle (iife, minify)  ┐
assets/ui/index.template     ─────────────────────────────────┼→ assets/ui/index.html
                                 占位符 /*__MCP_BRIDGE__*/      ┘
```

```bash
npm install
npm run build:ui
```

`build-ui.mjs` 做三件容易被忽略的事：把 bundle 里的 `</script` 转义（否则会提前闭合标签）、用函数形式替换（否则 bundle 里的 `$&` 会被当成替换模式）、替换后断言占位符已消失（否则会悄悄产出一个没有 bridge 的页面）。

要内联第三方库时，在 `build-ui.mjs` 里从 `node_modules` 读出来，再替换模板里的另一个占位符，不要在 HTML 里写 `<script src>`。

## bridge 契约

顺序是硬约束：**先 `new App` → 再注册事件 handler → 最后 `connect()`**。`connect()` 期间到达的首个 tool-result 会丢。`ready` 只能在 `connect()` 完成后 resolve。

骨架暴露的最小接口：

| 成员 | 用途 |
|---|---|
| `ready` | Promise，首次读取数据前必须等它 |
| `callTool(name, args)` | 转 `app.callServerTool({ name, arguments })` |
| `onToolResult(handler)` | 订阅 Host 推送；订阅时回放最近一次结果 |
| `getHostContext()` | 取合并后的完整 context |
| `onHostContextChanged(handler)` | 订阅 context 变更 |
| `isPreview` | 是否处于离线预览模式 |

只有页面真的提供切换按钮时才加 `requestDisplayMode`。不要在说明里写支持某能力，而 bridge 里并没有暴露对应方法。

两个易错点：

- **回放最近结果**。Host 可能在页面订阅之前就推过 tool-result，不回放会白屏。
- **`connect()` 失败也要 resolve `ready`**，否则页面永远卡在 `await ready`。

## 结果处理

Agent 推来的结果和页面自己 `callTool` 的返回，必须走**同一个**标准化函数与渲染路径，否则两条链路会渐渐长出不同的行为。

```js
function normalize(payload) {
  if (!payload) return null;
  return payload.structuredContent || payload;
}
```

错误处理的原则是不要让一次失败清空已有界面：已有数据时只提示，没有数据时才整屏报错。

## Host Context

初始值在 `ui/initialize` 的响应里，之后通过 `ui/notifications/host-context-changed` 送**增量**。SDK 会先把增量并进内部 context，所以取值一律用 `getHostContext()`，不要自己缓存整份再覆盖。用 `addEventListener("hostcontextchanged", ...)`，不要用已废弃的 `onhostcontextchanged` 属性。

| 字段 | 用途与要求 |
|---|---|
| `theme` | 只有 `light` / `dark`。优先配合 Host 提供的 CSS 变量使用 |
| `displayMode` | `inline` / `fullscreen` / `pip`。据此调整信息密度与导航，不要只处理前两种 |
| `availableDisplayModes` | Host 支持的展示态。只有在此列表内才可请求切换 |
| `containerDimensions` | iframe 容器的固定或最大宽高，不是浏览器 viewport |
| `locale`、`timeZone` | BCP 47 与 IANA 时区，用于展示；持久化仍用带时区的 ISO8601 |
| `platform`、`deviceCapabilities` | 据 `touch` / `hover` 调整控件尺寸与 hover 行为 |
| `safeAreaInsets` | 移动端安全区，用 CSS padding 或变量避让 |
| `toolInfo` | 本次创建视图的调用元数据，仅供展示与诊断，不作为业务状态或权限依据 |

需要会话级 UI 状态时用扩展对象，不要覆盖标准字段：

```json
{ "theme": "dark", "displayMode": "inline", "oneagent": { "conversationId": "opaque-id" } }
```

`oneagent.conversationId` 只能用于给前端临时状态分区（展开项、当前 tab、未提交表单）。它不是凭证，不得作为后端鉴权依据，也不得让 iframe 用它去选任意用户的数据。

不是每个字段都要做 UI 控件，但每个视图都必须：读初始 context、接收增量、合并而不是覆盖。确实用不上的字段，在生成包的 SKILL.md 里写明"不使用"，不要假装已适配。

## 安全

- 用户内容一律 `textContent`，不要拼进 `innerHTML`。
- 破坏性操作在页面内确认，不要指望 Host 提供确认框。
- 不把密钥、Cookie、原始认证头放进任何前端状态。

## 预览

```bash
open "assets/ui/index.html?preview"
open "assets/ui/index.html?preview&theme=dark"
```

预览模式塞入一份假的 host context 并禁用 `callTool`，用来快速看布局和主题。**它只能验证 UI**，不能替代 jsdom 的 bridge 运行时测试，更不等于真实 Host 端到端验证。
