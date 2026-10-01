import {
  detectPlatform, getPlatformJson, fetchRemoteVersion,
  writeLastCheckEpoch, fail,
} from "./_common.ts";
import { unlinkSync } from "node:fs";

if (process.argv[2] === "help") {
  console.log(
    `Usage: bun scripts/install-cli.ts\n\n` +
    `Download and install (or auto-update) tencent-video-cli for the current platform.`,
  );
  process.exit(0);
}

const p = detectPlatform();

// Ensure config directory exists
await Bun.write(p.configDir + "/.keep", "");

// ---- Helper: download, install, verify ----
async function downloadAndInstall(): Promise<string> {
  const res = await fetch(p.downloadUrl);
  if (!res.ok) {
    fail(`Download failed: HTTP ${res.status} from ${p.downloadUrl}`);
  }

  const buf = await res.arrayBuffer();

  if (!p.isWindows) {
    const proc = Bun.spawn(["chmod", "+x", "/dev/stdin"], {
      stdin: new Blob([buf]),
      stdout: "pipe",
      stderr: "pipe",
    });
    await proc.exited;
  }

  // Write to temp, verify, then replace
  const tmpPath = p.cliPath + ".tmp";
  await Bun.write(tmpPath, buf);

  if (!p.isWindows) {
    const proc = Bun.spawn(["chmod", "+x", tmpPath], { stderr: "pipe" });
    await proc.exited;
    if (proc.exitCode !== 0) fail("chmod +x failed");
  }

  // Verify new binary works
  const verifyProc = Bun.spawn([tmpPath, "version"], { stdout: "pipe", stderr: "pipe" });
  const version = (await new Response(verifyProc.stdout).text()).trim();
  if (verifyProc.exitCode !== 0 && verifyProc.exitCode !== null) {
    try { Deno.removeSync?.(tmpPath); } catch {}
    fail("Downloaded binary verification failed.");
  }

  await Bun.write(p.cliPath, buf);
  try { unlinkSync(tmpPath); } catch {}
  return version;
}

// ---- Main ----
const cliExists = await Bun.file(p.cliPath).exists();

if (!cliExists) {
  // Fresh install
  console.error(`Downloading ${p.binaryFilename} ...`);
  const version = await downloadAndInstall();
  await writeLastCheckEpoch(p.lastCheckFile);

  console.log(JSON.stringify({
    platform: getPlatformJson(p),
    installed: true,
    version,
    message: `CLI installed successfully (${version}).`,
  }, null, 2));
  process.exit(0);
}

// Already installed → auto-update check
const proc = Bun.spawn([p.cliPath, "version"], { stdout: "pipe" });
const localVersion = (await new Response(proc.stdout).text()).trim();

const remoteVersion = await fetchRemoteVersion();
if (!remoteVersion) {
  console.log(JSON.stringify({
    platform: getPlatformJson(p),
    installed: true,
    version: localVersion,
    message: "CLI is installed, could not check for updates.",
  }, null, 2));
  process.exit(0);
}

// Compare base versions
let hasUpdate = false;
if (localVersion != remoteVersion) {
  hasUpdate = true
}

if (!hasUpdate) {
  await writeLastCheckEpoch(p.lastCheckFile);
  console.log(JSON.stringify({
    platform: getPlatformJson(p),
    installed: true,
    version: localVersion,
    updateAvailable: false,
    message: "CLI is up to date.",
  }, null, 2));
  process.exit(0);
}

// Auto-apply update
console.error(`Updating ${localVersion} -> ${remoteVersion} ...`);
const newVersion = await downloadAndInstall();
await writeLastCheckEpoch(p.lastCheckFile);

console.log(JSON.stringify({
  platform: getPlatformJson(p),
  installed: true,
  previousVersion: localVersion,
  version: newVersion,
  updated: true,
  message: `CLI updated to ${newVersion}.`,
}, null, 2));
