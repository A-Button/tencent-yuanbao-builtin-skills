/**
 * 影片相关：热映榜单 / 搜索 / 详情 / 可观影日期
 *
 * 命令函数：recommendHotMovies / searchMovies / getMovieDetail / getMovieShowDays
 * 复用函数：fetchHotMoviesList / fetchMovieDetailById（供 shows/seat 等复用）
 */
import { maoyanApiGet } from '../lib/http.js';
import { CHANNEL_ID, CITY_ID } from '../lib/config.js';
import { resizeImg } from '../lib/util.js';

type Raw = Record<string, unknown>;
type Args = Record<string, string | number | boolean>;

// ── 归一化函数 ─────────────────────────────────────────────────

function normalizeHotMovie(m: Raw) {
  return {
    movieId:         m.id,
    name:            m.nm,
    img:             resizeImg(m.img),
    score:           m.sc,
    releaseDate:     m.rt,
    star:            m.star,
    showInfo:        m.showInfo,
    wish:            m.wish,
    version:         m.version || '',
    preShow:         m.preShow ?? false,
    globalReleased:  m.globalReleased ?? false,
    showStateButton: m.showStateButton
      ? { content: (m.showStateButton as Raw).content, color: (m.showStateButton as Raw).color }
      : null,
  };
}

function normalizeSearchMovie(m: Raw) {
  return {
    movieId: String(m.id || ''),
    name:    m.nm   || '',
    img:     resizeImg(m.img),
    score:   m.sc   != null ? String(m.sc) : '',
    showst:  m.showst ?? null,
    cat:     String(m.cat || '').replace(/,/g, '/'),
    dur:     Number(m.dur  ?? 0),
    pubDesc: m.pubDesc || m.showInfo || '',
    wish:    m.wish ?? 0,
    star:    m.act  || m.star || '',
  };
}

// ── 可复用 fetch 函数 ──────────────────────────────────────────

/** 拉取热映列表（normalizeHotMovie 格式） */
export async function fetchHotMoviesList(cityId: number, limit: number) {
  const res = await maoyanApiGet<Raw>(
    '/mmdb/movie/v3/list/hot.json',
    { ct: cityId, ci: cityId, channelId: CHANNEL_ID },
    '',
  );
  const rawList = ((res.data as Raw)?.hot as Raw[]) || [];
  return rawList.slice(0, limit).map(normalizeHotMovie);
}

/** 拉取单部影片完整详情 */
export async function fetchMovieDetailById(movieId: string) {
  const res = await maoyanApiGet<Raw>(
    `/mmdb/movie/v5/${encodeURIComponent(movieId)}.json`,
    { needCouponLabel: 'true', channelId: CHANNEL_ID, ci: CITY_ID },
    '',
  );
  const m = ((res.data as Raw)?.movie ?? {}) as Raw;
  const actors = String(m.star ?? m.act ?? '').split(',').map(s => s.trim()).filter(Boolean);
  const posterUrl = resizeImg(
    (m.img as Record<string, string>)?.dynamicUrl
    ?? (m.img as Record<string, string>)?.url
    ?? (typeof m.img === 'string' ? m.img : undefined)
  ) || undefined;
  return {
    movieId:     String(m.id ?? movieId),
    title:       String(m.nm ?? ''),
    enTitle:     m.enm ? String(m.enm) : undefined,
    genre:       m.cat ? String(m.cat).split(',').slice(0, 3).join('/') : '',
    duration:    Number(m.dur ?? 0),
    score:       m.sc ? parseFloat(String(m.sc)) : undefined,
    scoreLabel:  m.scoreLabel ? String(m.scoreLabel) : undefined,
    description: m.dra ? String(m.dra) : undefined,
    director:    m.dr  ? String(m.dr)  : undefined,
    actors:      actors.length ? actors : undefined,
    poster:      posterUrl,
    releaseDate: m.pubDesc ? String(m.pubDesc) : undefined,
    wish:        Number(m.wish ?? 0) || undefined,
    ver:         m.ver ? String(m.ver) : undefined,
  };
}

// ── 命令函数 ───────────────────────────────────────────────────

