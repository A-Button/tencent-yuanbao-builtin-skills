/**
 * Schedule query script for tencent-video-cli
 * Calls CLI `schedule <cid>` and formats the raw JSON into human-readable output.
 *
 * Usage:
 *   bun scripts/schedule.ts <cid>
 */

import { detectPlatform, fail } from "./_common.ts";

// ===== Type definitions (aligned with Go structs) =====

interface VideoPlanInfo {
  episode: number;
  personal_can_play: boolean;
  free_start_play_date: string;
  vip_start_play_date: string;
  svip_start_play_date: string;
  vid: string;
  free_can_play: boolean;
  vip_can_play: boolean;
  svip_can_play: boolean;
  period_name: string;
  title: string;
}

interface ScheduleData {
  cid: string;
  name: string;
  ip_online_status_id: string;
  premiere_time: string;
  free_episodes: number;
  pay_episodes: number;
  play_status: number;
  videos: VideoPlanInfo[];
  prompt_text: string;
  vip_status: number;
  c_type: number;
}

// ===== Play status enum =====
const PLAY_STATUS_MAP: Record<number, string> = {
  0: "无效",
  1: "敬请期待",
  2: "即将上线",
  3: "正在热播",
  4: "已完结",
};

// ===== Helpers =====

const WEEKDAYS = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];

function parseDate(dateStr: string): Date | null {
  if (!dateStr) return null;
  const d = new Date(dateStr);
  return isNaN(d.getTime()) ? null : d;
}

function formatDateFriendly(dateStr: string): string {
  const d = parseDate(dateStr);
  if (!d) return dateStr;

  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const target = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const diffDays = Math.round((target.getTime() - today.getTime()) / 86400000);

  const weekday = WEEKDAYS[d.getDay()];
  const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;

  let prefix: string;
  if (diffDays === 0) prefix = "今天";
  else if (diffDays === 1) prefix = "明天";
  else if (diffDays === 2) prefix = "后天";
  else prefix = `${d.getMonth() + 1}月${d.getDate()}日`;

  return `${prefix}（${weekday}）${time}`;
}

function playStatusText(status: number): string {
  return PLAY_STATUS_MAP[status] ?? `未知(${status})`;
}

function getNextPlayTime(v: VideoPlanInfo): string {
  if (v.svip_start_play_date) return formatDateFriendly(v.svip_start_play_date) + "（SVIP）";
  if (v.vip_start_play_date) return formatDateFriendly(v.vip_start_play_date) + "（VIP）";
  if (v.free_start_play_date) return formatDateFriendly(v.free_start_play_date);
  return "";
}

/** Derive update schedule from all episode dates, e.g. "周二 20:00、周三 20:00" */
function extractUpdateSchedule(videos: VideoPlanInfo[]): string {
  const weekdayTimeMap = new Map<string, string>();

  for (const v of videos) {
    const dateStr = v.vip_start_play_date || v.free_start_play_date;
    if (!dateStr) continue;

    const d = parseDate(dateStr);
    if (!d) continue;

    const weekday = WEEKDAYS[d.getDay()];
    const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;

    if (!weekdayTimeMap.has(weekday) || time) {
      weekdayTimeMap.set(weekday, time);
    }
  }

  if (weekdayTimeMap.size === 0) return "";

  const order = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  const parts: string[] = [];
  for (const wd of order) {
    const t = weekdayTimeMap.get(wd);
    if (t !== undefined) {
      parts.push(t ? `${wd} ${t}` : wd);
    }
  }
  return parts.join("、");
}

// ===== Main =====

const args = process.argv.slice(2);
if (args.length < 1 || args[0] === "help") {
  console.log("Usage: bun scripts/schedule.ts <cid>");
  console.log("  Queries the schedule for a given CID and prints formatted output.");
  process.exit(args[0] === "help" ? 0 : 1);
}

const cid = args[0];
const p = detectPlatform();

// Call CLI
const proc = Bun.spawn([p.cliPath, "schedule", cid], {
  stdout: "pipe",
  stderr: "pipe",
});

const stdout = await new Response(proc.stdout).text();
const stderr = await new Response(proc.stderr).text();
const exitCode = await proc.exited;

