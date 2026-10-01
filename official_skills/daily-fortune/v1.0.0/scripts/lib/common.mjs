import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const require = createRequire(import.meta.url);
const here = dirname(fileURLToPath(import.meta.url));

// 依赖为什么放在 scripts/lib/third_party：
// 1) 早先叫 vendor/vendor_modules（刻意不叫 node_modules，怕装机脚本整目录跳过）；
// 2) 但远端沙箱同步技能时会把 vendor/ 整目录丢掉，scripts/ 却能完整同步，
//    于是线上报 Cannot find module .../vendor/vendor_modules/@mingora/bazi/index.mjs。
// 所以最终只保留 scripts/lib/third_party 一处，vendor/ 已彻底删除。
// 目录名不能叫 node_modules，否则装机脚本仍会整目录跳过。
// 环境变量 DAILY_FORTUNE_VENDOR_DIR 可临时指定依赖目录，便于排查。
function vendorRoots() {
  const roots = [];
  if (process.env.DAILY_FORTUNE_VENDOR_DIR) roots.push(process.env.DAILY_FORTUNE_VENDOR_DIR);
  roots.push(join(here, "third_party"));
  return roots;
}

function missingDependencyError(name, tried) {
  const error = new Error(
    `依赖缺失：${name}。已尝试 ${tried.join("、")}。请确认技能的第三方依赖已随包同步` +
    `（可用环境变量 DAILY_FORTUNE_VENDOR_DIR 临时指定依赖目录）。`
  );
  error.code = "VENDOR_MISSING";
  return error;
}

export const DISCLAIMER = "传统文化与娱乐性参考，不是科学预测，也不构成健康、投资、法律、职业或婚恋决策建议。";

export function requireVendor(name) {
  return requireCjs(name);
}

export function vendorPath(name) {
  for (const root of vendorRoots()) {
    const target = join(root, name);
    if (require("fs").existsSync(target)) return target;
  }
  return join(vendorRoots()[0], name);
}

export function requireCjs(name) {
  const tried = [name];
  try {
    return require(name);
  } catch (error) {
    if (error?.code !== "MODULE_NOT_FOUND") throw error;
  }
  for (const root of vendorRoots()) {
    const target = join(root, name);
    tried.push(target);
    try {
      return require(target);
    } catch (error) {
      if (error?.code !== "MODULE_NOT_FOUND") throw error;
    }
  }
  throw missingDependencyError(name, tried);
}

export async function importVendor(name, entryFromPackageJson = true) {
  const { pathToFileURL } = require("node:url");
  const fs = require("fs");
  const toUrl = (target) => pathToFileURL(target).href;
  const tried = [];
  const attempt = async (candidate) => {
    tried.push(candidate);
    return await import(candidate.startsWith("/") ? toUrl(candidate) : candidate);
  };
  // 先试裸名：远端若真的装过依赖（package.json 里有），这一步就能命中。
  try {
    return await attempt(name);
  } catch (error) {
    if (error?.code !== "ERR_MODULE_NOT_FOUND" && error?.code !== "MODULE_NOT_FOUND") throw error;
  }
  for (const root of vendorRoots()) {
    const pkgDir = join(root, name);
    const entries = [];
    if (entryFromPackageJson && fs.existsSync(join(pkgDir, "package.json"))) {
      const pkg = JSON.parse(fs.readFileSync(join(pkgDir, "package.json"), "utf8"));
      entries.push(pkg.module || pkg.main || "index.js");
    }
    entries.push("index.js", "index.mjs");
    for (const entry of entries) {
      try {
        return await attempt(join(pkgDir, entry));
      } catch (error) {
        if (error?.code !== "ERR_MODULE_NOT_FOUND" && error?.code !== "MODULE_NOT_FOUND") throw error;
      }
    }
  }
  throw missingDependencyError(name, tried);
}

export function loadJSON(relativePath) {
  const fs = require("fs");
  return JSON.parse(fs.readFileSync(join(here, "..", "..", relativePath), "utf8"));
}

