/**
 * 影院相关：附近影院 / 搜索 / 详情 / 按影片查影院
 *
 * 三个列表工具共用 resolveCityLocation（城市/经纬度三级解析 + IP 兜底）。
 * 命令函数：getNearbyCinemas / searchCinemas / getCinemaDetail / getCinemasByMovie
 * 复用函数：fetchCinemasByMovie
 */
import { maoyanApiGet } from '../lib/http.js';
import { CHANNEL_ID, CITY_ID } from '../lib/config.js';
import { fetchCityByName, fetchLocation } from './help.js';
import { todayBJT } from '../tools/filter-cinema-show.js';

type Raw = Record<string, unknown>;
type Args = Record<string, string | number | boolean>;

// ── 标签 emoji 映射 ────────────────────────────────────────────

const EMOJI_REF_COLORS: { emoji: string; r: number; g: number; b: number }[] = [
  { emoji: '\u{1F7E2}', r: 76,  g: 175, b: 80  },  // 🟢
  { emoji: '\u{1F535}', r: 33,  g: 150, b: 243 },  // 🔵
  { emoji: '\u{1F7E0}', r: 255, g: 152, b: 0   },  // 🟠
  { emoji: '\u{1F7EA}', r: 156, g: 39,  b: 176 },  // 🟣
  { emoji: '\u{1F7E1}', r: 255, g: 235, b: 59  },  // 🟡
  { emoji: '\u{1F534}', r: 244, g: 67,  b: 54  },  // 🔴
  { emoji: '\u{1F7E4}', r: 121, g: 85,  b: 72  },  // 🟤
  { emoji: '⚪',     r: 255, g: 255, b: 255 },  // ⚪
  { emoji: '⚫',     r: 38,  g: 38,  b: 38  },  // ⚫
];

function colorToEmoji(hex: string): string {
  if (!hex || hex === 'undefined' || hex === 'null') return '';
  const h = hex.replace('#', '');
  if (h.length < 6) return '';
  const r = parseInt(h.substring(0, 2), 16);
  const g = parseInt(h.substring(2, 4), 16);
  const b = parseInt(h.substring(4, 6), 16);
  if (isNaN(r) || isNaN(g) || isNaN(b)) return '';
  let best = EMOJI_REF_COLORS[0];
  let bestDist = Infinity;
  for (const ref of EMOJI_REF_COLORS) {
    const dr = r - ref.r, dg = g - ref.g, db = b - ref.b;
    const dist = dr * dr + dg * dg + db * db;
    if (dist < bestDist) { bestDist = dist; best = ref; }
  }
  return best.emoji;
}

/** 影院标签归一化 */
function normalizeCinemaLabels(c: Raw): { name: string; color: string; borderColor: string; emoji: string }[] {
  const rawTags = (c.tags as Raw[]) || (c.labels as Raw[]) || (c.cinemaLabelResource as Raw[]) || [];
  return rawTags.map((l: Raw) => {
    const name = String(l.label || l.name || l.desc || '');
    const color = String(l.color || '');
    return {
      name,
      color,
      borderColor: String(l.borderColor || l.color || ''),
      emoji: colorToEmoji(color),
    };
  }).filter(l => l.name);
}

// ── 归一化函数 ─────────────────────────────────────────────────

function normalizeNearbyCinema(c: Raw) {
  const labels    = normalizeCinemaLabels(c);
  const priceDesc = String(c.priceDesc || '');
  const sellPrice = priceDesc ? parseFloat(priceDesc.replace(/[^0-9.]/g, '')) || null
                   : (c.sellPrice != null ? parseFloat(String(c.sellPrice)) || null : null);
  return {
    cinemaId:    c.id,
    name:        c.name  || c.nm    || '',
    addr:        c.addr  || c.address || '',
    distance:    c.distanceDesc || c.distance || '',
    sellPrice,
    priceDesc,
    labels,
  };
}

function normalizeSearchCinema(c: Raw) {
  return {
    cinemaId:  String(c.id || ''),
    name:      String(c.nm || c.name || ''),
    addr:      String(c.addr || c.address || ''),
    distance:  String(c.distanceDesc || (c.distance ? `${c.distance}km` : '')),
    sellPrice: parseFloat(String(c.sellPrice)) || 0,
    labels:    normalizeCinemaLabels(c),
  };
}

