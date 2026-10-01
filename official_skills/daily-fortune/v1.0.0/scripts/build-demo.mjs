// 生成可离线点击的演示卡片：把真实数据注进构建产物，再装一个 mock bridge。
// 预览模式（?preview）会主动吞掉所有点击，所以这里不用 preview，而是自己接管 bridge。
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const uiPath = path.join(root, "assets", "ui", "index.html");
const outPath = process.argv[2] || path.join(root, "..", "daily-fortune-demo.html");

function callEngine(payload, profileDir) {
  const env = { ...process.env };
  if (profileDir) env.METAPHYSICS_PROFILE_DIR = profileDir;
  const out = execFileSync(process.execPath, [path.join(root, "scripts", "engine.mjs"), JSON.stringify(payload)], {
    encoding: "utf8",
    env
  });
  const line = out.split("\n").find((l) => l.trim().startsWith("{"));
  return JSON.parse(line);
}

const result = callEngine({ operation: "get_card" });
if (result.phase !== "result" || !result.data?.cards) {
  console.error("引擎未返回 16 组卡片，演示文件未生成");
  process.exit(1);
}

const html = fs.readFileSync(uiPath, "utf8");
const payload = JSON.stringify({
  structuredContent: {
    phase: "result",
    skill: "daily-fortune",
    facts: { operation: "get_card" },
    data: result.data
  }
});

const mock = `
<script>
/* 离线演示：接管 bridge，让界面在无宿主时也能真实切换。
   数据来自本地档案的真实计算，切 16 种组合都是真的重取，不是假数据。 */
(function () {
  var SNAP = ${payload};
  var ctx = { theme: "light", displayMode: "inline", locale: "zh-CN", timeZone: "Asia/Shanghai" };
  window.DailyFortuneBridge = {
    ready: Promise.resolve(),
    callTool: function () { return Promise.resolve(SNAP); },
    onToolResult: function () { return function () {}; },
    getHostContext: function () { return ctx; },
    onHostContextChanged: function (h) { h(ctx); return function () {}; },
    isPreview: false
  };
  var btn = document.createElement("button");
  btn.textContent = "切换深浅色";
  btn.style.cssText = "position:fixed;right:12px;bottom:12px;z-index:9;font:12px/1 -apple-system,'PingFang SC',sans-serif;padding:8px 12px;border-radius:999px;border:1px solid #ccc;background:#fff;color:#333;cursor:pointer;opacity:.85";
  btn.addEventListener("click", function () {
    ctx.theme = ctx.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = ctx.theme;
  });
  document.addEventListener("DOMContentLoaded", function () {
    document.body.appendChild(btn);
    document.dispatchEvent(new CustomEvent("daily-fortune:result", { detail: SNAP.structuredContent }));
  });
})();
</script>
`;

// mock 必须排在 UI 脚本之前，否则界面初始化时读到的还是真实 bridge
const marker = "<!-- MCP_BRIDGE_END -->";
const at = html.indexOf(marker);
if (at < 0) {
  console.error("index.html 缺少 MCP_BRIDGE_END 标记");
  process.exit(1);
}
const out = html.slice(0, at) + mock + html.slice(at);
fs.writeFileSync(outPath, out);
console.log("demo ->", outPath, (out.length / 1024).toFixed(0) + "KB");
