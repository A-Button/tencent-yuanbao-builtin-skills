/**
 * 通用工具：图片缩放 + 设备标识
 */
import { readFileSync, writeFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { v1, v4 } from 'uuid';
import { SCRIPTS_ROOT } from './scripts-root.js';

/** 缩放图片 URL：pipi.cn 用 imageMogr2/thumbnail/120x，美团 CDN 用 @200w_280h_1e */
export function resizeImg(url: unknown): string {
  if (!url || typeof url !== 'string') return '';
  if (url.includes('pipi.cn') || url.includes('imageMogr2')) {
    const base = url.split('?')[0];
    return `${base}?imageMogr2/thumbnail/120x`;
  }
  const base = url.replace(/@[\d]+w_[\d]+h_[\de]+q?\d?$/, '');
  return `${base}@200w_280h_1e`;
}

const DEVICE_TOKEN_FILE = join(SCRIPTS_ROOT, '.device-token');

/**
 * 获取持久化的设备标识。
 * 算法对齐美团 m-trade uuid 中间件：uuid v1 + uuid v4 去掉连字符后转大写。
 */
export function getDeviceToken(): string {
  try {
    if (existsSync(DEVICE_TOKEN_FILE)) {
      const cached = readFileSync(DEVICE_TOKEN_FILE, 'utf-8').trim();
      if (cached) return cached;
    }
    const dt = (v1() + v4()).replace(/-/g, '').toUpperCase();
    writeFileSync(DEVICE_TOKEN_FILE, dt, 'utf-8');
    return dt;
  } catch {
    return (v1() + v4()).replace(/-/g, '').toUpperCase();
  }
}

export type ClientType = 'mac' | 'windows' | 'miniprogram' | 'pc';

/**
 * 判定当前运行环境。优先读 WORKBUDDY_CLIENT_TYPE / YUANBAO_CLIENT_TYPE，否则按 process.platform 推断。
 */
export function getWorkBuddyClientType(): ClientType {
  const envType = (
    process.env.YUANBAO_CLIENT_TYPE ||
    process.env.WORKBUDDY_CLIENT_TYPE ||
    ''
  ).toLowerCase();
  if (envType === 'mac' || envType === 'windows' || envType === 'miniprogram') return envType;
  if (envType === 'pc') return process.platform === 'darwin' ? 'mac' : 'windows';
  if (process.platform === 'darwin') return 'mac';
  if (process.platform === 'win32') return 'windows';
  if (process.platform === 'linux') return 'miniprogram';
  return 'pc';
}
