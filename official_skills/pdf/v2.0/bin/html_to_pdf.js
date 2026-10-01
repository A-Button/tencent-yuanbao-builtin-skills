#!/usr/bin/env node
"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");
const { pathToFileURL } = require("url");

const DEFAULT_CHROMIUM = "/nix/runtime/nix-env/bin/chromium";
const CHROME_COMMANDS = ["google-chrome", "chromium", "chromium-browser"];

function usage() {
  return [
    "Usage:",
    "  html_to_pdf --source . --target output.pdf",
    "  html_to_pdf --source report.html --target output/report.pdf",
    "  html_to_pdf --source /abs/report-dir --target /abs/output/report.pdf",
    "  html_to_pdf --source ./report --target ./output/report.pdf --chrome /nix/runtime/nix-env/bin/chromium",
    "",
    "Options:",
    "  --source <path>   HTML file or directory containing index.html (default: .)",
    "  --target <path>   Output PDF path (required)",
    "  --chrome <path>   Chromium executable path, or a directory containing chromium",
    "  --help            Show this help",
  ].join("\n");
}

function fail(message) {
  console.error(`html_to_pdf: ${message}`);
  process.exit(1);
}

function parseArgs(argv) {
  const args = { source: ".", target: null, chrome: null };

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (token === "--help" || token === "-h") {
      console.log(usage());
      process.exit(0);
    }

    if (token === "--source" || token === "--target" || token === "--chrome") {
      const value = argv[i + 1];
      if (!value || value.startsWith("--")) {
        fail(`${token} 需要一个参数值`);
      }
      args[token.slice(2)] = value;
      i += 1;
      continue;
    }

    fail(`未知参数: ${token}\n\n${usage()}`);
  }

  if (!args.target) {
    fail("--target 是必填参数");
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
    if (isExecutable(candidate)) {
      return candidate;
    }
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
    if (fs.existsSync(item)) {
      const stat = fs.statSync(item);
      if (stat.isDirectory()) {
        const nested = path.join(item, "chromium");
        if (isExecutable(nested)) return nested;
      }
      if (stat.isFile() && isExecutable(item)) return item;
    }
  }

  return null;
}

function findChromium(explicitChrome) {
  const candidates = [
    explicitChrome,
    process.env.CHROME,
    DEFAULT_CHROMIUM,
    ...CHROME_COMMANDS,
  ].filter(Boolean);

  for (const candidate of candidates) {
    const resolved = resolveChromeCandidate(candidate);
    if (resolved) {
      return resolved;
    }
  }

  fail(
    [
      "未找到 Chromium。",
      "查找顺序：--chrome、CHROME、/nix/runtime/nix-env/bin/chromium、google-chrome、chromium、chromium-browser。",
      "当前镜像应提供 /nix/runtime/nix-env/bin/chromium；如路径不同，请用 --chrome 指定。",
    ].join("\n")
  );
}

function resolveSource(sourceArg) {
  const sourcePath = path.resolve(process.cwd(), sourceArg || ".");
  if (!fs.existsSync(sourcePath)) {
    fail(`--source 不存在: ${sourcePath}`);
  }

  const stat = fs.statSync(sourcePath);
  const htmlPath = stat.isDirectory()
    ? path.join(sourcePath, "index.html")
    : sourcePath;

  if (!fs.existsSync(htmlPath)) {
    fail(`HTML 入口不存在: ${htmlPath}`);
  }
  if (!fs.statSync(htmlPath).isFile()) {
    fail(`HTML 入口不是文件: ${htmlPath}`);
  }

  return htmlPath;
}

function buildChromeArgs({ htmlPath, targetPath, userDataDir, headlessFlag }) {
  return [
    headlessFlag,
    "--no-sandbox",
    "--disable-gpu",
    "--disable-dev-shm-usage",
    "--incognito",
    `--user-data-dir=${userDataDir}`,
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-extensions",
    "--disable-component-update",
    "--no-pdf-header-footer",
    `--print-to-pdf=${targetPath}`,
    pathToFileURL(htmlPath).href,
  ];
}

function runChromium(chromePath, options, headlessFlag) {
  const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), "html-to-pdf-chrome-"));
  try {
    const args = buildChromeArgs({ ...options, userDataDir, headlessFlag });
    return spawnSync(chromePath, args, {
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } finally {
    fs.rmSync(userDataDir, { recursive: true, force: true });
  }
}

function assertPdfCreated(targetPath) {
  if (!fs.existsSync(targetPath)) {
    fail(`PDF 未生成: ${targetPath}`);
  }
  const size = fs.statSync(targetPath).size;
  if (size <= 0) {
    fail(`PDF 文件为空: ${targetPath}`);
  }
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  const htmlPath = resolveSource(args.source);
  const targetPath = path.resolve(process.cwd(), args.target);
  const chromePath = findChromium(args.chrome);

  fs.mkdirSync(path.dirname(targetPath), { recursive: true });

  const options = { htmlPath, targetPath };
  let result = runChromium(chromePath, options, "--headless=new");
  if (result.status !== 0) {
    const firstError = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
    console.error("html_to_pdf: --headless=new 失败，回退到 --headless 再试一次。");
    if (firstError) console.error(firstError);
    result = runChromium(chromePath, options, "--headless");
  }

  if (result.status !== 0) {
    const details = [result.stdout, result.stderr].filter(Boolean).join("\n").trim();
    fail(`Chromium 渲染失败，exit=${result.status}${details ? `\n${details}` : ""}`);
  }

  assertPdfCreated(targetPath);
  console.log(`PDF generated: ${targetPath}`);
}

main();