function normalizeCinemaByMovie(cinema: Raw) {
  const labels    = normalizeCinemaLabels(cinema);
  const labelNames = labels.map(l => l.name);
  const priceDesc = String(cinema.priceDesc || '');
  const sellPrice = priceDesc ? parseFloat(priceDesc.replace(/[^0-9.]/g, '')) || null : null;
  return {
    cinemaId:    cinema.id,
    name:        cinema.name || '',
    addr:        cinema.addr || '',
    distance:    cinema.distance || '',
    sellPrice,
    priceDesc,
    allowRefund: labelNames.some(l => l.includes('退票')),
    endorse:     labelNames.some(l => l.includes('改签')),
    snack:       labelNames.some(l => l.includes('小食') || l.includes('小吃')),
    labels,
    shows: ((cinema.cellShows as Raw[]) || []).map((s: Raw) => {
      const seat = (s.seatStatus as Raw) || {};
      return {
        seqNo:     s.seqNo || '',
        showId:    s.showId || '',
        tm:        s.tm || '',
        dt:        s.dt || '',
        lang:      s.lang || '',
        tp:        s.tp || '',
        hallName:  s.hallName || '',
        sellPr:    s.sellPr ?? null,
        sellPrice: s.sellPr ?? null,
        seatRemain: seat.remain ?? null,
        seatTotal:  seat.total ?? null,
        nextDimensionUrl: s.nextDimensionUrl || '',
      };
    }),
  };
}

/** 去掉常见影院后缀，提取核心关键词 */
function extractCinemaKeyword(input: string): string {
  const suffixes = ['电影院', '电影城', '影院', '影城', '影都', '剧院', '剧场'];
  let kw = input.trim();
  for (const s of suffixes) {
    if (kw.endsWith(s) && kw.length > s.length) { kw = kw.slice(0, -s.length); break; }
  }
  return kw.trim();
}

// ── 城市/经纬度解析（三级优先级 + IP 兜底，三个工具共用）────────

interface ResolvedLocation {
  cityId:      number;
  lat?:        number;
  lng?:        number;
  hasLocation: boolean;
}

async function resolveCityLocation(args: Args): Promise<ResolvedLocation> {
  let cityId: number | null = null;
  let resolvedLat = args.lat !== undefined ? Number(args.lat) : undefined;
  let resolvedLng = args.lng !== undefined ? Number(args.lng) : undefined;

  if (args.cityId !== undefined) {
    cityId = Number(args.cityId);
  } else if (args.cityName) {
    const cityResult = await fetchCityByName(String(args.cityName));
    if (cityResult.success && cityResult.cityId) {
      cityId = cityResult.cityId;
    }
  }
  // IP 定位兜底：经纬度缺失时补 lat/lng 和 cityId
  if (!(resolvedLat && resolvedLng)) {
    const ipLoc = await fetchLocation();
    if (ipLoc.success) {
      if (!(resolvedLat && resolvedLng)) {
        resolvedLat = ipLoc.lat;
        resolvedLng = ipLoc.lng;
      }
      if (!cityId) {
        cityId = ipLoc.cityId as number;
      }
    }
  }
  if (!cityId) cityId = Number(CITY_ID);
  return { cityId, lat: resolvedLat, lng: resolvedLng, hasLocation: !!(resolvedLat && resolvedLng) };
}

// ── 可复用 fetch 函数 ──────────────────────────────────────────

/** 按影片查影院（含场次价格），供 shows 的 recommend_nearby_shows 复用 */
export async function fetchCinemasByMovie(
  movieId:  string,
  showDate: string,
  cityId:   number,
  options?: { lat?: number; lng?: number; sort?: string; offset?: number; limit?: number },
): Promise<{ success: boolean; cinemas: ReturnType<typeof normalizeCinemaByMovie>[]; message?: string }> {
  const { lat, lng, sort = 'distance', offset = 0, limit = 20 } = options ?? {};
  try {
    const res = await maoyanApiGet<Raw>(
      '/mmcs/cinema/movie/cinemas.json',
      {
        movieId, showDate, cityId, ci: cityId,
        channelId: CHANNEL_ID, offset, limit,
        lat: lat ?? -1, lng: lng ?? -1, sort,
        districtId: -1, lineId: -1, areaId: -1, stationId: -1,
        brandId: -1, brandIds: '[-1]',
        hallTypeId: 'all', hallTypeIds: '["all"]',
        serviceId: -1, serviceIds: '[-1]',
        languageId: 'all', languageIds: '["all"]',
        dimId: 'all', dimIds: '["all"]',
        utm_term: '7.5', client: 'iphone',
      },
      '',
    );
    const data   = (res.data as Raw) || {};
    const list   = (data.cinemas as Raw[]) || [];
    return { success: true, cinemas: list.map(normalizeCinemaByMovie) };
  } catch (e) {
    return { success: false, cinemas: [], message: String(e) };
  }
}

// ── 命令函数 ───────────────────────────────────────────────────

