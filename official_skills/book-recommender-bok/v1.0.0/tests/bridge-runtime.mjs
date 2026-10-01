// jsdom 运行时测试：握手 → 首屏列表 → 搜索 → 推荐 → Host 推送。
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";

const html = await readFile(resolve("assets/ui/workspace.html"), "utf8");

const appMessages = [];
const errors = [];
let hostWindow;
let appWindow;

function deliver(data) {
  appWindow.dispatchEvent(new appWindow.MessageEvent("message", { data, source: hostWindow }));
}

function handleAppMessage(message) {
  appMessages.push(message);
  if (message?.method === "ui/initialize") {
    queueMicrotask(() => deliver({
      jsonrpc: "2.0",
      id: message.id,
      result: {
        protocolVersion: "2026-01-26",
        hostInfo: { name: "test-host", version: "1.0.0" },
        hostCapabilities: {},
        hostContext: {
          theme: "light",
          displayMode: "inline",
          availableDisplayModes: ["inline"],
          locale: "zh-CN",
          safeAreaInsets: { top: 0, right: 0, bottom: 0, left: 0 },
        },
      },
    }));
  }
}

function respondToolCall(message, structuredContent) {
  deliver({
    jsonrpc: "2.0",
    id: message.id,
    result: { content: [], structuredContent },
  });
}

async function waitFor(predicate, message) {
  const deadline = Date.now() + 2000;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise((done) => setTimeout(done, 10));
  }
  throw new Error(message);
}

const virtualConsole = new VirtualConsole();
virtualConsole.on("jsdomError", (error) => errors.push(error.message));
virtualConsole.on("error", (error) => errors.push(String(error)));

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  url: "https://app.local/assets/ui/workspace.html",
  pretendToBeVisual: true,
  virtualConsole,
  beforeParse(window) {
    appWindow = window;
    hostWindow = { postMessage: handleAppMessage };
    Object.defineProperty(window, "parent", { value: hostWindow, configurable: true });
    window.confirm = () => true;
    window.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
    window.requestAnimationFrame = () => 0;
    window.cancelAnimationFrame = () => {};
  },
});

try {
  await waitFor(
    () => appMessages.some((m) => m?.method === "ui/notifications/initialized"),
    "UI 未完成握手",
  );

  // 首屏自动调 list_books。
  const firstCall = await waitForCall("list_books");
  respondToolCall(firstCall, {
    operation: "list_books",
    books: [
      { id: "1", title: "三体", author: "刘慈欣", rating: 4.8, category: "科幻", description: "科幻经典。" },
      { id: "2", title: "活着", author: "余华", rating: 4.7, category: "文学", description: "人生故事。" },
    ],
    count: 2,
    categories: ["文学", "科幻", "历史"],
  });
  await waitFor(
    () => appWindow.document.querySelector(".title")?.textContent === "三体",
    "首屏列表未渲染",
  );

  // host context 增量合并
  deliver({
    jsonrpc: "2.0",
    method: "ui/notifications/host-context-changed",
    params: { theme: "dark", safeAreaInsets: { top: 0, right: 0, bottom: 17, left: 0 } },
  });
  await waitFor(
    () => appWindow.document.documentElement.dataset.theme === "dark",
    "主题未应用",
  );
  assert.equal(appWindow.document.body.style.getPropertyValue("--safe-bottom"), "17px");

  // 页面发起搜索 -> search_books。
  var input = appWindow.document.getElementById("query");
  input.value = "活着";
  appWindow.document.getElementById("search-btn").click();
  var searchCall = await waitForCall("search_books");
  assert.equal(searchCall.params.arguments.query, "活着");
  respondToolCall(searchCall, {
    operation: "search_books",
    books: [{ id: "2", title: "活着", author: "余华", rating: 4.7, category: "文学", description: "人生故事。" }],
    count: 1,
    query: "活着",
  });
  await waitFor(
    () => appWindow.document.querySelectorAll(".title").length === 1,
    "搜索结果未渲染",
  );

  // Agent 推送 recommend_books。
  deliver({
    jsonrpc: "2.0",
    method: "ui/notifications/tool-result",
    params: {
      content: [],
      structuredContent: {
        operation: "recommend_books",
        books: [
          { id: "1", title: "三体", author: "刘慈欣", rating: 4.8, category: "科幻", description: "科幻经典。" },
          { id: "3", title: "百年孤独", author: "马尔克斯", rating: 4.6, category: "文学", description: "魔幻现实主义。" },
        ],
        count: 2,
      },
    },
  });
  await waitFor(
    () => appWindow.document.querySelectorAll(".title").length === 2,
    "Agent 推送未渲染",
  );

  // 转义验证
  deliver({
    jsonrpc: "2.0",
    method: "ui/notifications/tool-result",
    params: {
      content: [],
      structuredContent: {
        operation: "search_books",
        books: [{ id: "x", title: "<img src=x onerror=1>", author: "x", rating: 1, category: "x", description: "x" }],
        count: 1,
      },
    },
  });
  await waitFor(
    () => appWindow.document.querySelectorAll(".title").length === 1,
    "转义用例未渲染",
  );
  assert.equal(appWindow.document.querySelectorAll("#stage img").length, 0);

  assert.deepEqual(errors, []);
  console.log("bridge runtime: 握手、host context、搜索、推荐推送与转义均通过");
} finally {
  dom.window.close();
}

async function waitForCall(toolName) {
  let found;
  await waitFor(() => {
    found = appMessages.find(
      (m) => m?.method === "tools/call" && m.params?.name === toolName,
    );
    return Boolean(found);
  }, `页面未发起 ${toolName} 调用`);
  return found;
}