const CITIES = [
  { name: "北京市朝阳区", longitude: 116.44355, latitude: 39.9219, timeZone: "Asia/Shanghai", region: "北京市", source: "seed-cn-admin-v1" },
  { name: "北京市", longitude: 116.4074, latitude: 39.9042, timeZone: "Asia/Shanghai", region: "北京市", source: "seed-cn-city-v1" },
  { name: "上海市", longitude: 121.4737, latitude: 31.2304, timeZone: "Asia/Shanghai", region: "上海市", source: "seed-cn-city-v1" },
  { name: "天津市", longitude: 117.1901, latitude: 39.1252, timeZone: "Asia/Shanghai", region: "天津市", source: "seed-cn-city-v1" },
  { name: "重庆市", longitude: 106.5516, latitude: 29.563, timeZone: "Asia/Shanghai", region: "重庆市", source: "seed-cn-city-v1" },
  { name: "广州市", longitude: 113.2644, latitude: 23.1291, timeZone: "Asia/Shanghai", region: "广东省", source: "seed-cn-city-v1" },
  { name: "深圳市", longitude: 114.0579, latitude: 22.5431, timeZone: "Asia/Shanghai", region: "广东省", source: "seed-cn-city-v1" },
  { name: "成都市", longitude: 104.0665, latitude: 30.5728, timeZone: "Asia/Shanghai", region: "四川省", source: "seed-cn-city-v1" },
  { name: "杭州市", longitude: 120.1551, latitude: 30.2741, timeZone: "Asia/Shanghai", region: "浙江省", source: "seed-cn-city-v1" },
  { name: "南京市", longitude: 118.7969, latitude: 32.0603, timeZone: "Asia/Shanghai", region: "江苏省", source: "seed-cn-city-v1" },
  { name: "武汉市", longitude: 114.3055, latitude: 30.5928, timeZone: "Asia/Shanghai", region: "湖北省", source: "seed-cn-city-v1" },
  { name: "西安市", longitude: 108.9402, latitude: 34.3416, timeZone: "Asia/Shanghai", region: "陕西省", source: "seed-cn-city-v1" },
  { name: "香港特别行政区", longitude: 114.1694, latitude: 22.3193, timeZone: "Asia/Hong_Kong", region: "中国香港", source: "seed-cn-region-v1" },
  { name: "中国香港", longitude: 114.1694, latitude: 22.3193, timeZone: "Asia/Hong_Kong", region: "中国香港", source: "seed-cn-region-v1" },
  { name: "澳门特别行政区", longitude: 113.5439, latitude: 22.1987, timeZone: "Asia/Macau", region: "中国澳门", source: "seed-cn-region-v1" },
  { name: "中国澳门", longitude: 113.5439, latitude: 22.1987, timeZone: "Asia/Macau", region: "中国澳门", source: "seed-cn-region-v1" },
  { name: "台北市", longitude: 121.5654, latitude: 25.033, timeZone: "Asia/Taipei", region: "中国台湾", source: "seed-cn-city-v1" }
];

const ZONE_OFFSETS = {
  "Asia/Shanghai": 8,
  "Asia/Hong_Kong": 8,
  "Asia/Macau": 8,
  "Asia/Taipei": 8,
  "Asia/Chongqing": 8,
  "Asia/Singapore": 8,
  "Asia/Tokyo": 9,
  "Asia/Seoul": 9,
  "Europe/London": 0,
  "Europe/Paris": 1,
  "Europe/Berlin": 1,
  "America/New_York": -5,
  "America/Chicago": -6,
  "America/Los_Angeles": -8,
  "UTC": 0
};

const CN_DST_RANGES = [
  { start: "1986-05-04", end: "1986-09-14" },
  { start: "1987-04-12", end: "1987-09-13" },
  { start: "1988-04-10", end: "1988-09-11" },
  { start: "1989-04-16", end: "1989-09-17" },
  { start: "1990-04-15", end: "1990-09-16" },
  { start: "1991-04-14", end: "1991-09-15" }
];

export function parseDate(value, field) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(value || ""));
  if (!match) throw Object.assign(new Error(`${field} 必须是 YYYY-MM-DD`), { code: "INVALID_DATE" });
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  // 正则只挡得住格式；13 月、2 月 30 日这类值会一路流到历法库，抛出 "wrong month 13" 这类
  // 英文错误，且 phase 仍是 result，界面只显示"无法生成卡片"。在这里拦成可读的中文报错。
  if (month < 1 || month > 12) {
    throw Object.assign(new Error(`${field} 的月份必须在 01–12 之间：${value}`), { code: "INVALID_DATE" });
  }
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  if (day < 1 || day > daysInMonth) {
    throw Object.assign(new Error(`${field} 的日期超出 ${year} 年 ${month} 月的天数（1–${daysInMonth}）：${value}`), { code: "INVALID_DATE" });
  }
  return { year, month, day };
}

