#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const net = require("net");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");
const { pathToFileURL } = require("url");

const DEFAULT_CHROMIUM = "/nix/runtime/nix-env/bin/chromium";
const CHROME_COMMANDS = ["google-chrome", "chromium", "chromium-browser"];
const MACOS_CHROME_PATHS = [
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  "/Applications/Chromium.app/Contents/MacOS/Chromium",
];

function usage() {
  return [
    "Usage:",
    "  node scripts/check_render_quality.js --source output/document.html",
    "  node scripts/check_render_quality.js --source output/document.html --report output/render-quality.json",
    "",
    "Options:",
    "  --source <path>          HTML file or directory containing index.html (default: .)",
    "  --report <path>          Save JSON report",
    "  --chrome <path>          Chromium executable path, or a directory containing chromium",
    "  --page-selector <css>    Page containers (default: .report-page,.fullbleed-page,.page)",
    "  --help                   Show this help",
  ].join("\n");
}

function fail(message) {
  console.error(`check_render_quality: ${message}`);
  process.exit(1);
}

function parseArgs(argv) {
  const args = {
    source: ".",
    report: null,
    chrome: null,
    pageSelector: ".report-page,.fullbleed-page,.page",
  };

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--help" || token === "-h") {
      console.log(usage());
      process.exit(0);
    }

    const keyMap = {
      "--source": "source",
      "--report": "report",
      "--chrome": "chrome",
      "--page-selector": "pageSelector",
    };

    if (keyMap[token]) {
      const value = argv[i + 1];
      if (!value || value.startsWith("--")) {
        fail(`${token} 需要一个参数值`);
      }
      args[keyMap[token]] = value;
      i += 1;
      continue;
    }

    fail(`未知参数: ${token}\n\n${usage()}`);
  }

  return args;
}

function isExecutable(filePath) {
  try {
    fs.accessSync(filePath, fs.constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

function findOnPath(command) {
  const pathEnv = process.env.PATH || "";
  for (const dir of pathEnv.split(path.delimiter)) {
    if (!dir) continue;
    const candidate = path.join(dir, command);
    if (isExecutable(candidate)) return candidate;
  }
  return null;
}

function resolveChromeCandidate(candidate) {
  if (!candidate) return null;

  const absolute = path.resolve(process.cwd(), candidate);
  const directCandidates = [];
  if (path.isAbsolute(candidate)) {
    directCandidates.push(candidate);
  } else {
    directCandidates.push(absolute);
    const fromPath = findOnPath(candidate);
    if (fromPath) directCandidates.push(fromPath);
  }

  for (const item of directCandidates) {
    if (!fs.existsSync(item)) continue;
    const stat = fs.statSync(item);
    if (stat.isDirectory()) {
      const nested = path.join(item, "chromium");
      if (isExecutable(nested)) return nested;
    }
    if (stat.isFile() && isExecutable(item)) return item;
  }
  return null;
}

function findChromium(explicitChrome) {
  const candidates = [
    explicitChrome,
    process.env.CHROME,
    DEFAULT_CHROMIUM,
    ...MACOS_CHROME_PATHS,
    ...CHROME_COMMANDS,
  ].filter(Boolean);

  for (const candidate of candidates) {
    const resolved = resolveChromeCandidate(candidate);
    if (resolved) return resolved;
  }

  fail("未找到 Chromium。请用 --chrome 指定可执行文件。");
}

function resolveSource(sourceArg) {
  const sourcePath = path.resolve(process.cwd(), sourceArg || ".");
  if (!fs.existsSync(sourcePath)) fail(`--source 不存在: ${sourcePath}`);

  const stat = fs.statSync(sourcePath);
  const htmlPath = stat.isDirectory()
    ? path.join(sourcePath, "index.html")
    : sourcePath;

  if (!fs.existsSync(htmlPath)) fail(`HTML 入口不存在: ${htmlPath}`);
  if (!fs.statSync(htmlPath).isFile()) fail(`HTML 入口不是文件: ${htmlPath}`);
  return htmlPath;
}

function createTempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "render-quality-chrome-"));
}

