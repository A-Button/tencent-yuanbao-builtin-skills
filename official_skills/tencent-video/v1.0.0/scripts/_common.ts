/**
 * Common utilities for tencent-video-cli scripts
 * Adapted from tencent-news skill
 */

import { homedir, platform } from "os";
import { join } from "path";

// ===== CDN URLs =====
const CDN_BASE = "https://community.image.video.qpic.cn/tencent-cli";
export const VERSION_URL = `${CDN_BASE}/version.txt`;
export const DOWNLOAD_BASE = CDN_BASE;

// ===== Platform detection =====
export interface PlatformInfo {
  os: "macos" | "linux" | "windows";
  arch: "x64" | "arm64";
  isWindows: boolean;
  cliName: string;
  cliPath: string;
  configDir: string;
  credentialsFile: string;
  lastCheckFile: string;
  detectedShell: string;
  helpCommand: string;
  /** e.g. "tencent-video-cli-darwin-arm64" */
  binaryFilename: string;
  /** full download URL for this platform */
  downloadUrl: string;
}

export function detectPlatform(): PlatformInfo {
  const os = platform();
  const arch = process.arch === "arm64" ? "arm64" : "x64";
  const isWindows = os === "win32";
  const cliName = isWindows ? "tencent-video-cli.exe" : "tencent-video-cli";
  const configDir = join(homedir(), ".config", "tencent-video-skill");

  // Detect shell
  let detectedShell = "bash";
  if (isWindows) {
    detectedShell = "powershell";
  } else if (process.env.SHELL?.includes("zsh")) {
    detectedShell = "zsh";
  }

  const goOs = os === "darwin" ? "darwin" : isWindows ? "windows" : "linux";
  const goArch = arch === "x64" ? "amd64" : "arm64";
  const binaryFilename = `tencent-video-cli-${goOs}-${goArch}${isWindows ? ".exe" : ""}`;

  return {
    os: os === "darwin" ? "macos" : isWindows ? "windows" : "linux",
    arch,
    isWindows,
    cliName,
    cliPath: join(configDir, cliName),
    configDir,
    credentialsFile: join(configDir, "credentials"),
    lastCheckFile: join(configDir, ".last_update_check"),
    detectedShell,
    helpCommand: isWindows
      ? `& "${join(configDir, cliName)}" help`
      : `${join(configDir, cliName)} help`,
    binaryFilename,
    downloadUrl: `${DOWNLOAD_BASE}/${binaryFilename}`,
  };
}

export function getPlatformJson(p: PlatformInfo) {
  return {
    os: p.os,
    arch: p.arch,
    cliName: p.cliName,
    cliPath: p.cliPath,
    configDir: p.configDir,
    helpCommand: p.helpCommand,
  };
}

// ===== Update check =====
export const DEFAULT_UPDATE_WINDOW_SECONDS = 86400; // 24 hours

export async function readLastCheckEpoch(filepath: string): Promise<number> {
  try {
    const file = Bun.file(filepath);
    if (!(await file.exists())) return 0;
    const content = await file.text();
    const epoch = parseInt(content.trim(), 10);
    return isNaN(epoch) ? 0 : epoch;
  } catch {
    return 0;
  }
}

export async function writeLastCheckEpoch(filepath: string): Promise<void> {
  await Bun.write(filepath, String(Math.floor(Date.now() / 1000)));
}

/**
 * Fetch remote version from CDN
 * @returns version string like "1.0.0+ca3d9af" or null on failure
 */
export async function fetchRemoteVersion(): Promise<string | null> {
  try {
    const res = await fetch(VERSION_URL);
    if (!res.ok) return null;
    return (await res.text()).trim();
  } catch {
    return null;
  }
}

// ===== Auth state =====
export interface AuthState {
  authenticated: boolean;
  vuid?: string;
  vusessionValid?: boolean;
  vurefreshValid?: boolean;
  canAutoRefresh?: boolean;
  credentialsFile?: string;
  error?: string;
}

export async function getAuthState(p: PlatformInfo): Promise<AuthState> {
  try {
    // Check if credentials file exists
    const file = Bun.file(p.credentialsFile);
    if (!(await file.exists())) {
      return {
        authenticated: false,
        credentialsFile: p.credentialsFile,
      };
    }

    // Run CLI status command
    const proc = Bun.spawn([p.cliPath, "status"], {
      stdout: "pipe",
      stderr: "pipe",
    });
    const output = await new Response(proc.stdout).text();
    const stderr = await new Response(proc.stderr).text();
    const exitCode = proc.exitCode;

    if (exitCode !== 0) {
      return {
        authenticated: false,
        error: stderr || output,
        credentialsFile: p.credentialsFile,
      };
    }

    // Parse status output
    const isLoggedIn = output.includes("状态: 已登录");
    const isExpired = output.includes("Status: Session expired");
    const vuidMatch = output.match(/VUID:\s*(.+)/);
    const vuid = vuidMatch ? vuidMatch[1].trim() : undefined;

    return {
      authenticated: isLoggedIn,
      vuid,
      vusessionValid: isLoggedIn,
      vurefreshValid: !isExpired || isLoggedIn,
      canAutoRefresh: isLoggedIn,
      credentialsFile: p.credentialsFile,
    };
  } catch (error) {
    return {
      authenticated: false,
      error: String(error),
      credentialsFile: p.credentialsFile,
    };
  }
}

// ===== Error handling =====
export function fail(message: string): never {
  console.error(JSON.stringify({ error: message }, null, 2));
  process.exit(1);
}
