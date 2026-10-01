import {
  envelope,
  fail,
  importVendor,
  parseDate,
  parseRequest,
  parseTime,
  requireCjs,
  resolveLocation,
  zoneOffsetMinutes,
  civilToUtc
} from "./lib/common.mjs";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// 依赖加载失败不能让整个引擎崩掉：远端同步丢目录时，用户看到的是一张正常的错误卡
// 加一句可读说明，而不是 ERR_MODULE_NOT_FOUND 的堆栈。
let VENDOR_ERROR = null;
let Solar = null;
let calculateBaziChart = null;
let calculateTrueSolarTime = null;
try {
  Solar = requireCjs("lunar-javascript/index.js").Solar;
  const bazi = await importVendor("@mingora/bazi");
  calculateBaziChart = bazi.calculateBaziChart;
  calculateTrueSolarTime = bazi.calculateTrueSolarTime;
} catch (error) {
  VENDOR_ERROR = error;
}

const SKILL = "daily-fortune";
const ENGINE_VERSION = "daily-fortune-engine-v0.1.0";
const POLICY_VERSION = "daily-fortune-rules-v0.1.0";
const CALENDAR_LIB = "lunar-javascript@1.7.7";
const CHART_LIB = "@mingora/bazi@0.1.0";

const PROFILE_DIR = process.env.METAPHYSICS_PROFILE_DIR || path.join(os.homedir(), ".one-agent", "metaphysics-profile");
const PROFILE_FILE = path.join(PROFILE_DIR, "profiles.json");

// ---------- 五行 / 十神 常量（与 bazi-master 一致） ----------
const ELEMENT_CN = { wood: "木", fire: "火", earth: "土", metal: "金", water: "水" };
const STEM_ELEMENT = {
  甲: "wood", 乙: "wood", 丙: "fire", 丁: "fire", 戊: "earth",
  己: "earth", 庚: "metal", 辛: "metal", 壬: "water", 癸: "water"
};
const PRODUCES = { wood: "fire", fire: "earth", earth: "metal", metal: "water", water: "wood" };
const CONTROLS = { wood: "earth", earth: "water", water: "fire", fire: "metal", metal: "wood" };
const RESOURCE_FOR = { wood: "water", fire: "wood", earth: "fire", metal: "earth", water: "metal" };
const COLOR_BY_ELEMENT = {
  wood: ["青绿色", "松绿色"], fire: ["暖红色", "紫红色"], earth: ["米黄色", "棕黄色"],
  metal: ["白色", "银灰色"], water: ["深蓝色", "黑色"]
};
const DIRECTION_BY_ELEMENT = { wood: "东方", fire: "南方", earth: "中央", metal: "西方", water: "北方" };
const COMBINES = new Set(["子丑", "寅亥", "卯戌", "辰酉", "巳申", "午未", "丑子", "亥寅", "戌卯", "酉辰", "申巳", "未午"]);
const CLASHES = new Set(["子午", "丑未", "寅申", "卯酉", "辰戌", "巳亥", "午子", "未丑", "申寅", "酉卯", "戌辰", "亥巳"]);
// 地支五行，用于让"喜用"同时参考流期地支（只看天干的话，月柱与年柱同为火时会算出同一个结果）
const BRANCH_ELEMENT = {
  子: "water", 丑: "earth", 寅: "wood", 卯: "wood", 辰: "earth", 巳: "fire",
  午: "fire", 未: "earth", 申: "metal", 酉: "metal", 戌: "earth", 亥: "water"
};
const ELEMENT_ORDER = ["wood", "fire", "earth", "metal", "water"];

// 克我者（官杀）：找出那个"制约 e"的五行
function elementControlling(e) {
  return Object.keys(CONTROLS).find((x) => CONTROLS[x] === e) || e;
}

// a 对 b 的生克关系（a 为流期，b 为对照对象）
function relationOf(a, b) {
  if (a === b) return "same";
  if (PRODUCES[a] === b) return "a-nourishes-b"; // 流期生对象
  if (PRODUCES[b] === a) return "b-nourishes-a"; // 对象生流期（泄气）
  if (CONTROLS[a] === b) return "a-controls-b";  // 流期克对象（受制）
  if (CONTROLS[b] === a) return "b-controls-a";  // 对象克流期（耗力）
  return "none";
}

