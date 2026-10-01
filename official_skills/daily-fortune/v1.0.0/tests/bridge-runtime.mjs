// 在 jsdom 里跑构建产物，验证 bridge 的运行时契约而不是字符串包含关系：
// 握手 → 首屏自拉取 → Host 推 tool-result → 页面切维度/主题 → 失败不清屏 → 转义。
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";

const TOOL_NAME = "daily_fortune";
const html = await readFile(resolve("assets/ui/index.html"), "utf8");

const appMessages = [];
const errors = [];
let hostWindow;
let appWindow;

function card(overrides = {}) {
  return {
    title: "今日运势概述",
    summary: "把已有计划拆成清晰步骤。",
    score: { value: 72, scale: "45–88", label: "稳中求进" },
    keyword: { label: "今日关键词", value: "确认", desc: "先完成第一版" },
    overview: "你的日主属金，今日宜借土气。",
    lucky: {
      color: "米黄色、棕黄色",
      colorHex: ["#f0e0a8", "#c8a165"],
      time: "07:00–09:00、13:00–15:00",
      timeGlyph: "⏰",
      direction: "中央",
      directionGlyph: "🏛️",
      number: "5、0",
      numberGlyph: "🎲",
      food: "谷物薯类、南瓜山药、黄色食物",
      foodGlyph: "🌾",
      accessory: "陶瓷、石质或暖黄配饰",
      accessoryGlyph: "🏺",
    },
    advice: { do: "先确认信息与边界。", avoid: "避免只做准备不推进。" },
    insight: { title: "今日事业/学习", body: "宜把目标拆成可执行清单。", meta: "今日 · 事业/学习" },
    transit: { yearGanZhi: "丙午", monthGanZhi: "丁酉", dayGanZhi: "甲子", anchorGanZhi: "甲子", timekey: "today" },
    bazi: { dayMaster: "庚", dayMasterElement: "金", pillars: { year: "庚辰", month: "戊寅", day: "庚午", hour: "戊寅" } },
    evidence: ["流期天干为日主生助五行，加 8 分"],
    ...overrides,
  };
}

function snapshot(overrides = {}) {
  return {
    phase: "result",
    data: {
      subject: "self",
      timekey: "today",
      topickey: "career",
      target_date: "2026-09-10",
      needs_profile: false,
      card: card(),
      ...overrides,
    },
  };
}

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
  deliver({ jsonrpc: "2.0", id: message.id, result: { content: [], structuredContent } });
}

async function waitFor(predicate, message) {
  const deadline = Date.now() + 2000;
  while (Date.now() < deadline) {
    if (predicate()) return;
    await new Promise((done) => setTimeout(done, 10));
  }
  throw new Error(message);
}

// cursor 只往前走：同一次断言不能被早先的调用满足，否则拿到的是上一次的参数。
let cursor = 0;

