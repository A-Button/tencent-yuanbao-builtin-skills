/**
 * 配置：渠道/城市/域名/TA 签名 code
 *
 * 所有配置默认值内联；需调试覆盖时通过 process.env 注入。
 * 唯一需要 .env 的变量是 ENV（控制环境切换），由 env.ts 加载。
 */

export const CHANNEL_ID = '1';
export const EXT_CHANNEL_ID = '1000558';
export const CITY_ID = process.env.CITY_ID ?? '1';
export const BASE_URL = 'https://m.maoyan.com';
export const TA_CODE = process.env.TA_CODE ?? '43e936102090e926';
export const TIMEOUT_MS = 10_000;

const AUTH_ENV_RAW = process.env.ENV ?? 'prod';
if (!['test', 'st', 'prod'].includes(AUTH_ENV_RAW)) {
  throw new Error(`不支持的 ENV: ${AUTH_ENV_RAW}，仅支持 test / st / prod`);
}
export const AUTH_ENV = AUTH_ENV_RAW as 'test' | 'st' | 'prod';

const MAOYAN_API_BASE_MAP: Record<string, string> = {
  test: 'http://api.movie.test.sankuai.com/api',
  st:   'https://api.movie.st.sankuai.com/api',
  prod: 'https://api.maoyan.com',
};
export const MAOYAN_API_BASE = process.env.MAOYAN_API_BASE ?? MAOYAN_API_BASE_MAP[AUTH_ENV] ?? MAOYAN_API_BASE_MAP.prod;