// 各主题对应「主星 + 辅星」两个十神（均相对日主）。
// 只用单一十神会出问题：女命的官杀既是事业星也是夫星，于是"事业"和"感情"
// 两张卡算出来一模一样。加入辅星后两者区分开——事业兼看印绶（资质），感情兼看食伤（表达）。
const TOPIC_STARS = {
  career: (self) => ({ primary: elementControlling(self), secondary: RESOURCE_FOR[self], primaryLabel: "官杀", secondaryLabel: "印绶" }),
  wealth: (self) => ({ primary: CONTROLS[self], secondary: PRODUCES[self], primaryLabel: "财星", secondaryLabel: "食伤" }),
  social: (self) => ({ primary: self, secondary: RESOURCE_FOR[self], primaryLabel: "比劫", secondaryLabel: "印绶" }),
  love: (self, gender) => (gender === "male"
    ? { primary: CONTROLS[self], secondary: PRODUCES[self], primaryLabel: "妻财", secondaryLabel: "食伤" }
    : gender === "female"
      ? { primary: elementControlling(self), secondary: PRODUCES[self], primaryLabel: "官杀", secondaryLabel: "食伤" }
      : { primary: PRODUCES[self], secondary: self, primaryLabel: "食伤", secondaryLabel: "比劫" })
};

const HE_TU = { wood: ["3", "8"], fire: ["2", "7"], earth: ["5", "0"], metal: ["4", "9"], water: ["1", "6"] };
const LUCKY_TIME = {
  wood: ["03:00–05:00", "15:00–17:00"], fire: ["09:00–11:00", "21:00–23:00"],
  earth: ["07:00–09:00", "13:00–15:00"], metal: ["17:00–19:00", "23:00–01:00"], water: ["21:00–23:00", "05:00–07:00"]
};
const LUCKY_FOOD = {
  wood: "清润蔬菜、绿叶瓜果、豆制品", fire: "温补红肉、红枣桂圆、少量辛香",
  earth: "谷物薯类、南瓜山药、黄色食物", metal: "白色清淡、坚果、润肺食材", water: "汤水鱼鲜、黑色食物、润燥之品"
};
const LUCKY_ACCESSORY = {
  wood: "绿植、木质或编织手串", fire: "红色或暖色系配饰、玛瑙",
  earth: "陶瓷、石质或暖黄配饰", metal: "简洁金属腕表或银饰", water: "深色系配饰、水波纹饰品"
};
// 缩略图（emoji 形式，零依赖），与上面文案按五行对齐
const COLOR_HEX = {
  wood: ["#2e8b57", "#01796f"], fire: ["#e74c3c", "#8e44ad"],
  earth: ["#f0e0a8", "#c8a165"], metal: ["#ffffff", "#c0c0c0"], water: ["#1b3a6b", "#1a1a1a"]
};
const FOOD_GLYPH = { wood: "🥬", fire: "🍖", earth: "🌾", metal: "🌰", water: "🍜" };
const ACCESSORY_GLYPH = { wood: "📿", fire: "🔴", earth: "🏺", metal: "💍", water: "💧" };
const DIRECTION_GLYPH = { wood: "🌅", fire: "☀️", earth: "🏛️", metal: "🌇", water: "❄️" };
const TIME_GLYPH = "⏰";
const NUMBER_GLYPH = "🎲";
const ELEMENT_ARCHETYPE = {
  wood: "如草木向上，主仁、主生长：积极有规划，喜拓展，但易因想得多而行动滞后。",
  fire: "如火焰向上，主礼、主热情：外放有感染力，行动快，但需防三分钟热度。",
  earth: "如大地厚载，主信、主稳定：踏实可靠、重承诺，但需防过于保守。",
  metal: "如金石坚刚，主义、主决断：刚毅讲原则、重秩序，但需防顾虑过多。",
  water: "如流水灵动，主智、主变化：灵活善应变、喜自由，但需防方向飘移。"
};
const TIMEKEY_LABEL = { today: "今日", week: "本周", month: "本月", year: "今年" };
const TOPIC_LABEL = { career: "事业/学习", love: "感情", wealth: "财富", social: "人际" };

const TIMEKEY_SUMMARY = {
  today: "把已有计划拆成清晰步骤，不宜在信息不全时做过度承诺。",
  week: "适合把计划从想法推进到执行表，稳住节奏、明确责任。",
  month: "关键词是建立稳定标签：可靠、专业、能交付，适合补齐方法论。",
  year: "适合稳健上升：积累资质、建立信誉、优化表达，把长期目标拆成季度节点。"
};
const TIMEKEY_KEYWORD = {
  today: { high: ["执行", "少想一步，多做一步"], mid: ["确认", "先完成第一版"], low: ["留白", "减少临时承诺"] },
  week: { high: ["落地", "把目标拆成周计划"], mid: ["规划", "明确每周三件关键事"], low: ["缓冲", "先稳住节奏"] },
  month: { high: ["突破", "让能力被看见"], mid: ["沉淀", "整理阶段成果"], low: ["守成", "不宜频繁换向"] },
  year: { high: ["信誉", "长期主义更有利"], mid: ["积累", "建立年度能力地图"], low: ["蛰伏", "先夯实基础"] }
};

