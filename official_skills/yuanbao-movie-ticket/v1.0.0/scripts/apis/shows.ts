/**
 * 排片相关：单影院排片 / 编排查影院排片
 *
 * 命令函数：getCinemaShow / recommendNearbyShows
 * 复用函数：fetchCinemaShows / normalizeMovieShows（供 seat 复用）
 *
 * 过滤逻辑走 filterCinemaShow（服务端确定性执行，含已开场过滤 + 5 级兜底）。
 */
import { maoyanApiGet } from '../lib/http.js';
import { CHANNEL_ID, CITY_ID } from '../lib/config.js';
import { fetchCityByName, fetchLocation } from './help.js';
import { fetchCinemasByMovie } from './cinema.js';
import { filterCinemaShow, todayBJT } from '../tools/filter-cinema-show.js';
import { resizeImg } from '../lib/util.js';

type Raw = Record<string, unknown>;
type Args = Record<string, string | number | boolean>;

// ── 归一化函数 ─────────────────────────────────────────────────

function normalizeShow(p: Raw) {
  return {
    seqNo:         String(p.seqNo ?? ''),
    startTime:     String(p.tm    ?? ''),
    date:          String(p.dt    ?? ''),
    language:      String(p.lang  ?? ''),
    dimension:     String(p.tp    ?? ''),
    hall:          String(p.hn ?? p.th ?? ''),
    sellPrice:         p.sellPr            != null ? parseFloat(String(p.sellPr))            || 0 : null,
    originalPrice:     p.baseSellPrice     != null ? parseFloat(String(p.baseSellPrice))     || 0 : null,
    discountPrice:     p.discountSellPrice != null ? parseFloat(String(p.discountSellPrice)) || 0 : null,
  };
}

export function normalizeMovieShows(movie: Raw) {
  return {
    movieId:        String(movie.id   ?? ''),
    name:           String(movie.nm   ?? ''),
    img:            resizeImg(movie.img),
    desc:           String(movie.desc ?? ''),
    score:          movie.sc  != null ? parseFloat(String(movie.sc)) : null,
    duration:       movie.dur != null ? Number(movie.dur) : null,
    globalReleased: Boolean(movie.globalReleased ?? false),
    shows: ((movie.shows as Raw[]) || []).map((s: Raw) => ({
      showDate: String(s.showDate ?? ''),
      dateShow: String(s.dateShow ?? ''),
      plist:    ((s.plist as Raw[]) || []).map(normalizeShow),
    })),
  };
}

// ── 可复用 fetch 函数 ──────────────────────────────────────────

/** 拉取影院完整排片（原始数据，含 cinema/cinemaAddr/movies） */
export async function fetchCinemaShows(
  cinemaId:   string,
  cityId:     number,
  channelId?: string,
): Promise<{ success: boolean; data: Raw; message?: string }> {
  const params: Record<string, string | number | undefined> = {
    cinemaId,
    ci:        cityId,
    channelId: channelId ?? CHANNEL_ID,
  };
  const res = await maoyanApiGet<Raw>('/mmcs/show/v2/cinema/shows.json', params, '');
  if (!res.success || !(res.data as Raw)?.movies) {
    return { success: false, data: {}, message: '暂无排片信息' };
  }
  return { success: true, data: (res.data as Raw) };
}

// ── 城市解析（复用 help + IP 兜底）────────────────────────────

async function resolveCity(args: Args): Promise<{ cityId: number; lat?: number; lng?: number; hasLocation: boolean }> {
  let cityId: number | null = null;
  let resolvedLat = args.lat !== undefined ? Number(args.lat) : undefined;
  let resolvedLng = args.lng !== undefined ? Number(args.lng) : undefined;

  if (args.cityId !== undefined) {
    cityId = Number(args.cityId);
  } else if (args.cityName) {
    const r = await fetchCityByName(String(args.cityName));
    if (r.success && r.cityId) cityId = r.cityId;
  }
  if (!(resolvedLat && resolvedLng)) {
    const ipLoc = await fetchLocation();
    if (ipLoc.success) {
      if (!(resolvedLat && resolvedLng)) { resolvedLat = ipLoc.lat; resolvedLng = ipLoc.lng; }
      if (!cityId) cityId = ipLoc.cityId as number;
    }
  }
  if (!cityId) cityId = Number(CITY_ID);
  return { cityId, lat: resolvedLat, lng: resolvedLng, hasLocation: !!(resolvedLat && resolvedLng) };
}

// ── 命令函数 ───────────────────────────────────────────────────