export function parseTime(value, field = "time") {
  if (value === undefined || value === null || value === "") return null;
  const match = /^(\d{1,2}):(\d{2})(?::(\d{2}))?$/.exec(String(value));
  if (!match) throw Object.assign(new Error(`${field} 必须是 HH:mm 或 HH:mm:ss`), { code: "INVALID_TIME" });
  const hour = Number(match[1]);
  const minute = Number(match[2]);
  const second = Number(match[3] || 0);
  if (hour > 23 || minute > 59 || second > 59) throw Object.assign(new Error(`${field} 超出合法范围`), { code: "INVALID_TIME" });
  return { hour, minute, second };
}

export function resolveLocation(input) {
  if (Number.isFinite(input.longitude) && typeof input.timezone === "string" && input.timezone.trim()) {
    return {
      name: String(input.birth_place || input.place || "用户提供坐标"),
      longitude: Number(input.longitude),
      latitude: Number.isFinite(input.latitude) ? Number(input.latitude) : null,
      timeZone: input.timezone.trim(),
      source: "user-provided"
    };
  }
  const query = String(input.birth_place || input.place || "").replace(/\s+/g, "").replace(/^中国/, "");
  const item = CITIES.find((row) => query === row.name || query.includes(row.name));
  if (!item) {
    throw Object.assign(
      new Error("地点无法唯一解析，请补充 longitude、latitude 和 timezone（IANA，例如 Asia/Shanghai）"),
      { code: "LOCATION_REQUIRED" }
    );
  }
  return { ...item };
}

export function isChinaZone(zone) {
  return ["Asia/Shanghai", "Asia/Chongqing", "Asia/Hong_Kong", "Asia/Macau", "Asia/Taipei"].includes(zone);
}

export function zoneOffsetMinutes(datePart, timePart, zone) {
  if (!ZONE_OFFSETS[zone]) throw Object.assign(new Error(`暂不支持的 IANA 时区：${zone}`), { code: "UNSUPPORTED_TIMEZONE" });
  let offset = ZONE_OFFSETS[zone] * 60;
  let dstApplied = false;
  if (isChinaZone(zone) && datePart) {
    const ymd = `${datePart.year}-${String(datePart.month).padStart(2, "0")}-${String(datePart.day).padStart(2, "0")}`;
    for (const range of CN_DST_RANGES) {
      if (ymd >= range.start && ymd <= range.end) {
        offset += 60;
        dstApplied = true;
        break;
      }
    }
  }
  return { offsetMinutes: offset, dstApplied };
}

export function civilToUtc(datePart, timePart, offsetMinutes) {
  const t = timePart || { hour: 12, minute: 0, second: 0 };
  const ms = Date.UTC(datePart.year, datePart.month - 1, datePart.day, t.hour, t.minute, t.second || 0);
  return new Date(ms - offsetMinutes * 60000);
}

export function envelope(skill, input) {
  const { data = {}, facts = {}, confidence, warnings = [], source = {}, audit = {} } = input;
  return {
    phase: "result",
    skill,
    engineVersion: source.engineVersion || "unspecified",
    policyVersion: source.policyVersion || "unspecified",
    facts,
    data,
    confidence: confidence || { level: "medium", reasons: [] },
    warnings,
    source,
    audit,
    disclaimer: DISCLAIMER
  };
}

export function fail(code, message, details = {}) {
  return { phase: "error", code, message, retryable: false, details };
}

export function readStdin() {
  const fs = require("fs");
  try {
    return fs.readFileSync(0, "utf8");
  } catch (error) {
    return "";
  }
}

export function parseRequest(argv) {
  const raw = argv[2] || readStdin();
  if (!raw || !raw.trim()) return {};
  try {
    const value = JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("参数必须是 JSON 对象");
    return value;
  } catch (error) {
    throw Object.assign(new Error(`参数必须是合法 JSON 对象：${error.message}`), { code: "INVALID_JSON" });
  }
}
