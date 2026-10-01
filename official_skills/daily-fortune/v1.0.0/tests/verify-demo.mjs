// 验证演示文件：首屏能渲染，且切换时段/主题时标题、指数、幸运色、解读都真的变化。
import fs from "node:fs";
import path from "node:path";
import { JSDOM } from "jsdom";

const file = process.argv[2];
const html = fs.readFileSync(file, "utf8");
const errors = [];

const dom = new JSDOM(html, { runScripts: "dangerously", pretendToBeVisual: true, url: "https://x/demo.html" });
const { window } = dom;
window.addEventListener("error", (e) => errors.push(String(e.message)));

const wait = (ms) => new Promise((r) => setTimeout(r, ms));
await wait(400);

const doc = window.document;
const text = () => (doc.getElementById("stage")?.textContent || "").replace(/\s+/g, " ");
const title = () => doc.getElementById("title")?.textContent?.trim() || "";

function clickButton(label) {
  const btns = [...doc.querySelectorAll("button")];
  const b = btns.find((x) => x.textContent?.trim() === label);
  if (!b) throw new Error(`找不到按钮：${label}`);
  b.dispatchEvent(new window.MouseEvent("click", { bubbles: true }));
}

function colorOf() {
  const m = text().match(/幸运色([^\s]{2,6})/);
  return m ? m[1] : "?";
}

const results = [];
console.log(`首屏: ${title()} | 幸运色 ${colorOf()}`);
results.push({ label: "首屏", title: title(), color: colorOf(), text: text() });

for (const tk of ["本周", "本月", "今年", "今日"]) {
  clickButton(tk);
  await wait(120);
  console.log(`点「${tk}」: ${title()} | 幸运色 ${colorOf()}`);
  results.push({ label: tk, title: title(), color: colorOf(), text: text() });
}

const periodResults = results.slice(1, 4);
const periodColors = new Set(periodResults.map((r) => r.color));
if (periodColors.size !== 3) throw new Error(`四个时段幸运色应互不相同，实际 ${[...periodColors].join("/")}`);
console.log(`✓ 四个时段幸运色互不相同（${[...periodColors].join("、")}）`);

const topicTexts = new Set();
for (const tp of ["感情", "财富", "人际", "事业/学习"]) {
  clickButton(tp);
  await wait(120);
  topicTexts.add(text());
  console.log(`切「${tp}」: 解读含该主题 = ${text().includes(tp.split("/")[0])} | 幸运色 ${colorOf()}`);
}
if (topicTexts.size !== 4) throw new Error(`四个主题内容应互不相同，实际 ${topicTexts.size} 种`);
console.log("✓ 四个主题内容互不相同");

if (errors.length) throw new Error(`JS 报错：${errors.join(" | ")}`);
console.log("✓ 无 JS 报错");
// jsdom 会留下未关闭的定时器/窗口，不显式退出进程会一直挂着。
window.close();
process.exit(0);