/** recommend_hot_movies: 热映榜单 + 并发补全详情 */
export async function recommendHotMovies(args: Args) {
  const ci        = args.cityId !== undefined ? Number(args.cityId) : Number(CITY_ID);
  const safeLimit = Math.min(Math.max(1, args.limit !== undefined ? Number(args.limit) : 8), 10);

  const hotMovies = await fetchHotMoviesList(ci, safeLimit);
  if (!hotMovies.length) return { total: 0, movies: [] };

  const detailResults = await Promise.allSettled(
    hotMovies.map(m => fetchMovieDetailById(String(m.movieId ?? ''))),
  );

  const movies = hotMovies.map((hot, i) => {
    const settled = detailResults[i];
    const d = settled.status === 'fulfilled' ? settled.value : null;
    const imgFallback = typeof hot.img === 'string'
      ? hot.img
      : (hot.img as Record<string, string> | null)?.url ?? '';
    const poster = d?.poster || imgFallback;
    return {
      movieId:         hot.movieId,
      name:            hot.name,
      poster,
      score:           d?.score ?? (hot.score != null ? parseFloat(String(hot.score)) : undefined),
      scoreLabel:      d?.scoreLabel,
      genre:           d?.genre,
      duration:        d?.duration,
      description:     d?.description,
      director:        d?.director,
      actors:          d?.actors
                       ?? (hot.star
                           ? String(hot.star).split(',').map(s => s.trim()).filter(Boolean)
                           : undefined),
      releaseDate:     d?.releaseDate ?? (hot.releaseDate ? String(hot.releaseDate) : undefined),
      showInfo:        hot.showInfo,
      wish:            hot.wish,
      version:         hot.version,
      showStateButton: hot.showStateButton,
    };
  });

  return { total: movies.length, movies };
}

/** search_movies: 关键词搜索影片（只返回 showst=3/4） */
export async function searchMovies(args: Args) {
  const keyword = String(args.keyword ?? '');
  if (!keyword) return { success: false, message: '缺少参数 keyword' };
  const cityId = args.cityId !== undefined ? Number(args.cityId) : Number(CITY_ID);
  const lat = args.lat !== undefined ? Number(args.lat) : undefined;
  const lng = args.lng !== undefined ? Number(args.lng) : undefined;

  const res = await maoyanApiGet<Raw>(
    '/mmdb/search/integrated/keyword/v2/list.json',
    {
      keyword,
      offset:         0,
      stype:          JSON.stringify([{ type: 0 }]),
      iscorrected:    'false',
      ci:             cityId,
      channelId:      CHANNEL_ID,
      limit:           10,
      utm_medium:     'iphone',
      requestVersion: 0,
      ...(lat !== undefined ? { lat } : {}),
      ...(lng !== undefined ? { lng } : {}),
    },
    '',
  );
  const list  = (res.data as Raw);
  const group = Array.isArray((list as Raw)?.list) ? ((list as Raw).list as Raw[])[0] : null;
  const raw   = (group?.list as Raw[]) || [];
  const movies = raw
    .filter(m => m.showst === 3 || m.showst === 4)
    .slice(0, 10)
    .map(normalizeSearchMovie);
  return { total: movies.length, movies };
}

/** get_movie_detail: 单部影片详情 */
export async function getMovieDetail(args: Args) {
  const movieId = String(args.movieId ?? '');
  if (!movieId) return { success: false, message: '缺少参数 movieId' };
  return await fetchMovieDetailById(movieId);
}

/** get_movie_show_days: 影片可观影日期 */
export async function getMovieShowDays(args: Args) {
  const movieId = String(args.movieId ?? '');
  if (!movieId) return { success: false, message: '缺少参数 movieId' };
  const cityId    = args.cityId    !== undefined ? Number(args.cityId)    : Number(CITY_ID);
  const channelId = String(args.channelId ?? CHANNEL_ID);

  const res = await maoyanApiGet<Raw>(
    '/mmcs/show/v1/movie/showdays.json',
    { movieId, cityId, channelId },
    '',
  );
  const raw   = (res.data as Raw) || res;
  const dates = ((raw.dates as Raw[]) || []).map(d => ({
    date:          String(d.date ?? ''),
    isPredate:     Boolean(d.isPredate ?? false),
    labelResource: d.labelResource ?? null,
  }));
  return { total: dates.length, dates };
}