// ---------- 档案读取 ----------
function loadProfile(subject = "self") {
  if (!fs.existsSync(PROFILE_FILE)) return null;
  try {
    const store = JSON.parse(fs.readFileSync(PROFILE_FILE, "utf8"));
    const profiles = store.profiles || {};
    if (subject === "self") return profiles.self || Object.values(profiles)[0] || null;
    return profiles[subject] || null;
  } catch (error) {
    return null;
  }
}

// ---------- 八字计算（复用 @mingora/bazi 确定性引擎） ----------
function buildBase(input) {
  const p = input || {};
  const date = parseDate(p.birth_date, "birth_date");
  const precision = p.birth_time_precision || (p.birth_time ? "exact" : "unknown");
  const time = precision === "unknown" ? null : parseTime(p.birth_time, "birth_time");
  // 档案把坐标存在 location 子对象里，而 resolveLocation 只认顶层 longitude/timezone。
  // 不合并的话，任何不在内置城市库的地点（市辖区、县级市）都会解析失败，
  // 即使档案已补全经纬度 —— self 之所以正常，只是因为"北京市"恰好在库里。
  const location = resolveLocation({
    ...p,
    longitude: p.longitude ?? p.location?.longitude,
    latitude: p.latitude ?? p.location?.latitude,
    timezone: p.timezone ?? p.location?.timeZone
  });
  const dayBoundary = p.day_boundary === "zi-hour" ? "zi-hour" : "midnight";
  const solarPolicy = p.solar_time_policy === "civil" ? "civil" : "true-solar";
  const zoneInfo = zoneOffsetMinutes(date, time, location.timeZone);
  const utc = civilToUtc(date, time, zoneInfo.offsetMinutes);
  return { p, date, time, precision, location, dayBoundary, solarPolicy, zoneInfo, utc };
}

function computeChart(profile) {
  const base = buildBase(profile);
  const { date, time, precision, location, dayBoundary, solarPolicy, zoneInfo } = base;
  const useSolar = solarPolicy === "true-solar" && time !== null;
  const chart = calculateBaziChart({
    date, time,
    location: { timeZone: location.timeZone, longitude: location.longitude, ...(location.latitude === null ? {} : { latitude: location.latitude }) },
    options: { solarTime: useSolar ? "true" : "civil", dayBoundary, disambiguation: "compatible" }
  });
  return {
    dayMasterElement: chart.dayMaster?.element || null,
    dayMasterChar: chart.dayMaster?.character ?? null,
    pillars: {
      year: chart.pillars?.year?.ganZhi,
      month: chart.pillars?.month?.ganZhi,
      day: chart.pillars?.day?.ganZhi,
      hour: chart.pillars?.hour?.ganZhi
    },
    dayBranch: chart.pillars?.day?.branch?.character ?? null,
    warnings: chart.warnings || [],
    confidenceLevel: chart.confidence?.level ?? "low"
  };
}

// ---------- 流期干支 ----------
function transitGanZhi(target) {
  const lunar = Solar.fromYmd(target.year, target.month, target.day).getLunar();
  return {
    year: lunar.getYearInGanZhiExact(),
    month: lunar.getMonthInGanZhiExact(),
    day: lunar.getDayInGanZhiExact2(),
    yearStem: lunar.getYearInGanZhiExact().slice(0, 1),
    yearBranch: lunar.getYearInGanZhiExact().slice(1, 2),
    monthStem: lunar.getMonthInGanZhiExact().slice(0, 1),
    monthBranch: lunar.getMonthInGanZhiExact().slice(1, 2),
    dayStem: lunar.getDayInGanZhiExact2().slice(0, 1),
    dayBranch: lunar.getDayInGanZhiExact2().slice(1, 2)
  };
}

// 十天干循环，用于推导"周干"
const STEM_CYCLE = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"];

// 选择某一时间维度对应的"流期天干/地支"作为评分锚点
// today→日干；week→按星期几在日干上偏移出独立"周干"；month→月干；year→年干(流年)
function periodAnchor(transit, timekey, target) {
  if (timekey === "today") return { stem: transit.dayStem, branch: transit.dayBranch };
  if (timekey === "week") {
    // 本周锚点取"该周周一"的日柱——那才是这一周的流期。
    // 旧做法是在今日日柱上按星期几偏移，周日（偏移 0）会与今日完全重合，
    // 导致"今日"和"本周"两张卡内容一模一样。
    const d = new Date(target.year, target.month - 1, target.day);
    const dow = d.getDay(); // 0=周日..6=周六
    d.setDate(d.getDate() + (dow === 0 ? -6 : 1 - dow)); // 回退到本周一
    const gz = Solar.fromYmd(d.getFullYear(), d.getMonth() + 1, d.getDate()).getLunar().getDayInGanZhiExact2();
    return { stem: gz.slice(0, 1), branch: gz.slice(1, 2) };
  }
  if (timekey === "month") return { stem: transit.monthStem, branch: transit.monthBranch };
  return { stem: transit.yearStem, branch: transit.yearBranch }; // year
}