if (exitCode !== 0) {
  console.error(stderr || stdout);
  process.exit(1);
}

// Parse JSON
// CLI returns flat ScheduleData directly (no ret/msg/data wrapper)
let data: ScheduleData;
try {
  data = JSON.parse(stdout.trim());
} catch {
  console.error("Failed to parse CLI output as JSON");
  console.error(stdout);
  process.exit(1);
}

// ===== Format output =====
const lines: string[] = [];

lines.push(`🎬 ${data.name}`);
lines.push("");
lines.push(`📊 播出状态：${playStatusText(data.play_status)}`);
lines.push("");

const totalEpisodes = data.videos.length;
if (totalEpisodes > 0) {
  // Count aired episodes (those with any play date)
  let airedCount = 0;
  let nextEpisode: VideoPlanInfo | undefined;

  for (const v of data.videos) {
    if (v.free_start_play_date || v.vip_start_play_date || v.svip_start_play_date) {
      airedCount++;
    } else if (!nextEpisode && v.episode > 0) {
      nextEpisode = v;
    }
  }

  if (data.play_status === 4) {
    // 已完结
    lines.push(`📺 共 ${totalEpisodes} 集（已完结）`);
  } else if (data.pay_episodes > 0) {
    const remaining = Math.max(0, data.pay_episodes - airedCount);
    lines.push(`📺 已更新 ${airedCount}/${data.pay_episodes} 集，还剩 ${remaining} 集未播出`);
  } else {
    lines.push(`📺 已更新 ${airedCount} 集`);
  }
  lines.push("");

  if (data.free_episodes > 0) {
    lines.push(`🔓 免费可看：${data.free_episodes} 集`);
    lines.push("");
  }

  // VIP advance episodes
  const vipAdvanceCount = data.videos.filter((v) => v.vip_can_play && !v.free_can_play).length;
  if (vipAdvanceCount > 0) {
    lines.push(`👑 VIP 可多看 ${vipAdvanceCount} 集`);
    lines.push("");
  }

  // SVIP advance episodes
  const svipAdvanceCount = data.videos.filter((v) => v.svip_can_play && !v.vip_can_play).length;
  if (svipAdvanceCount > 0) {
    lines.push(`👑 SVIP 可多看 ${svipAdvanceCount} 集`);
    lines.push("");
  }

  // Update schedule
  const schedule = extractUpdateSchedule(data.videos);
  if (schedule) {
    lines.push(`📅 更新日程：${schedule}`);
    lines.push("");
  }

  // Next episode time
  if (nextEpisode) {
    const nextTime = getNextPlayTime(nextEpisode);
    if (nextTime) {
      lines.push(`⏰ 下一集（第 ${nextEpisode.episode} 集）播出时间：${nextTime}`);
      lines.push("");
    }
  }
}

if (data.premiere_time) {
  lines.push(`🎬 首播时间：${data.premiere_time}`);
  lines.push("");
}

if (data.prompt_text) {
  lines.push(`💡 ${data.prompt_text}`);
  lines.push("");
}

// Recent episodes
if (data.videos.length > 0) {
  lines.push("📋 最近集数信息：");
  const startIdx = Math.max(0, data.videos.length - 5);
  for (let i = startIdx; i < data.videos.length; i++) {
    const v = data.videos[i];
    if (v.episode === 0) continue;

    let status: string;
    if (v.free_can_play) status = "✅ 免费可看";
    else if (v.vip_can_play) status = "👑 VIP可看";
    else if (v.svip_can_play) status = "👑 SVIP可看";
    else if (v.free_start_play_date || v.vip_start_play_date) status = "📅 待播出";
    else status = "⏳ 未定";

    let timeInfo = "";
    const playTime = getNextPlayTime(v);
    if (playTime && !v.free_can_play && !v.vip_can_play && !v.svip_can_play) {
      timeInfo = `（${playTime}）`;
    }

    const title = v.title || `第${v.episode}集`;
    lines.push(`  第 ${v.episode} 集：${title} ${status}${timeInfo}`);
  }
}

console.log(lines.join("\n"));