async function waitForCall(operation) {
  let found;
  await waitFor(() => {
    for (let i = cursor; i < appMessages.length; i += 1) {
      const message = appMessages[i];
      if (message?.method === "tools/call" && message.params?.arguments?.operation === operation) {
        found = message;
        cursor = i + 1;
        return true;
      }
    }
    return false;
  }, `页面未发起 ${operation} 调用`);
  return found;
}

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
    hostWindow = { postMessage: handleAppMessage };
    Object.defineProperty(window, "parent", { value: hostWindow, configurable: true });
    window.confirm = () => true;
    // SDK 会在 rAF 回调里上报 iframe 尺寸。jsdom 的 rAF 会在 connect() 完成前就跑，
    // 那时 transport 还没就绪，notification 抛 Not connected 并直接崩掉进程。
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

  // 首屏应当自己拉一次卡片。
  const firstCall = await waitForCall("get_card");
  assert.equal(firstCall.params.name, TOOL_NAME);
  respondToolCall(firstCall, snapshot());
  await waitFor(
    () => appWindow.document.querySelector(".scoreBox .value")?.textContent === "72",
    "首屏卡片未渲染",
  );
  // 卡片上不应残留任何订阅入口。
  assert.equal(appWindow.document.getElementById("subPill"), null, "订阅徽标未移除");
  assert.equal(appWindow.document.getElementById("saveBtn"), null, "保存按钮未移除");
  assert.equal(appWindow.document.getElementById("toggleBtn"), null, "订阅按钮未移除");
  assert.equal(appWindow.document.querySelectorAll(".panel").length, 0, "设置面板未移除");
  assert.ok(!/订阅|推送/.test(appWindow.document.body.textContent), "卡面仍出现订阅/推送字样");

  // 成功出卡不该再弹"这是你的运势卡片"这类提示条。
  assert.equal(appWindow.document.getElementById("toast").hidden, true, "成功出卡后仍显示了提示条");

  // 部分 host context 更新必须合并进已有 context，而不是整体覆盖。
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

  // Agent 侧推来的 tool-result 走同一条渲染路径。
  deliver({
    jsonrpc: "2.0",
    method: "ui/notifications/tool-result",
    params: {
      content: [],
      structuredContent: snapshot({
        card: card({ score: { value: 81, scale: "45–88", label: "顺势推进" } }),
      }),
    },
  });
  await waitFor(
    () => appWindow.document.querySelector(".scoreBox .value")?.textContent === "81",
    "Agent 推送的结果未渲染",
  );

  // 页面自己切时间维度。
  const weekChip = [...appWindow.document.querySelectorAll("#timeSeg button")]
    .find((btn) => btn.dataset.key === "week");
  assert.ok(weekChip, "缺少本周切换按钮");
  weekChip.dispatchEvent(new appWindow.MouseEvent("click", { bubbles: true }));
  const weekCall = await waitForCall("get_card");
  assert.equal(weekCall.params.arguments.timekey, "week");
  assert.equal(weekCall.params.arguments.topickey, "career");
  respondToolCall(weekCall, snapshot({
    timekey: "week",
    card: card({ title: "本周运势概述" }),
  }));
  await waitFor(
    () => appWindow.document.getElementById("title").textContent === "本周运势概述",
    "切换时间维度后未渲染",
  );

  // 页面自己切解读主题。
  const topicChip = [...appWindow.document.querySelectorAll("#stage .seg.light button")]
    .find((btn) => btn.dataset.key === "love");
  assert.ok(topicChip, "缺少感情主题切换按钮");
  topicChip.dispatchEvent(new appWindow.MouseEvent("click", { bubbles: true }));
  const topicCall = await waitForCall("get_card");
  assert.equal(topicCall.params.arguments.timekey, "week");
  assert.equal(topicCall.params.arguments.topickey, "love");
  respondToolCall(topicCall, snapshot({
    timekey: "week",
    topickey: "love",
    card: card({ title: "本周运势概述", insight: { title: "本周感情", body: "多倾听。", meta: "本周 · 感情" } }),
  }));
  await waitFor(
    () => appWindow.document.querySelector(".insightBox .title")?.textContent === "本周感情",
    "切换主题后未渲染",
  );

  // 一次失败不能清空已有界面。
  deliver({
    jsonrpc: "2.0",
    method: "ui/notifications/tool-result",
    params: { content: [], structuredContent: { phase: "error", code: "ENGINE_FAILED", message: "引擎失败" } },
  });
  await waitFor(
    () => appWindow.document.getElementById("toast").textContent === "引擎失败",
    "失败未提示",
  );
  assert.equal(appWindow.document.querySelector(".scoreBox .value").textContent, "72", "失败后不应清空已有卡片");
  assert.equal(appWindow.document.querySelectorAll("#stage .error").length, 0);

  // 转义验证：卡片文案里的标签不能变成真实节点。
  deliver({
    jsonrpc: "2.0",
    method: "ui/notifications/tool-result",
    params: {
      content: [],
      structuredContent: snapshot({
        card: card({ keyword: { label: "今日关键词", value: "<img src=x onerror=1>", desc: "注入" } }),
      }),
    },
  });
  await waitFor(
    () => appWindow.document.querySelectorAll(".scoreBox .value").length === 2,
    "转义用例未渲染",
  );
  assert.equal(appWindow.document.querySelectorAll("#stage img").length, 0);

  assert.deepEqual(errors, []);
  console.log("bridge runtime: 握手、host context、切维度、切主题、无订阅残留、失败不清屏与转义均通过");
} finally {
  dom.window.close();
}