// ---------- 评分（沿用 bazi-master 的版本化规则） ----------
function scoreFor(selfElement, transitStem, natalBranch, transitBranch) {
  const transitElement = STEM_ELEMENT[transitStem] || selfElement;
  let score = 62;
  const evidence = [];
  // 五行相克是一个五步循环，因此下面这些关系互斥，命中即止。
  let relation = "none";
  if (transitElement === selfElement) {
    score += 5; relation = "transit-same";
    evidence.push("流期天干与日主同五行，加 5 分");
  } else if (transitElement === RESOURCE_FOR[selfElement]) {
    score += 8; relation = "transit-nourishes";
    evidence.push("流期天干为日主生助五行，加 8 分");
  } else if (PRODUCES[selfElement] === transitElement) {
    score += 3; relation = "self-drains";
    evidence.push("日主生流期五行，加 3 分");
  } else if (CONTROLS[transitElement] === selfElement) {
    score -= 8; relation = "transit-restrains";
    evidence.push("流期五行制日主，减 8 分");
  } else if (CONTROLS[selfElement] === transitElement) {
    score += 2; relation = "self-spends";
    evidence.push("日主制流期五行，加 2 分");
  }
  let branchState = "none";
  if (natalBranch && transitBranch && COMBINES.has(`${natalBranch}${transitBranch}`)) {
    score += 5; branchState = "combine";
    evidence.push("日支与流期地支六合，加 5 分");
  } else if (natalBranch && transitBranch && CLASHES.has(`${natalBranch}${transitBranch}`)) {
    score -= 6; branchState = "clash";
    evidence.push("日支与流期地支相冲，减 6 分");
  }
  score = Math.max(45, Math.min(88, score));
  return { score, transitElement, relation, branchState, evidence };
}

// ---------- 喜用（幸运要素）推导 ----------
// 旧实现固定取 RESOURCE_FOR[selfElement]（日主之印），于是幸运色对同一个人恒定不变，
// 切今日/本周/本月/今年、换日期都不动。这里改成同时看「日主」与「流期」：
// 日主是本人底色，流期是当下时段——两者的生克关系决定此时该补什么、该泄什么。
// 同时权衡「日主 / 流期天干 / 流期地支 / 所问领域的十神」四方，给五个五行分别打分取最优。
// 演进：① 只取日主之印 → 幸运色对同一个人恒定不变；② 只看日主×流期天干 →
// 月柱与年柱同五行时"本月、今年"撞成同一个颜色。这里把流期地支与十神一起纳入，
// 四个时段、四个主题各自算出自己的喜用，幸运色才会真正跟着切换走。
// 喜用五行只由「日主 + 本时段流期」决定，与生活领域（事业/感情/…）无关。
// 这样幸运色、幸运时段等就只随"今日/本周/本月/今年"变化，切主题时保持不变。
function rankElements(selfElement, transitStemElement, transitBranchElement, branchState) {
  const scored = ELEMENT_ORDER.map((e) => {
    let s = 0;
    const why = [];
    if (PRODUCES[e] === selfElement) { s += 3; why.push("印绶护身"); }
    if (e === selfElement) { s += 2; why.push("比劫助身"); }
    if (CONTROLS[e] === selfElement) { s -= 3; why.push("克身不宜"); }
    // 流期权重给得比"日主底色"更高，否则印绶护身这类恒定加分会把结果锁死在同一个五行
    if (e === transitStemElement) { s += 2; why.push("顺势流期天干"); }
    if (CONTROLS[transitStemElement] === e) { s -= 3; why.push("受流期天干所制"); }
    if (CONTROLS[e] === transitStemElement) { s += 2; why.push("可制衡流期天干"); }
    if (e === transitBranchElement || PRODUCES[transitBranchElement] === e) { s += 2; why.push("得流期地支之气"); }
    if (CONTROLS[transitBranchElement] === e) { s -= 2; why.push("失流期地支之气"); }
    if (branchState === "clash" && e === RESOURCE_FOR[selfElement]) { s += 2; why.push("日支逢冲，取印通关"); }
    return { element: e, score: s, why };
  });
  scored.sort((a, b) => b.score - a.score || ELEMENT_ORDER.indexOf(a.element) - ELEMENT_ORDER.indexOf(b.element));
  return scored;
}

function bandOf(score) { return score >= 75 ? "high" : score >= 60 ? "mid" : "low"; }

// ---------- 解读文案生成 ----------
// 注意别在文案里重复"日主"二字——句子模板已含"你的X日主"，
// 早先写成"与你的火日主日主生流期"就是这样重复出来的。
const SELF_RELATION_PHRASE = {
  "transit-nourishes": "得流期生扶，底气较足",
  "transit-same": "与流期同气，行动力稳",
  "self-drains": "生流期而精力外泄",
  "transit-restrains": "受流期所制，压力偏大",
  "self-spends": "克流期而费力，但能掌控",
  "none": "与流期关系平缓"
};

