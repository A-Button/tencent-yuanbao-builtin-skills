// show-qrcode.ts — Generate QR code login HTML page
// Usage: bun scripts/show-qrcode.ts <png_path> <qr_code_id>
// Output: <html_path>

import { readFileSync, writeFileSync, existsSync } from "fs";
import { resolve, join } from "path";

const pngPath = process.argv[2];
const qrCodeId = process.argv[3] || "unknown";

if (!pngPath || !existsSync(pngPath)) {
  console.error("Usage: bun scripts/show-qrcode.ts <png_path> <qr_code_id>");
  console.error(`Error: PNG file not found: ${pngPath}`);
  process.exit(1);
}

const pngData = readFileSync(pngPath);
const base64 = pngData.toString("base64");

const html = `<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>腾讯视频 登录</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #1a1a2e; color: #e0e0e0;
    display: flex; justify-content: center; align-items: center;
    min-height: 100vh; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .card {
    background: #16213e; border-radius: 20px; padding: 48px 40px; text-align: center;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
  }
  .card h2 { font-size: 22px; font-weight: 600; margin-bottom: 4px; color: #fff; }
  .card .sub { font-size: 13px; color: #888; margin-bottom: 28px; }
  .card img { width: 256px; height: 256px; border-radius: 12px;
    background: #fff; padding: 8px; }
  .tip { margin-top: 28px; font-size: 13px; color: #aaa; line-height: 1.8; }
  .tip em { color: #ffb74d; font-style: normal; font-weight: 500; }
</style>
</head>
<body>
<div class="card">
  <h2>腾讯视频 扫码登录</h2>
  <p class="sub">请使用腾讯视频 App 扫描二维码</p>
  <img src="data:image/png;base64,${base64}" alt="登录二维码">
  <div class="tip">
    扫码后在 App 中点击「确认登录」<br>
    确认完毕后，请回到对话框回复 <em>【扫码完成】</em>
  </div>
</div>
</body>
</html>`;

const outPath = resolve(process.cwd(), ".workbuddy", "qrcode-login.html");
writeFileSync(outPath, html, "utf-8");
console.log(outPath);