/** get_cinema_show: 影院排片（含 filterCinemaShow 过滤 + 兜底） */
export async function getCinemaShow(args: Args) {
  const cinemaId = String(args.cinemaId ?? '');
  if (!cinemaId) return { success: false, message: '缺少参数 cinemaId' };
  const cityId    = args.cityId    !== undefined ? Number(args.cityId)    : Number(CITY_ID);
  const channelId = args.channelId !== undefined ? String(args.channelId) : undefined;

  const result = await fetchCinemaShows(cinemaId, cityId, channelId);
  if (!result.success) {
    return { success: false, message: result.message };
  }
  const cinemaInfo = (result.data.cinema as Raw) || (result.data.cinemaInfo as Raw) || {};
  const movies     = ((result.data.movies as Raw[]) || []).map(normalizeMovieShows);

  const filtered = filterCinemaShow({
    movies,
    cinemaName: String(cinemaInfo.name ?? cinemaInfo.nm ?? ''),
    cinemaAddr: String(cinemaInfo.addr ?? cinemaInfo.address ?? ''),
    movieId:    args.movieId    !== undefined ? String(args.movieId)    : undefined,
    showDate:   args.showDate    !== undefined ? String(args.showDate) : undefined,
    timeRange:  args.timeRange   !== undefined ? String(args.timeRange) : undefined,
  });

  return {
    success:           !filtered.empty,
    cinemaName:        filtered.cinemaName,
    cinemaAddr:        filtered.cinemaAddr,
    movies:            filtered.movies,
    empty:             filtered.empty,
    movieChanged:      filtered.movieChanged,
    dateChanged:       filtered.dateChanged,
    noDateAvailable:   filtered.noDateAvailable,
    timeRangeRelaxed:  filtered.timeRangeRelaxed,
    appliedMovieId:    filtered.appliedMovieId,
    appliedShowDate:   filtered.appliedShowDate,
    appliedTimeRange:  filtered.appliedTimeRange,
  };
}

/** recommend_nearby_shows: 编排（定位城市 → 查最近2家影院 → 过滤排片） */
export async function recommendNearbyShows(args: Args) {
  const movieId = String(args.movieId ?? '');
  if (!movieId) return { success: false, message: '缺少参数 movieId' };
  const targetDate = args.showDate  ? String(args.showDate)  : todayBJT();
  const timeRange  = args.timeRange ? String(args.timeRange) : undefined;
  const { cityId, lat, lng, hasLocation } = await resolveCity(args);

  // Step2: 查最近 2 家有该影片排片的影院
  const cinemaResult = await fetchCinemasByMovie(movieId, targetDate, cityId, {
    lat: hasLocation ? lat : undefined,
    lng: hasLocation ? lng : undefined,
    sort: 'distance', limit: 2,
  });
  if (!cinemaResult.success || cinemaResult.cinemas.length === 0) {
    return { success: false, message: '附近暂无该影片的排片影院' };
  }

  // Step3&4: 并发查排片 + 过滤
  const cinemas = await Promise.all(
    cinemaResult.cinemas.map(async cinema => {
      const cid = String(cinema.cinemaId ?? '');
      const showRes = await fetchCinemaShows(cid, cityId);
      if (!showRes.success) {
        return {
          cinemaId: cid, cinemaName: cinema.name, cinemaAddr: cinema.addr,
          distance: cinema.distance, success: false,
          message: showRes.message ?? '获取排片失败',
        };
      }
      const movies = ((showRes.data.movies as Raw[]) || []).map(normalizeMovieShows);
      const filtered = filterCinemaShow({
        movies,
        cinemaName: String(cinema.name ?? ''),
        cinemaAddr: String(cinema.addr ?? ''),
        movieId, showDate: targetDate, timeRange,
      });
      return {
        cinemaId:          cid,
        cinemaName:        filtered.cinemaName,
        cinemaAddr:        filtered.cinemaAddr,
        distance:          cinema.distance,
        success:           !filtered.empty,
        movies:            filtered.movies,
        empty:             filtered.empty,
        movieChanged:      filtered.movieChanged,
        dateChanged:       filtered.dateChanged,
        noDateAvailable:   filtered.noDateAvailable,
        timeRangeRelaxed:  filtered.timeRangeRelaxed,
        appliedMovieId:    filtered.appliedMovieId,
        appliedShowDate:   filtered.appliedShowDate,
        appliedTimeRange:  filtered.appliedTimeRange,
        requestedMovieId:  movieId,
        requestedDate:     targetDate,
        requestedTimeRange: timeRange ?? null,
      };
    }),
  );

  return { success: true, cityId, lat, lng, cinemas };
}