// 各时段的影响跨度不同，说明文字必须体现"这段时间究竟有多长"
const PERIOD_TAIL = {
  today: "影响只覆盖这一天，适合处理当天能闭环的具体事",
  week: "影响覆盖整周，有相对完整的时间把计划落成可执行的排期",
  month: "影响持续约三十天，适合建立稳定标签并补齐方法",
  year: "影响贯穿全年，适合做长期布局、资质积累与信誉建设"
};

// 流期 × 该领域十神 → 状态描述（4 主题 × 5 种关系）
const TOPIC_PHRASE = {
  career: {
    "a-nourishes-b": "事业与学业上易得规则或上司加持，推进阻力小",
    "same": "事业节奏与流期合拍，按部就班就有收获",
    "b-nourishes-a": "事业上投入多而见效慢，宜先夯实再谈产出",
    "a-controls-b": "事业受外部约束明显，宜守规矩、少冒进",
    "b-controls-a": "你能反向塑造工作局面，但要控制投入强度",
    "none": "事业面平稳，维持既有节奏即可"
  },
  wealth: {
    "a-nourishes-b": "财星得流期生扶，正财路径较顺",
    "same": "财气与流期同气，宜按预算稳步执行",
    "b-nourishes-a": "钱财易向外流出，宜先守后攻",
    "a-controls-b": "财星受制，不宜新增支出与冒险项目",
    "b-controls-a": "你能主动争取财源，但要防用力过猛",
    "none": "财务面平稳，按常规节奏收支即可"
  },
  love: {
    "a-nourishes-b": "感情上对方态度较暖，适合主动表达",
    "same": "感情节奏平顺，宜用稳定陪伴积累默契",
    "b-nourishes-a": "感情上付出感偏重，宜先照顾好自己",
    "a-controls-b": "感情易受外部因素干扰，宜降低期待、少试探",
    "b-controls-a": "你在关系中有主导力，但别把控制当成关心",
    "none": "感情面平稳，保持自然相处即可"
  },
  social: {
    "a-nourishes-b": "人际上易得助力，适合求助、合作与引荐",
    "same": "人际氛围与你同频，适合维护核心圈子",
    "b-nourishes-a": "社交消耗偏大，宜筛掉低效应酬",
    "a-controls-b": "人际易有摩擦，宜低调、少争辩",
    "b-controls-a": "你在群体中有影响力，注意别过度承担",
    "none": "人际面平稳，维持常规社交距离"
  }
};

// 对应上面每种状态的具体做法，保证"状态+做法"整体随主题与时段落变化
const TOPIC_ACTION = {
  career: {
    "a-nourishes-b": "主动争取可见的任务与反馈",
    "same": "把清单推进到可交付状态",
    "b-nourishes-a": "先补齐方法与资料，再谈产出",
    "a-controls-b": "守住流程与承诺，减少变量",
    "b-controls-a": "控制节奏，别同时开多条线",
    "none": "维持既有节奏"
  },
  wealth: {
    "a-nourishes-b": "按预算推进既定财务计划",
    "same": "记账复盘，按规则执行",
    "b-nourishes-a": "先守后攻，预留应急金",
    "a-controls-b": "不加新支出，不碰不熟悉的项目",
    "b-controls-a": "主动争取收入，但留足安全边际",
    "none": "维持常规收支"
  },
  love: {
    "a-nourishes-b": "主动表达，安排一次认真相处",
    "same": "用稳定陪伴积累默契",
    "b-nourishes-a": "先照顾自己，别过度付出",
    "a-controls-b": "降低期待，少试探少追问",
    "b-controls-a": "给对方空间，别把关心变成控制",
    "none": "保持自然相处频率"
  },
  social: {
    "a-nourishes-b": "适合求助、合作与引荐",
    "same": "维护核心圈子，做深不做广",
    "b-nourishes-a": "筛掉低效应酬，保留精力",
    "a-controls-b": "低调少争辩，别硬碰",
    "b-controls-a": "发挥影响力，但别过度承担",
    "none": "维持常规社交距离"
  }
};

// 概述只讲"本时段日主与流期的关系"，不掺入生活领域——
// 领域差异交给下方解读区表达，否则切主题会让整段概述都变。
function overviewText(timekey, topickey, ctx) {
  const timeLabel = TIMEKEY_LABEL[timekey];
  const selfCN = ELEMENT_CN[ctx.selfElement];
  const supportCN = ELEMENT_CN[ctx.supportElement];
  const rel = SELF_RELATION_PHRASE[ctx.relation] || SELF_RELATION_PHRASE.none;
  return `${timeLabel}流期锚在${ctx.anchorGanZhi}（${ELEMENT_CN[ctx.transitStemElement]}${ELEMENT_CN[ctx.transitBranchElement]}），` +
    `你的${selfCN}日主${rel}。` +
    `${PERIOD_TAIL[timekey]}，宜以${supportCN}为用。${ELEMENT_ARCHETYPE[ctx.selfElement] || ""}`;
}

