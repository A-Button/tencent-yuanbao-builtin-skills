// 多卡实例标识：宿主在 hostContext 下发 instanceId 时，界面必须登记并原样回传，
// 这样宿主才能把结果路由回那一张卡；宿主不下发时行为必须与旧版完全一致。
//
// 注意：这里验证的是「技能侧已经就绪」，不等于客户端会正确处理多卡。
// 客户端是否按实例区分卡片，取决于它自己有没有下发并使用这个字段。
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";

const html = await readFile(resolve("assets/ui/index.html"), "utf8");

function baseContext(extra = {}) {
  return {
    theme: "light",
    displayMode: "inline",
    availableDisplayModes: ["inline"],
    locale: "zh-CN",
    safeAreaInsets: { top: 0, right: 0, bottom: 0, left: 0 },
    ...extra,
  };
}

// 起一个独立 jsdom，模拟宿主握手并下发指定 hostContext，收集页面发出的调用。
async function boot(context) {
  const calls = [];
  const errors = [];
  let appWindow;
  let hostWindow;

  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (error) => errors.push(error.message));
  virtualConsole.on("error", (error) => errors.push(String(error)));

  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    url: "https://app.local/assets/ui/index.html",
    pretendToBeVisual: true,
    virtualConsole,
    beforeParse(window) {
      appWindow = window;
      hostWindow = {
        postMessage(message) {
          if (message?.method === "ui/initialize") {
            queueMicrotask(() =>
              window.dispatchEvent(
                new window.MessageEvent("message", {
                  source: hostWindow,
                  data: {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: {
                      protocolVersion: "2026-01-26",
                      hostInfo: { name: "test-host", version: "1.0.0" },
                      hostCapabilities: {},
                      hostContext: context,
                    },
                  },
                }),
              ),
            );
            return;
          }
          if (message?.method === "tools/call") {
            calls.push(message.params.arguments);
            queueMicrotask(() =>
              window.dispatchEvent(
                new window.MessageEvent("message", {
                  source: hostWindow,
                  data: {
                    jsonrpc: "2.0",
                    id: message.id,
                    result: { content: [], structuredContent: { phase: "result", data: { needs_profile: false, card: null } } },
                  },
                }),
              ),
            );
          }
        },
      };
      Object.defineProperty(window, "parent", { value: hostWindow, configurable: true });
      window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
      window.requestAnimationFrame = () => 0;
      window.cancelAnimationFrame = () => {};
    },
  });

  const deadline = Date.now() + 2000;
  while (Date.now() < deadline && calls.length === 0) {
    await new Promise((done) => setTimeout(done, 10));
  }
  return { dom, appWindow, calls, errors };
}

// 场景一：宿主下发了实例标识。
{
  const { dom, appWindow, calls, errors } = await boot(baseContext({ instanceId: "card-2026-0911-a" }));
  try {
    assert.ok(calls.length > 0, "页面未发起首屏调用");
    assert.equal(calls[0].instanceId, "card-2026-0911-a", "首屏调用未回传实例标识");
    assert.equal(
      appWindow.document.documentElement.dataset.instanceId,
      "card-2026-0911-a",
      "未在根元素登记实例标识",
    );
    assert.deepEqual(errors, []);
    console.log("  实例标识：宿主下发时已登记并回传 ✓");
  } finally {
    dom.window.close();
  }
}

// 场景二：宿主不支持该字段（当前线上客户端的真实情况）。
{
  const { dom, appWindow, calls, errors } = await boot(baseContext());
  try {
    assert.ok(calls.length > 0, "页面未发起首屏调用");
    assert.equal("instanceId" in calls[0], false, "宿主未下发时不应凭空带上该字段");
    assert.equal(
      appWindow.document.documentElement.dataset.instanceId,
      undefined,
      "宿主未下发时不应登记实例标识",
    );
    assert.deepEqual(errors, []);
    console.log("  实例标识：宿主未下发时与旧版一致（向后兼容）✓");
  } finally {
    dom.window.close();
  }
}

console.log("bridge instance: 实例标识登记/回传/向后兼容均通过");
