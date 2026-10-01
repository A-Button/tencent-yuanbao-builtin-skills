// esbuild 入口：打包成 IIFE 后由 build-ui.mjs 内联进 index.html。
// 顺序是硬约束：先 new App → 再注册 handler → 最后 connect()，否则 connect 期间
// 到达的首个 tool-result 会丢。ready 在 connect 完成后才 resolve。
import { App } from "@modelcontextprotocol/ext-apps";

const resultHandlers = new Set();
const contextHandlers = new Set();
let latestResult = null;
let hostContext = {};
let resolveReady;
const ready = new Promise((resolve) => { resolveReady = resolve; });

function publishResult(result) {
  latestResult = result;
  for (const handler of resultHandlers) handler(result);
}

function publishContext(context) {
  // host-context-changed 送的是增量，必须合并进已有 context，不能整体覆盖。
  hostContext = { ...hostContext, ...(context || {}) };
  for (const handler of contextHandlers) handler(hostContext);
}

function onToolResult(handler) {
  resultHandlers.add(handler);
  // 回放最近一次结果：Host 可能在页面订阅前就已经推过 tool-result。
  if (latestResult) handler(latestResult);
  return () => resultHandlers.delete(handler);
}

function onHostContextChanged(handler) {
  contextHandlers.add(handler);
  handler(hostContext);
  return () => contextHandlers.delete(handler);
}

const query = new URLSearchParams(location.search);

if (query.has("preview")) {
  // 浏览器直接打开时的离线模式，用于验证布局与主题。它不是端到端验证。
  hostContext = {
    theme: query.get("theme") === "dark" ? "dark" : "light",
    displayMode: "inline",
    availableDisplayModes: ["inline"],
    locale: "zh-CN",
    timeZone: "Asia/Shanghai",
    platform: "desktop",
    deviceCapabilities: { touch: false, hover: true },
    safeAreaInsets: { top: 0, right: 0, bottom: 0, left: 0 },
  };
  window.DailyFortuneBridge = {
    ready,
    callTool: async () => { throw new Error("预览模式不连接宿主，无法调用工具。"); },
    onToolResult,
    getHostContext: () => hostContext,
    onHostContextChanged,
    isPreview: true,
  };
  resolveReady();
} else {
  const app = new App(
    { name: "daily-fortune", version: "1.1.0" },
    { availableDisplayModes: ["inline"] },
  );

  app.addEventListener("toolresult", (result) => publishResult(result));
  app.addEventListener("hostcontextchanged", () => publishContext(app.getHostContext() || {}));

  window.DailyFortuneBridge = {
    ready,
    callTool(name, args) {
      return app.callServerTool({ name, arguments: args });
    },
    onToolResult,
    getHostContext() {
      return app.getHostContext() || hostContext;
    },
    onHostContextChanged,
    isPreview: false,
  };

  void app.connect().then(() => {
    publishContext(app.getHostContext() || {});
    resolveReady();
  }).catch((error) => {
    // 连不上 Host 时也要 resolve，否则页面会一直卡在 await ready。
    publishResult({
      structuredContent: {
        phase: "error",
        code: "HOST_CONNECT_FAILED",
        message: error?.message || "无法连接宿主。",
        retryable: true,
      },
    });
    resolveReady();
  });
}