/** get_nearby_cinemas: 附近影院列表 */
export async function getNearbyCinemas(args: Args) {
  const { cityId, lat, lng, hasLocation } = await resolveCityLocation(args);
  const sort   = args.sort !== undefined ? String(args.sort) : (hasLocation ? 'distance' : 'price');
  const offset = args.offset !== undefined ? Number(args.offset) : 0;
  const limit  = args.limit  !== undefined ? Number(args.limit)  : 20;

  const res = await maoyanApiGet<Raw>(
    '/mmcs/cinema/v1/select/cinemas.json',
    {
      cityId, ci: cityId,
      lat:  hasLocation ? lat : -1,
      lng:  hasLocation ? lng : -1,
      sort, offset, limit,
      channelId: CHANNEL_ID,
      utm_term: '7.5', client: 'iphone',
    },
    '',
  );
  const data   = (res.data as Raw) || {};
  const list   = (data.cinemas as Raw[]) || [];
  const paging = (data.paging as Raw) || {};
  const cinemas = list.map(normalizeNearbyCinema).map(c => ({
    ...c,
    distance: hasLocation ? c.distance : '',
  }));
  return {
    total:   paging.total ?? list.length,
    hasMore: paging.hasMore ?? false,
    offset:  paging.offset ?? offset,
    cinemas,
  };
}

/** search_cinemas: 按关键词搜索影院 */
export async function searchCinemas(args: Args) {
  const keyword = String(args.keyword ?? '');
  if (!keyword) return { success: false, message: '缺少参数 keyword' };
  const kw = extractCinemaKeyword(keyword);
  const { cityId, lat, lng, hasLocation } = await resolveCityLocation(args);

  const res = await maoyanApiGet<Raw>(
    '/mmdb/search/integrated/keyword/v2/list.json',
    {
      keyword:        kw,
      offset:         0,
      stype:          JSON.stringify([{ type: 2 }]),
      iscorrected:    'false',
      ci:             cityId,
      channelId:      CHANNEL_ID,
      limit:          10,
      utm_medium:     'iphone',
      requestVersion: 0,
      ...(hasLocation ? { lat, lng } : {}),
    },
    '',
  );
  const groups = ((res.data as Raw)?.list as Raw[]) || [];
  const group  = groups.find(g => g.type === 2);
  const list   = (group?.list as Raw[]) || [];
  const cinemas = list.map(normalizeSearchCinema).map(c => ({
    ...c,
    distance: hasLocation ? c.distance : '',
  }));
  return { total: cinemas.length, cinemas };
}

/** get_cinema_detail: 影院详情 */
export async function getCinemaDetail(args: Args) {
  const cinemaId = String(args.cinemaId ?? '');
  if (!cinemaId) return { success: false, message: '缺少参数 cinemaId' };
  const res = await maoyanApiGet<Raw>(
    '/mmcs/cinema/v1/cinema.json',
    { cinemaId, channelId: CHANNEL_ID },
    '',
  );
  const c = (res.data as Raw) || {};
  return {
    cinemaId:  String(c.id ?? cinemaId),
    name:      c.nm    || c.name    || '',
    addr:      c.addr  || c.address || '',
    phone:     c.tel   || c.phone   || '',
    lat:       c.lat,
    lng:       c.lng,
    sellPrice: c.sellPrice ? parseFloat(String(c.sellPrice)) : undefined,
    poiId:     c.poiId || c.poi_id  || '',
    labels:    normalizeCinemaLabels(c),
  };
}

/** get_cinemas_by_movie: 按影片查有排片的影院 */
export async function getCinemasByMovie(args: Args) {
  const movieId = String(args.movieId ?? '');
  if (!movieId) return { success: false, message: '缺少参数 movieId' };
  const { cityId, lat, lng, hasLocation } = await resolveCityLocation(args);
  const showDate = args.showDate ? String(args.showDate) : todayBJT();
  const sort   = args.sort   !== undefined ? String(args.sort)   : (hasLocation ? 'distance' : 'price');
  const offset = args.offset !== undefined ? Number(args.offset) : 0;
  const limit  = args.limit  !== undefined ? Number(args.limit)  : 20;

  const result = await fetchCinemasByMovie(movieId, showDate, cityId, {
    lat: hasLocation ? lat : undefined,
    lng: hasLocation ? lng : undefined,
    sort, offset, limit,
  });
  if (!result.success) {
    return { success: false, message: result.message };
  }
  const cinemas = result.cinemas.map(c => ({
    ...c,
    distance: hasLocation ? c.distance : '',
  }));
  return { total: cinemas.length, hasMore: false, offset, cinemas };
}
