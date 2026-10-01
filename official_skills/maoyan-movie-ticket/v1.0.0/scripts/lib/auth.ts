import { createHash } from 'crypto';
import { TA_CODE } from './config.js';

export interface TaHeader {
  Key:           string;
  Date:          string;
  Authorization: string;
}

/**
 * 构建 TA 签名请求头
 *
 * 算法与 m-trade @myfe/token-auth 完全一致：
 *   str = randKey + [keyValues, token, METHOD, date].join(TA_CODE) + randKey
 *   Authorization = MD5(str.toUpperCase())
 */
export function buildTaHeader(
  token:  string,
  method: 'GET' | 'POST',
  data:   Record<string, unknown> = {},
): TaHeader {
  const date    = new Date().toUTCString();
  const randKey = Math.random().toString(36).substring(2, 10);

  let keyValues = '';
  if (method === 'POST' && Object.keys(data).length > 0) {
    keyValues = Object.keys(data)
      .sort()
      .map(k => `${k}=${data[k]}`)
      .join('&');
  }

  const str = [randKey, [keyValues, token, method, date].join(TA_CODE), randKey].join('');
  const authorization = createHash('md5').update(str.toUpperCase(), 'utf8').digest('hex');

  return { Key: randKey, Date: date, Authorization: authorization };
}
