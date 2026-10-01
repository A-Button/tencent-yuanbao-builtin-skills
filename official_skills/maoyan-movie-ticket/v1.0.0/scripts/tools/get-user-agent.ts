/**
 * 获取 WorkBuddy User-Agent（供 HTTP 请求头使用）
 *
 * WorkBuddy 运行时自动注入 WORKBUDDY_APP_VERSION / WORKBUDDY_PRODUCT_NAME，
 * 构造格式：WorkBuddy/{version} (Macintosh; macOS {release}; {arch})
 *
 * 非 WorkBuddy 环境兜底为移动端 UA。
 */

import os from 'node:os';

const MOBILE_UA =
  'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';

/**
 * 获取当前环境应使用的 User-Agent 字符串
 */
export function getUserAgent(): string {
  const version = process.env.WORKBUDDY_APP_VERSION;
  if (!version) return MOBILE_UA;

  const product = process.env.WORKBUDDY_PRODUCT_NAME || 'WorkBuddy';

  const platformName = process.platform === 'darwin' ? 'Macintosh'
    : process.platform === 'win32' ? 'Windows'
    : 'Linux';

  const osRelease = os.release();
  const arch = os.arch();

  return `${product}/${version} (${platformName}; ${osRelease}; ${arch})`;
}