function adviceText(band, supportElement, topickey, topicRelation) {
  const supportCN = ELEMENT_CN[supportElement];
  const doMap = {
    high: `优先推进一件已有准备的事项到可交付状态；多用${supportCN}相关的方式（色彩、方位、时段）增强节奏感`,
    mid: `先确认信息与边界，再完成一个确定步骤；用${supportCN}气稳住心态，不宜贪多`,
    low: `减少临时承诺，把重要决定推迟到信息更完整时；以${supportCN}气养精蓄锐`
  };
  const avoidMap = {
    high: "避免因为顺风顺水就扩大摊子、答应超出能力的请求。",
    mid: "避免只做准备不推进，也不要把别人的需求全部接到自己身上。",
    low: "避免硬撑或仓促做重大决定，也不宜在情绪低位做长期承诺。"
  };
  return { do: `${doMap[band]}。`, avoid: avoidMap[band] };
}

function insightText(topickey, timekey, ctx) {
  const timeLabel = TIMEKEY_LABEL[timekey];
  const topicLabel = TOPIC_LABEL[topickey];
  const supportCN = ELEMENT_CN[ctx.supportElement];
  const starCN = ELEMENT_CN[ctx.topicStarElement];
  const state = TOPIC_PHRASE[topickey][ctx.topicRelation];
  const action = TOPIC_ACTION[topickey][ctx.topicRelation];
  return {
    title: `${timeLabel}${topicLabel}｜${ctx.starLabel}（${starCN}）`,
    body: `${timeLabel}锚在${ctx.anchorGanZhi}，${state}。${action}，宜以${supportCN}为用。`
  };
}

// ---------- 卡片组装 ----------
// opts.forceElement：同主题内四个时段可能算出同一个喜用（五行只有五种，四个时段必然可能撞）。
// 撞上时由 buildAllCards 指定改用次喜用，保证切换时段时幸运色确实会变。
function buildCard(profile, subject, targetDate, timekey, topickey, opts) {
  const chart = computeChart(profile);
  if (!chart.dayMasterElement) {
    return fail("DAY_MASTER_MISSING", "无法取得日主五行，不能生成运势卡片");
  }
  const selfElement = chart.dayMasterElement;
  const natalBranch = chart.dayBranch;
  const transit = transitGanZhi(targetDate);
  const anchor = periodAnchor(transit, timekey, targetDate);
  const base = scoreFor(selfElement, anchor.stem, natalBranch, anchor.branch);
  const { relation, branchState, evidence } = base;
  // 主题只影响解读：每个领域对应一个十神，流期对该十神的生克决定这一领域
  // 在本时段的顺逆。分数、幸运色等不参与——它们只随时段变化。
  const gender = profile.gender || "unknown";
  const stars = TOPIC_STARS[topickey](selfElement, gender);
  const topicStarElement = stars.primary;
  const starLabel = stars.primaryLabel;
  const transitStemElement = STEM_ELEMENT[anchor.stem] || selfElement;
  const transitBranchElement = BRANCH_ELEMENT[anchor.branch] || selfElement;
  const topicRelation = relationOf(transitStemElement, topicStarElement);
  const score = Math.max(45, Math.min(88, base.score));
  // 喜用只由日主与流期决定，切主题时幸运要素保持不变。
  const ranked = rankElements(selfElement, transitStemElement, transitBranchElement, branchState);
  const favorable = ranked[0];
  const forced = (opts && opts.forceElement) || null;
  const supportElement = forced || favorable.element;
  // 置顶：界面只展示前 4 条依据，放在末尾会被相冲/六合等条目挤掉。
  evidence.unshift(forced
    ? `喜用取${ELEMENT_CN[supportElement]}：同主题内其他时段已取${ELEMENT_CN[favorable.element]}，改用次喜用`
    : `喜用取${ELEMENT_CN[supportElement]}：${favorable.why.join("、")}`);
  const band = bandOf(score);
  const kw = TIMEKEY_KEYWORD[timekey][band];
  const ctx = {
    selfElement, supportElement, topicStarElement, starLabel, topicRelation, relation,
    transitStemElement, transitBranchElement, anchorGanZhi: `${anchor.stem}${anchor.branch}`
  };

  const lucky = {
    color: COLOR_BY_ELEMENT[supportElement].join("、"),
    colorHex: COLOR_HEX[supportElement],
    time: LUCKY_TIME[supportElement].join("、"),
    timeGlyph: TIME_GLYPH,
    direction: DIRECTION_BY_ELEMENT[supportElement],
    directionGlyph: DIRECTION_GLYPH[supportElement],
    number: HE_TU[supportElement].join("、"),
    numberGlyph: NUMBER_GLYPH,
    food: LUCKY_FOOD[supportElement],
    foodGlyph: FOOD_GLYPH[supportElement],
    accessory: LUCKY_ACCESSORY[supportElement],
    accessoryGlyph: ACCESSORY_GLYPH[supportElement]
  };
  const advice = adviceText(band, supportElement, topickey, topicRelation);
  const insight = insightText(topickey, timekey, ctx);

  const card = {
    subject,
    timekey,
    topickey,
    title: `${TIMEKEY_LABEL[timekey]}运势概述`,
    summary: `${TIMEKEY_LABEL[timekey]}${TIMEKEY_SUMMARY[timekey]}`,
    score: { value: score, scale: "45–88", label: band === "high" ? "顺势推进" : band === "mid" ? "稳中求进" : "放慢确认" },
    keyword: { label: `${TIMEKEY_LABEL[timekey]}关键词`, value: kw[0], desc: kw[1] },
    overview: overviewText(timekey, topickey, ctx),
    lucky,
    advice,
    insight: { ...insight, meta: `${TIMEKEY_LABEL[timekey]} · ${TOPIC_LABEL[topickey]} · ${starLabel}` },
    transit: {
      yearGanZhi: transit.year, monthGanZhi: transit.month, dayGanZhi: transit.day,
      anchorGanZhi: `${anchor.stem}${anchor.branch}`, timekey,
      topicStar: starLabel, topicStarElement: ELEMENT_CN[topicStarElement], topicRelation
    },
    bazi: { dayMaster: chart.dayMasterChar, dayMasterElement: ELEMENT_CN[selfElement], pillars: chart.pillars },
    favorableElement: supportElement,
    favorableRank: ranked.map((r) => r.element),
    evidence
  };
  return card;
}