function startChromium(chromePath, htmlPath, userDataDir) {
  return spawn(chromePath, [
    "--headless=new",
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-extensions",
    "--disable-component-update",
    "--remote-debugging-port=0",
    `--user-data-dir=${userDataDir}`,
    pathToFileURL(htmlPath).href,
  ], {
    stdio: ["ignore", "ignore", "pipe"],
  });
}

function waitForDevToolsUrl(chrome, timeoutMs = 10000) {
  return new Promise((resolve, reject) => {
    let stderr = "";
    const timer = setTimeout(() => {
      reject(new Error(`等待 DevTools 地址超时。\n${stderr.trim()}`));
    }, timeoutMs);

    chrome.stderr.on("data", (chunk) => {
      stderr += chunk.toString();
      const match = stderr.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) {
        clearTimeout(timer);
        resolve(match[1]);
      }
    });

    chrome.on("exit", (code) => {
      clearTimeout(timer);
      reject(new Error(`Chromium 提前退出，exit=${code}\n${stderr.trim()}`));
    });
  });
}

async function getPageWebSocketUrl(browserWsUrl) {
  const parsed = new URL(browserWsUrl);
  const listUrl = `http://${parsed.host}/json/list`;
  for (let i = 0; i < 20; i += 1) {
    const response = await fetch(listUrl);
    const pages = await response.json();
    const page = pages.find((item) => item.type === "page" && item.webSocketDebuggerUrl);
    if (page) return page.webSocketDebuggerUrl;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("未找到可调试页面。");
}

function encodeWsFrame(payload) {
  const data = Buffer.from(payload);
  const mask = crypto.randomBytes(4);
  let header;

  if (data.length < 126) {
    header = Buffer.alloc(2);
    header[1] = 0x80 | data.length;
  } else if (data.length < 65536) {
    header = Buffer.alloc(4);
    header[1] = 0x80 | 126;
    header.writeUInt16BE(data.length, 2);
  } else {
    header = Buffer.alloc(10);
    header[1] = 0x80 | 127;
    header.writeBigUInt64BE(BigInt(data.length), 2);
  }

  header[0] = 0x81;
  const masked = Buffer.alloc(data.length);
  for (let i = 0; i < data.length; i += 1) {
    masked[i] = data[i] ^ mask[i % 4];
  }

  return Buffer.concat([header, mask, masked]);
}

function decodeWsFrames(buffer) {
  const messages = [];
  let offset = 0;

  while (buffer.length - offset >= 2) {
    const first = buffer[offset];
    const second = buffer[offset + 1];
    const opcode = first & 0x0f;
    const masked = Boolean(second & 0x80);
    let length = second & 0x7f;
    let headerLength = 2;

    if (length === 126) {
      if (buffer.length - offset < 4) break;
      length = buffer.readUInt16BE(offset + 2);
      headerLength = 4;
    } else if (length === 127) {
      if (buffer.length - offset < 10) break;
      length = Number(buffer.readBigUInt64BE(offset + 2));
      headerLength = 10;
    }

    const maskLength = masked ? 4 : 0;
    const frameLength = headerLength + maskLength + length;
    if (buffer.length - offset < frameLength) break;

    let payload = buffer.subarray(offset + headerLength + maskLength, offset + frameLength);
    if (masked) {
      const mask = buffer.subarray(offset + headerLength, offset + headerLength + 4);
      const unmasked = Buffer.alloc(payload.length);
      for (let i = 0; i < payload.length; i += 1) {
        unmasked[i] = payload[i] ^ mask[i % 4];
      }
      payload = unmasked;
    }

    if (opcode === 1) messages.push(payload.toString("utf8"));
    offset += frameLength;
  }

  return { messages, remaining: buffer.subarray(offset) };
}

function connectWebSocket(wsUrl) {
  const parsed = new URL(wsUrl);
  const key = crypto.randomBytes(16).toString("base64");
  const socket = net.createConnection(Number(parsed.port), parsed.hostname);
  let buffer = Buffer.alloc(0);
  let connected = false;
  const pending = new Map();
  let resolveReady;
  let rejectReady;
  const ready = new Promise((resolve, reject) => {
    resolveReady = resolve;
    rejectReady = reject;
  });

  socket.on("data", (chunk) => {
    buffer = Buffer.concat([buffer, chunk]);
    if (!connected) {
      const marker = buffer.indexOf("\r\n\r\n");
      if (marker === -1) return;
      const head = buffer.subarray(0, marker).toString("utf8");
      if (!/^HTTP\/1\.1 101\b/m.test(head)) {
        rejectReady(new Error(`WebSocket 握手失败：\n${head}`));
        socket.end();
        return;
      }
      connected = true;
      resolveReady();
      buffer = buffer.subarray(marker + 4);
    }

    const decoded = decodeWsFrames(buffer);
    buffer = decoded.remaining;
    for (const message of decoded.messages) {
      const data = JSON.parse(message);
      if (data.id && pending.has(data.id)) {
        const { resolve, reject, timer } = pending.get(data.id);
        clearTimeout(timer);
        pending.delete(data.id);
        if (data.error) reject(new Error(JSON.stringify(data.error)));
        else resolve(data);
      }
    }
  });

  socket.on("error", (error) => {
    rejectReady(error);
    for (const { reject, timer } of pending.values()) {
      clearTimeout(timer);
      reject(error);
    }
    pending.clear();
  });

  const requestPath = `${parsed.pathname}${parsed.search}`;
  socket.write([
    `GET ${requestPath} HTTP/1.1`,
    `Host: ${parsed.host}`,
    "Upgrade: websocket",
    "Connection: Upgrade",
    `Sec-WebSocket-Key: ${key}`,
    "Sec-WebSocket-Version: 13",
    "\r\n",
  ].join("\r\n"));

  let nextId = 1;
  return {
    async send(method, params = {}, timeoutMs = 10000) {
      await ready;
      const id = nextId;
      nextId += 1;
      const payload = JSON.stringify({ id, method, params });
      socket.write(encodeWsFrame(payload));
      return new Promise((resolve, reject) => {
        const timer = setTimeout(() => {
          pending.delete(id);
          reject(new Error(`CDP 调用超时: ${method}`));
        }, timeoutMs);
        pending.set(id, { resolve, reject, timer });
      });
    },
    close() {
      socket.end();
    },
  };
}

function buildAuditExpression(pageSelector) {
  return `
    (async () => {
      const pageSelector = ${JSON.stringify(pageSelector)};
      const MM_TO_PX = 96 / 25.4;
      const EDGE_TOLERANCE = 2;
      const A4_WIDTH = 210 * MM_TO_PX;
      const A4_HEIGHT = 297 * MM_TO_PX;
      const issues = [];

      const isVisible = (el) => {
        const style = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return style.display !== "none" &&
          style.visibility !== "hidden" &&
          Number(style.opacity || "1") > 0.01 &&
          rect.width > 1 &&
          rect.height > 1;
      };

      const selectorOf = (el) => {
        if (el.id) return "#" + el.id;
        const cls = String(el.className || "").trim().split(/\\s+/).filter(Boolean).slice(0, 3).join(".");
        return el.tagName.toLowerCase() + (cls ? "." + cls : "");
      };

      const rectJson = (rect) => ({
        x: Math.round(rect.x * 10) / 10,
        y: Math.round(rect.y * 10) / 10,
        width: Math.round(rect.width * 10) / 10,
        height: Math.round(rect.height * 10) / 10,
        right: Math.round(rect.right * 10) / 10,
        bottom: Math.round(rect.bottom * 10) / 10,
      });

      const add = (severity, code, message, el, details = {}) => {
        issues.push({
          severity,
          code,
          message,
          selector: el ? selectorOf(el) : null,
          rect: el ? rectJson(el.getBoundingClientRect()) : null,
          details,
        });
      };

      const imageLoadChecks = [];
      const urlFromCss = (value) => {
        const matches = [];
        const re = /url\\((?:["']?)(.*?)(?:["']?)\\)/g;
        let match;
        while ((match = re.exec(value)) !== null) {
          if (match[1] && !match[1].startsWith("data:")) matches.push(match[1]);
        }
        return matches;
      };

      // Wait for fonts and images BEFORE measuring page containers.
      // The original code queried .page divs first and only waited afterward,
      // so on cold runs querySelectorAll returned dimensions computed while
      // huge embedded base64 fonts were still parsing. Those rects failed
      // isVisible, pageList fell back to document.body, and every .page then
      // reported as an element-outside-page. Waiting first eliminates the race.
      await Promise.all([
        document.fonts && document.fonts.ready ? document.fonts.ready : Promise.resolve(),
        ...Array.from(document.images).map((img) => {
          if (img.complete) return Promise.resolve();
          return new Promise((resolve) => {
            img.addEventListener("load", resolve, { once: true });
            img.addEventListener("error", resolve, { once: true });
          });
        }),
      ]);

      // Now measure. Keep pages and pageList as independent arrays — aliasing
      // (pageList = pages) let later "pageList.length = 0" wipe pages.
      const pages = Array.from(document.querySelectorAll(pageSelector)).filter(isVisible);
      const pageList = pages.length ? [...pages] : [document.body];

      for (const img of Array.from(document.images).filter(isVisible)) {
        const rect = img.getBoundingClientRect();
        const style = getComputedStyle(img);
        if (!img.complete || img.naturalWidth === 0 || img.naturalHeight === 0) {
          add("error", "image-not-loaded", "图片资源未成功加载", img, { src: img.currentSrc || img.src });
          continue;
        }
        const naturalRatio = img.naturalWidth / img.naturalHeight;
        const renderedRatio = rect.width / rect.height;
        const fit = style.objectFit || "fill";
        if ((fit === "fill" || fit === "none") && Math.abs(naturalRatio - renderedRatio) / naturalRatio > 0.08) {
          add("warning", "image-ratio-shift", "插图渲染比例与原图比例差异较大，请显式设置 object-fit", img, {
            objectFit: fit,
            naturalRatio: Math.round(naturalRatio * 1000) / 1000,
            renderedRatio: Math.round(renderedRatio * 1000) / 1000,
          });
        }
      }

      for (const el of Array.from(document.querySelectorAll("*")).filter(isVisible)) {
        const style = getComputedStyle(el);
        const bgUrls = urlFromCss(style.backgroundImage || "");
        for (const bgUrl of bgUrls) {
          imageLoadChecks.push(new Promise((resolve) => {
            const probe = new Image();
            probe.onload = () => resolve({ el, bgUrl, ok: true });
            probe.onerror = () => resolve({ el, bgUrl, ok: false });
            probe.src = bgUrl;
          }));
        }

        const name = [
          el.className || "",
          el.id || "",
          el.getAttribute("aria-label") || "",
          el.getAttribute("role") || "",
        ].join(" ").toLowerCase();
        const isBackgroundLike = /bg|background|backdrop|cover|hero|fullbleed/.test(name);
        if (isBackgroundLike && bgUrls.length) {
          const bgSize = style.backgroundSize;
          if (!/(cover|100%\\s+100%)/.test(bgSize)) {
            add("warning", "background-size", "背景图容器需要声明覆盖式 background-size", el, { backgroundSize: bgSize });
          }
        }
      }

      for (const item of await Promise.all(imageLoadChecks)) {
        if (!item.ok) {
          add("error", "background-not-loaded", "背景图片资源未成功加载", item.el, { url: item.bgUrl });
        }
      }

      pageList.forEach((page, pageIndex) => {
        const pageRect = page.getBoundingClientRect();
        const pageStyle = getComputedStyle(page);
        const pageName = selectorOf(page);
        const isFullBleed = /fullbleed|cover|poster|hero/.test(String(page.className || "").toLowerCase());

        if (page !== document.body) {
          if (Math.abs(pageRect.width - A4_WIDTH) > 8) {
            add("warning", "page-width", "页面容器宽度需要接近 A4 宽度 210mm", page, { page: pageIndex + 1, expectedPx: Math.round(A4_WIDTH), actualPx: Math.round(pageRect.width) });
          }
          if (Math.abs(pageRect.height - A4_HEIGHT) > 12 && pageStyle.minHeight !== "none") {
            add("warning", "page-height", "页面容器高度需要接近 A4 高度 297mm", page, { page: pageIndex + 1, expectedPx: Math.round(A4_HEIGHT), actualPx: Math.round(pageRect.height) });
          }
          if (page.scrollHeight - page.clientHeight > 2) {
            add("error", "page-overflow-y", "页面内容高度超过页面容器", page, { page: pageIndex + 1, scrollHeight: page.scrollHeight, clientHeight: page.clientHeight });
          }
          if (page.scrollWidth - page.clientWidth > 2) {
            add("error", "page-overflow-x", "页面内容宽度超过页面容器", page, { page: pageIndex + 1, scrollWidth: page.scrollWidth, clientWidth: page.clientWidth });
          }
        }

        const descendants = Array.from(page.querySelectorAll("*")).filter(isVisible);
        const candidates = (page === document.body ? Array.from(document.body.querySelectorAll("*")) : descendants)
          .filter((el) => isVisible(el) && !["SCRIPT", "STYLE", "LINK", "META"].includes(el.tagName));

        for (const el of candidates) {
          const rect = el.getBoundingClientRect();
          const tag = el.tagName.toLowerCase();
          const hasText = (el.innerText || "").trim().length > 0;
          const isMedia = ["img", "svg", "canvas", "table"].includes(tag);
          const isLayoutOnly = !hasText && !isMedia;
          if (isLayoutOnly) continue;

          if (rect.left < pageRect.left - EDGE_TOLERANCE ||
              rect.top < pageRect.top - EDGE_TOLERANCE ||
              rect.right > pageRect.right + EDGE_TOLERANCE ||
              rect.bottom > pageRect.bottom + EDGE_TOLERANCE) {
            add("error", "element-outside-page", "页面元素超出所属 A4 页面容器", el, { page: pageIndex + 1, pageSelector: pageName, pageRect: rectJson(pageRect) });
          }

          const bottomGap = pageRect.bottom - rect.bottom;
          if (!isFullBleed && hasText && bottomGap < 4 * MM_TO_PX && !/foot|footer|page-no|page-number/.test(String(el.className || "").toLowerCase())) {
            add("warning", "bottom-safe-area", "正文元素接近页面底部安全线", el, { page: pageIndex + 1, bottomGapPx: Math.round(bottomGap) });
          }
        }

        const textBlocks = candidates.filter((el) => {
          const style = getComputedStyle(el);
          const display = style.display;
          const text = (el.innerText || "").trim();
          return text.length > 0 && /^(block|flex|grid|table|list-item)/.test(display) && el.children.length <= 6;
        });

        for (let i = 0; i < textBlocks.length; i += 1) {
          const a = textBlocks[i];
          const ar = a.getBoundingClientRect();
          for (let j = i + 1; j < textBlocks.length; j += 1) {
            const b = textBlocks[j];
            if (a.contains(b) || b.contains(a)) continue;
            const br = b.getBoundingClientRect();
            const x = Math.max(0, Math.min(ar.right, br.right) - Math.max(ar.left, br.left));
            const y = Math.max(0, Math.min(ar.bottom, br.bottom) - Math.max(ar.top, br.top));
            const area = x * y;
            const smaller = Math.min(ar.width * ar.height, br.width * br.height);
            if (area > 24 && area / smaller > 0.18) {
              add("error", "text-overlap", "文本块之间存在明显重叠", a, {
                page: pageIndex + 1,
                otherSelector: selectorOf(b),
                overlapArea: Math.round(area),
              });
            }
          }
        }
      });

      const decoratedPattern = /badge|tag|pill|chip|icon|mark|num|number|no|idx|check|tick|dot|bullet|avatar|seal|stamp|circle|square/i;
      for (const el of Array.from(document.querySelectorAll("*")).filter(isVisible)) {
        const label = [el.className || "", el.id || "", el.getAttribute("aria-label") || ""].join(" ");
        if (!decoratedPattern.test(label)) continue;
        const text = (el.innerText || "").trim();
        const rect = el.getBoundingClientRect();
        if (text.length > 4 || rect.width > 90 || rect.height > 90) continue;

        const style = getComputedStyle(el);
        const bg = style.backgroundColor;
        const hasBox = bg && bg !== "rgba(0, 0, 0, 0)" || parseFloat(style.borderWidth || "0") > 0;
        if (!hasBox) continue;

        const display = style.display;
        const alignItems = style.alignItems;
        const justifyContent = style.justifyContent;
        const fontSize = parseFloat(style.fontSize || "0");
        const lineHeight = style.lineHeight === "normal" ? null : parseFloat(style.lineHeight || "0");
        const lineRatio = lineHeight && fontSize ? lineHeight / fontSize : null;

        if (!/(flex|inline-flex|grid|inline-grid)/.test(display) ||
            alignItems !== "center" ||
            justifyContent !== "center" ||
            !lineRatio ||
            lineRatio > 1.2) {
          add("warning", "decorated-centering", "小型色块内符号需要使用可计算的居中规则", el, {
            display,
            alignItems,
            justifyContent,
            lineHeight: style.lineHeight,
            fontSize: style.fontSize,
          });
        }
      }

      const errors = issues.filter((issue) => issue.severity === "error");
      const warnings = issues.filter((issue) => issue.severity === "warning");
      return {
        ok: errors.length === 0,
        summary: {
          errors: errors.length,
          warnings: warnings.length,
          pages: pageList.length,
          images: document.images.length,
        },
        issues,
      };
    })()
  `;
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const htmlPath = resolveSource(args.source);
  const chromePath = findChromium(args.chrome);
  const userDataDir = createTempDir();
  let chrome;
  let cdp;
  let exitCode = 0;

  try {
    chrome = startChromium(chromePath, htmlPath, userDataDir);
    const browserWsUrl = await waitForDevToolsUrl(chrome);
    const pageWsUrl = await getPageWebSocketUrl(browserWsUrl);
    cdp = connectWebSocket(pageWsUrl);
    await cdp.send("Runtime.enable");
    const evaluation = await cdp.send("Runtime.evaluate", {
      expression: buildAuditExpression(args.pageSelector),
      awaitPromise: true,
      returnByValue: true,
    }, 30000);

    const report = evaluation.result.result.value;
    const output = JSON.stringify(report, null, 2);
    if (args.report) {
      const reportPath = path.resolve(process.cwd(), args.report);
      fs.mkdirSync(path.dirname(reportPath), { recursive: true });
      fs.writeFileSync(reportPath, `${output}\n`);
    }

    const summary = report.summary;
    console.log(`Render quality: ${report.ok ? "PASS" : "FAIL"} (${summary.errors} errors, ${summary.warnings} warnings, ${summary.pages} pages, ${summary.images} images)`);
    for (const issue of report.issues.slice(0, 30)) {
      console.log(`[${issue.severity}] ${issue.code}: ${issue.message}${issue.selector ? ` (${issue.selector})` : ""}`);
    }
    if (report.issues.length > 30) {
      console.log(`... ${report.issues.length - 30} more issues. Use --report to inspect all.`);
    }

    exitCode = report.ok ? 0 : 2;
  } finally {
    if (cdp) cdp.close();
    if (chrome && !chrome.killed) chrome.kill();
    try {
      fs.rmSync(userDataDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 100 });
    } catch {
      // A just-terminated browser can briefly hold profile files on macOS.
    }
  }

  process.exitCode = exitCode;
}

main().catch((error) => {
  fail(error.stack || error.message);
});
