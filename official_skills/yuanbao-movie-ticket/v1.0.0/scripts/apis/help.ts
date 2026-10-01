/**
 * 帮助类：城市查询 / 定位
 *
 * 导出 fetchCityByName / fetchLocation 供其他 api 复用（影院/排片的城市解析）。
 * 命令函数 getCityByName / getLocation 供 run.ts 调用。
 */
import { maoyanApiGet } from '../lib/http.js';

type Raw = Record<string, unknown>;

// ── 可复用 fetch 函数 ────────────────────────────────────────────

export interface CityResult {
  success:   boolean;
  cityId?:   number;
  cityName?: string;
  pinyin?:   string;
  message?:  string;
}

/** 按城市名（汉字或拼音）查猫眼城市 ID */
export async function fetchCityByName(cityName: string): Promise<CityResult> {
  const res = await maoyanApiGet<Raw>('/mmcs/city/newcities.json', {}, '');
  const list = ((res as Raw).cts ?? ((res as Raw).data as Raw)?.cts ?? []) as Raw[];
  if (!list.length) return { success: false, message: '获取城市列表失败' };

  const name  = cityName.trim();
  const lower = name.toLowerCase();
  const hit = list.find(c => c.nm === name)
         ?? list.find(c => typeof c.py === 'string' && c.py.toLowerCase() === lower)
         ?? list.find(c => typeof c.nm === 'string' && (name.includes(c.nm as string) || (c.nm as string).includes(name)))
         ?? null;

  if (!hit) return { success: false, message: `未找到城市：${cityName}` };
  return { success: true, cityId: hit.id as number, cityName: String(hit.nm ?? ''), pinyin: String(hit.py ?? '') };
}

export interface LocationResult {
  success:   boolean;
  cityId?:   number;
  cityName?: string;
  lat?:      number;
  lng?:      number;
  message?:  string;
}

/** 经纬度获取城市信息（lat/lng 不传则 IP 定位兜底） */
export async function fetchLocation(lat?: number, lng?: number): Promise<LocationResult> {
  const res = await maoyanApiGet<Raw>(
    '/mmcs/city/getLocation.json',
    {
      ...(lat !== undefined ? { lat } : {}),
      ...(lng !== undefined ? { lng } : {}),
    },
    '',
  );
  if (res.success === false) {
    return { success: false, message: String((res as Raw).errMsg ?? (res as Raw).msg ?? '获取城市信息失败') };
  }
  const data = (res.data as Raw) || {};
  return {
    success:  true,
    cityId:   data.myCityId as number,
    cityName: String(data.myCity ?? ''),
    lat:      data.lat as number | undefined,
    lng:      data.lng as number | undefined,
  };
}

/** 获取用户经纬度（IP 定位兜底，失败降级 -1） */
export async function resolveLatLon(): Promise<{ lat: number; lng: number }> {
  try {
    const loc = await fetchLocation();
    if (loc.success && loc.lat != null && loc.lng != null) {
      return { lat: loc.lat, lng: loc.lng };
    }
  } catch { /* IP 定位失败，降级 -1 */ }
  return { lat: -1, lng: -1 };
}

// ── 命令函数（供 run.ts 调用）──────────────────────────────────

type Args = Record<string, string | number | boolean>;

/** get_city_by_name: 按城市名查 cityId */
export async function getCityByName(args: Args) {
  const cityName = String(args.cityName ?? '');
  if (!cityName) return { success: false, message: '缺少参数 cityName' };
  return await fetchCityByName(cityName);
}

/** get_location: 经纬度获取城市信息 */
export async function getLocation(args: Args) {
  const lat = args.lat !== undefined ? Number(args.lat) : undefined;
  const lng = args.lng !== undefined ? Number(args.lng) : undefined;
  const loc = await fetchLocation(lat, lng);
  if (!loc.success) return { success: false, message: loc.message };
  return {
    success:  true,
    cityId:   loc.cityId,
    cityName: loc.cityName,
    lat:      loc.lat,
    lng:      loc.lng,
  };
}