// ---------- 视图快照 ----------
function normalizeChoice(value, allowed, fallback) {
  return allowed.includes(value) ? value : fallback;
}

function formatDate(date) {
  return `${date.year}-${String(date.month).padStart(2, "0")}-${String(date.day).padStart(2, "0")}`;
}

function targetFrom(input) {
  if (input.target_date) return parseDate(input.target_date, "target_date");
  const now = new Date();
  return { year: now.getFullYear(), month: now.getMonth() + 1, day: now.getDate() };
}

function buildSnapshot(input, options) {
  const opts = options || {};
  const subject = input.subject || "self";
  const timekey = normalizeChoice(input.timekey, ["today", "week", "month", "year"], "today");
  const topickey = normalizeChoice(input.topickey, ["career", "love", "wealth", "social"], "career");
  const target = targetFrom(input);
  const snapshot = {
    subject,
    timekey,
    topickey,
    target_date: formatDate(target),
    card: null,
    needs_profile: false,
    profile_message: "",
    card_error: ""
  };
  // 实例标识：界面从宿主 hostContext 拿到后原样回传，这里原样回显，
  // 让宿主能把结果路由回对应那张卡。宿主没下发就整个字段缺席。
  if (typeof input.instanceId === "string" && input.instanceId.trim()) {
    snapshot.instanceId = input.instanceId.trim();
  }
  if (opts.withCard === false) return snapshot;

  const profile = loadProfile(subject);
  if (!profile || !profile.birth_date) {
    snapshot.needs_profile = true;
    snapshot.profile_message = "还没有出生档案，无法计算八字与流期。请告诉元宝你的出生日期与时间（或由 metaphysics-profile 登记），回来刷新即可出卡。";
    return snapshot;
  }
  try {
    const card = buildCard(profile, subject, target, timekey, topickey);
    if (card && card.phase === "error") {
      snapshot.card_error = card.message || "卡片生成失败";
      return snapshot;
    }
    snapshot.card = card;
    // 一次性把 4 个时间维度 × 4 个主题共 16 张卡算好随包下发。
    // 界面切换时直接本地取用，不必再向宿主发起 tools/call——
    // 宿主对 UI 主动调用的支持程度不一致（有的不响应、有的拒绝），
    // 依赖它会导致"点了没反应"。本地切换则与宿主能力无关。
    if (opts.withAllCards !== false) {
      snapshot.cards = buildAllCards(profile, subject, target);
      // 主卡直接取去重后的那张，保证首屏内容与切到同一组合时完全一致。
      const same = snapshot.cards[timekey] && snapshot.cards[timekey][topickey];
      if (same) snapshot.card = same;
    }
  } catch (error) {
    snapshot.card_error = error.message || String(error);
  }
  return snapshot;
}

const PERIOD_ORDER = ["today", "week", "month", "year"];

