import http from 'node:http';
import https from 'node:https';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { BASE_URL, MAOYAN_API_BASE, CHANNEL_ID, EXT_CHANNEL_ID, TIMEOUT_MS, AUTH_ENV } from './config.js';
import { buildTaHeader } from './auth.js';
import { URL } from 'node:url';
import { createRequire } from 'node:module';
import { getDeviceToken, getWorkBuddyClientType } from './util.js';
import { getUserAgent } from '../tools/get-user-agent.js';
import { SCRIPTS_ROOT } from './scripts-root.js';

const pkg = JSON.parse(readFileSync(join(SCRIPTS_ROOT, 'package.json'), 'utf-8'));
const SCRIPT_VERSION = pkg.version as string;

type Raw = Record<string, unknown>;

/** 构造猫眼接口通用请求头 */
export function maoyanHeaders(token?: string, extra?: Record<string, string>): Record<string, string> {
  return {
    Accept: 'application/json, text/plain, */*',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    Referer: 'https://m.maoyan.com/',
    'User-Agent': getUserAgent(),
    'X-Requested-With': 'ajax',
    'X-Channel-ID': CHANNEL_ID,
    channelId: CHANNEL_ID,
    extChannelId: EXT_CHANNEL_ID,
    uuid: getDeviceToken(),
    'Client-Type': getWorkBuddyClientType(),
    version: SCRIPT_VERSION,
    ...(token ? { token } : {}),
    ...extra,
  };
}

let cliguardLoaded = false;

function ensureCliguardLoaded(): void {
  if (cliguardLoaded) return;
  try {
    const require = createRequire(import.meta.url);
    require('@sec/cliguard');
    cliguardLoaded = true;
    console.error('[cliguard] 已加载，mtgsig 将自动注入');
  } catch (e) {
    console.error('[cliguard] 加载失败:', e instanceof Error ? e.message : e);
  }
}

interface NativeRes {
  status: number;
  data: string;
}

function nativeRequest(
  method: string,
  urlStr: string,
  headers: Record<string, string>,
  body: string | undefined,
  timeout: number,
): Promise<NativeRes> {
  ensureCliguardLoaded();

  return new Promise<NativeRes>((resolve, reject) => {
    const parsed = new URL(urlStr);
    const isHttps = parsed.protocol === 'https:';
    const mod = isHttps ? https : http;

    const req = mod.request({
      hostname: parsed.hostname,
      port: parsed.port || (isHttps ? 443 : 80),
      path: parsed.pathname + parsed.search,
      method,
      headers,
      timeout,
    }, (res) => {
      const chunks: Buffer[] = [];
      res.on('data', (chunk: Buffer) => chunks.push(chunk));
      res.on('end', () => {
        resolve({
          status: res.statusCode ?? 502,
          data: Buffer.concat(chunks).toString('utf-8'),
        });
      });
    });

    req.on('timeout', () => {
      req.destroy();
      reject(new Error('请求超时'));
    });
    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

/** GET 请求（m.maoyan.com 移动端接口） */
export async function maoyanGet<T = unknown>(
  path: string,
  params: Record<string, string | number | undefined>,
  token?: string,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null) qs.set(k, String(v));
  }
  const fullUrl = `${BASE_URL}${path}${qs.toString() ? '?' + qs.toString() : ''}`;

  try {
    const res = await nativeRequest('GET', fullUrl, maoyanHeaders(token, extraHeaders), undefined, TIMEOUT_MS);
    if (res.status < 200 || res.status >= 300) throw new Error(`HTTP ${res.status}: ${path}`);
    return JSON.parse(res.data) as T;
  } catch (err: unknown) {
    if (err instanceof Error && err.message === '请求超时') throw err;
    if (err instanceof Error && err.message.startsWith('HTTP')) throw err;
    throw err;
  }
}

function buildApiUrl(path: string, queryParams: Record<string, string | number | undefined>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(queryParams)) {
    if (v !== undefined && v !== null) qs.set(k, String(v));
  }
  const query = qs.toString() ? '?' + qs.toString() : '';
  if (/^https?:\/\//i.test(path)) return `${path}${query}`;
  if (path.startsWith('/')) return `${MAOYAN_API_BASE}${path}${query}`;
  const scheme = AUTH_ENV === 'test' ? 'http://' : 'https://';
  return `${scheme}${path}${query}`;
}

/** GET 请求（直连 api.maoyan.com，需要 TA 签名） */
export async function maoyanApiGet<T = unknown>(
  path: string,
  queryParams: Record<string, string | number | undefined> = {},
  token?: string,
  extraHeaders?: Record<string, string>,
): Promise<T> {
  const fullUrl = buildApiUrl(path, queryParams);
  const ta = buildTaHeader(token ?? '', 'GET', {});

  try {
    const res = await nativeRequest('GET', fullUrl, {
      ...maoyanHeaders(token, extraHeaders),
      'Cache-Control': 'no-cache',
      Origin: 'https://m.maoyan.com',
      Key: ta.Key,
      Date: ta.Date,
      Authorization: ta.Authorization,
    }, undefined, TIMEOUT_MS);

    if (res.status < 200 || res.status >= 300) throw new Error(`HTTP ${res.status}: ${path}`);
    return JSON.parse(res.data) as T;
  } catch (err: unknown) {
    if (err instanceof Error && err.message === '请求超时') throw err;
    if (err instanceof Error && err.message.startsWith('HTTP')) throw err;
    throw err;
  }
}

export type { Raw };