function buildAllCards(profile, subject, target) {
  const all = {};
  for (const tk of PERIOD_ORDER) all[tk] = {};
  const topics = Object.keys(TOPIC_LABEL);
  // 喜用只随时段变化，所以先定好四个时段各自的喜用，再去重——
  // 若逐主题去重，会让同一时段内的四个主题弹出不同颜色，违背"主题只影响解读"。
  const natural = {};
  for (const tk of PERIOD_ORDER) {
    try {
      const card = buildCard(profile, subject, target, tk, topics[0]);
      if (card && card.phase !== "error") natural[tk] = card;
    } catch (error) {
      // 单个时段失败不影响其他时段，跳过即可。
    }
  }
  // 只保证四个时段互不相同：切"今日/本周/本月/今年"时幸运色要跟着变。
  // 五行有五种而时段只有四个，总能找到未被占用的。
  const used = new Set();
  const forced = {};
  for (const tk of PERIOD_ORDER) {
    const card = natural[tk];
    if (!card) continue;
    let el = card.favorableElement;
    if (used.has(el)) {
      const alt = (card.favorableRank || []).find((x) => !used.has(x));
      if (alt) el = alt;
    }
    used.add(el);
    forced[tk] = el;
  }
  for (const tk of PERIOD_ORDER) {
    for (const topic of topics) {
      try {
        const card = buildCard(profile, subject, target, tk, topic, {
          forceElement: forced[tk] === natural[tk]?.favorableElement ? null : forced[tk]
        });
        if (card && card.phase !== "error") all[tk][topic] = card;
      } catch (error) {
        // 单个组合失败不影响其他组合，跳过即可。
      }
    }
  }
  return all;
}

// ---------- 操作 ----------
function describeSkill() {
  return envelope(SKILL, {
    facts: { operation: "describe" },
    data: {
      operations: {
        describe: { required: [], optional: [] },
        get_card: { required: [], optional: ["subject", "target_date", "timekey", "topickey"] }
      },
      timekeys: TIMEKEY_LABEL,
      topics: TOPIC_LABEL,
      storage: { profileFile: PROFILE_FILE }
    },
    confidence: { level: "high", reasons: ["静态说明"] },
    warnings: [],
    source: { engineVersion: ENGINE_VERSION, policyVersion: POLICY_VERSION, calendarLibrary: CALENDAR_LIB, chartLibrary: CHART_LIB },
    audit: { pipeline: ["describe"] }
  });
}

function getCard(input) {
  const snapshot = buildSnapshot(input || {});
  const warnings = [];
  let confidence = { level: "high", reasons: ["八字与流期为确定性计算"] };
  if (snapshot.needs_profile) {
    warnings.push("尚未读取到出生档案，无法计算八字与运势。");
    confidence = { level: "medium", reasons: ["未找到本地档案"] };
  } else if (snapshot.card_error) {
    warnings.push(`卡片生成失败：${snapshot.card_error}`);
    confidence = { level: "low", reasons: ["卡片计算异常"] };
  } else {
    warnings.push("传统命理为娱乐性参考，不构成决策建议。");
  }
  return envelope(SKILL, {
    facts: { operation: "get_card", subject: snapshot.subject, timekey: snapshot.timekey, topickey: snapshot.topickey, score: snapshot.card ? snapshot.card.score.value : null, needs_profile: snapshot.needs_profile },
    // 不再附带 message：有卡片时它是"这是你的运势卡片"这类噪音，
    // 无卡片时又和 profile_message 重复（界面已在空态里单独渲染）。
    data: snapshot,
    confidence,
    warnings,
    source: { engineVersion: ENGINE_VERSION, policyVersion: POLICY_VERSION, calendarLibrary: CALENDAR_LIB, chartLibrary: CHART_LIB },
    audit: { pipeline: ["load-profile", "compute-chart", "transit", "score", "build-card"], storage: PROFILE_FILE }
  });
}

const OPERATIONS = {
  describe: describeSkill,
  get_card: getCard
};

function main() {
  if (VENDOR_ERROR) {
    return fail("RUNTIME_UNAVAILABLE", `无法加载计算依赖，暂时不能出卡。${VENDOR_ERROR.message}`, {
      hint: "把技能目录完整同步到运行环境后重试；依赖应位于 scripts/lib/third_party。"
    });
  }
  let request;
  try {
    request = parseRequest(process.argv);
  } catch (error) {
    return fail(error.code || "INVALID_REQUEST", error.message);
  }
  const operation = request.operation || (request.payload && request.payload.operation);
  if (!operation) return fail("INVALID_ARGUMENT", "缺少 operation");
  const payload = request.payload && typeof request.payload === "object" ? { ...request, ...request.payload } : request;
  const handler = OPERATIONS[operation];
  if (!handler) return fail("UNKNOWN_OPERATION", `不支持的操作：${operation}`);
  try {
    return handler(payload);
  } catch (error) {
    return fail(error.code || "CALCULATION_FAILED", error.message, { operation });
  }
}

try {
  process.stdout.write(JSON.stringify(main()));
} catch (error) {
  process.stdout.write(JSON.stringify(fail(error.code || "ENGINE_CRASH", error.message, { stack: String(error.stack || "").slice(0, 500) })));
}
