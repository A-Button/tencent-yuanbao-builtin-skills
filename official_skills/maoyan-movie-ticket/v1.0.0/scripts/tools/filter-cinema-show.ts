/**
 * filterCinemaShow — 排片数据过滤纯函数（不请求接口、不暴露为子命令）
 *
 * 被 get_cinema_show / recommend_nearby_shows 内部调用，按 movieId + showDate + timeRange
 * 过滤排片数据。带 5 级兜底：
 *   1. 全影院无排片              → empty
 *   2. 指定影片不存在            → movieChanged（切到第一个有排片的影片）
 *   3. 影片存在但无任何排片日期  → noDateAvailable（切到第一个有排片的其他影片）
 *   4. 指定日期无场次            → dateChanged（切到同影片第一个有场次的日期）
 *   5. timeRange 过滤后无场次    → timeRangeRelaxed（放宽时间过滤，返回该日期该影片全部场次）
 *
 * timeRange 解析逻辑移植自 wxapp/skills/maoyan-discovery/utils/filter-cinema-moive-time-range.js
 */

// ── 类型定义（与 shows/index.ts 的 normalizeMovieShows 返回结构一致，结构类型匹配即可）──

interface PlistItem {
  seqNo:         string;
  startTime:     string;
  date:          string;
  language:      string;
  dimension:     string;
  hall:          string;
  sellPrice:     number | null;
  originalPrice: number | null;
  discountPrice: number | null;
}

interface NormalizedShow {
  showDate: string;
  dateShow: string;
  plist:    PlistItem[];
}

interface NormalizedMovie {
  movieId:        string;
  name:           string;
  img:            string;
  desc:           string;
  score:          number | null;
  duration:       number | null;
  globalReleased: boolean;
  shows:          NormalizedShow[];
}

export interface FilteredMovie {
  movieId:        string;
  name:           string;
  score:          number | null;
  desc:           string;
  globalReleased: boolean;
  shows:          Array<{ showDate: string; plist: PlistItem[] }>;
}

export interface FilterCinemaShowResult {
  cinemaName:       string;
  cinemaAddr:       string;
  movies:           FilteredMovie[];
  // 兜底标志
  empty:            boolean;   // 全影院无排片
  movieChanged:     boolean;   // 影片不存在，已切换影片
  dateChanged:      boolean;   // 目标日期无场次，已切换日期
  noDateAvailable:  boolean;   // 影片无任何排片日期，已切换影片+日期
  timeRangeRelaxed: boolean;   // timeRange 过滤后无场次，已放宽时间过滤
  // 实际生效的过滤条件（兜底后可能跟入参不同）
  appliedMovieId:   string;
  appliedShowDate:  string;
  appliedTimeRange: string | null;
}

// ── 时间段解析（移植自 wxapp）─────────────────────────────────────

/** HH:mm → 分钟数 */
function toMinutes(tm: string): number {
  const parts = (tm || '').split(':');
  return (+parts[0] || 0) * 60 + (+parts[1] || 0);
}

/**
 * 解析时间段描述，返回 [startMinutes, endMinutes] 或 null
 * 支持：上午/下午/晚上、xx点后/前（含半、含时段前缀）、xx点到xx点、
 *       HH:mm 后/前、HH:mm 到 HH:mm、HH:mm（精确±30分钟）
 */
export function parseTimeRange(timeRange: string): [number, number] | null {
  if (!timeRange) return null;
  if (timeRange === '上午') return [0, 720];
  if (timeRange === '下午') return [720, 1080];
  if (timeRange === '晚上') return [1080, 1440];

  // 中文点时间 + 后/前（含可选时段前缀和「半」）
  // '7点后' '晚上7点后' '下午3点半以后' '上午9点前'
  const periodHour = timeRange.match(/^(上午|下午|晚上)?\s*(\d{1,2})点(半)?\s*(以?后|以?上|以?前|以?下)$/);
  if (periodHour) {
    const period = periodHour[1];
    let hour = Number(periodHour[2]);
    const half = periodHour[3] === '半';
    const direction = periodHour[4];
    if ((period === '下午' || period === '晚上') && hour !== 12) hour += 12;
    const base = hour * 60 + (half ? 30 : 0);
    if (/后|上/.test(direction)) return [base, 1440];
    if (/前|下/.test(direction)) return [0, base];
  }

  const rangeMatch = timeRange.match(/(\d+)点到(\d+)点/);
  if (rangeMatch) return [Number(rangeMatch[1]) * 60, Number(rangeMatch[2]) * 60];

  const hhmmAfter = timeRange.match(/^(\d{1,2}):(\d{2})\s*(以?后|以?上)$/);
  if (hhmmAfter) {
    const base = Number(hhmmAfter[1]) * 60 + Number(hhmmAfter[2]);
    return [base, 1440];
  }

  const hhmmBefore = timeRange.match(/^(\d{1,2}):(\d{2})\s*(以?前|以?下)$/);
  if (hhmmBefore) {
    const base = Number(hhmmBefore[1]) * 60 + Number(hhmmBefore[2]);
    return [0, base];
  }

  const hhmmRange = timeRange.match(/^(\d{1,2}):(\d{2})\s*到\s*(\d{1,2}):(\d{2})$/);
  if (hhmmRange) {
    const start = Number(hhmmRange[1]) * 60 + Number(hhmmRange[2]);
    const end = Number(hhmmRange[3]) * 60 + Number(hhmmRange[4]);
    return [start, end];
  }

  const exactMatch = timeRange.match(/^(\d{1,2}):(\d{2})$/);
  if (exactMatch) {
    const base = Number(exactMatch[1]) * 60 + Number(exactMatch[2]);
    return [base - 30, base + 30];
  }

  return null;
}

// ── 当前北京时间 YYYY-MM-DD ───────────────────────────────────────

export function todayBJT(): string {
  const now    = new Date();
  const offset = 8 * 60 * 60 * 1000;
  const bjt    = new Date(now.getTime() + now.getTimezoneOffset() * 60000 + offset);
  const y      = bjt.getFullYear();
  const m      = String(bjt.getMonth() + 1).padStart(2, '0');
  const d      = String(bjt.getDate()).padStart(2, '0');
  return `${y}-${m}-${d}`;
}

// ── 内部辅助 ──────────────────────────────────────────────────────

/** 找第一个有非空 plist 的 movie + show */
function firstAvailable(movies: NormalizedMovie[]): { movie: NormalizedMovie; show: NormalizedShow } | null {
  for (const m of movies) {
    for (const s of m.shows) {
      if (s.plist.length > 0) return { movie: m, show: s };
    }
  }
  return null;
}

/** 按时间段过滤 plist */
function filterPlistByTime(plist: PlistItem[], range: [number, number]): PlistItem[] {
  return plist.filter(p => {
    const min = toMinutes(p.startTime);
    return min >= range[0] && min < range[1];
  });
}

/** 当前北京时间当天的分钟数（用于判断场次是否已开场） */
function nowBJTMinutes(): number {
  const now    = new Date();
  const offset = 8 * 60 * 60 * 1000;
  const bjt    = new Date(now.getTime() + now.getTimezoneOffset() * 60000 + offset);
  return bjt.getHours() * 60 + bjt.getMinutes();
}

/**
 * 过滤已开场场次：仅对今天生效，剔除 startTime <= 当前北京时间的场次。
 * 已开场场次无法购票，展示无意义。非今天的场次原样返回。
 */
function filterStartedShows(plist: PlistItem[], showDate: string): PlistItem[] {
  if (showDate !== todayBJT()) return plist;
  const nowMin = nowBJTMinutes();
  return plist.filter(p => toMinutes(p.startTime) > nowMin);
}

/** 对排片数据中所有今天的场次过滤掉已开场场次（原地改 movies 副本） */
function stripStartedShows(movies: NormalizedMovie[]): NormalizedMovie[] {
  return movies.map(m => ({
    ...m,
    shows: m.shows.map(s => ({
      ...s,
      plist: filterStartedShows(s.plist, s.showDate),
    })),
  }));
}

// ── 主过滤函数 ────────────────────────────────────────────────────

export interface FilterCinemaShowParams {
  movies:     NormalizedMovie[];   // 排片数据（get_cinema_show / recommend_nearby_shows 内部传入）
  cinemaName: string;
  cinemaAddr: string;
  movieId?:   string;              // 可选，不传=全部影片
  showDate?:  string;              // 可选，不传=默认今天 BJT
  timeRange?: string;              // 可选，如"晚上"/"19点后"/"19:30到21:30"
}

export function filterCinemaShow(params: FilterCinemaShowParams): FilterCinemaShowResult {
  const { cinemaName, cinemaAddr } = params;
  // 第一步：先过滤掉已开场场次（仅对今天生效），再做后续过滤
  const movies          = stripStartedShows(params.movies);
  const requestedMovieId = params.movieId || '';
  const requestedDate    = params.showDate || todayBJT();
  const timeRangeStr     = params.timeRange || '';
  const timeRange        = parseTimeRange(timeRangeStr);

  const emptyResult: FilterCinemaShowResult = {
    cinemaName, cinemaAddr, movies: [],
    empty: false, movieChanged: false, dateChanged: false,
    noDateAvailable: false, timeRangeRelaxed: false,
    appliedMovieId: '', appliedShowDate: '', appliedTimeRange: timeRangeStr || null,
  };

  // ── 0. 全影院无排片 ──────────────────────────────────────────
  if (!movies.length || !movies.some(m => m.shows.some(s => s.plist.length > 0))) {
    return { ...emptyResult, empty: true };
  }

  // ── 不传 movieId：返回指定日期的所有影片（入口 B 场景）────────
  if (!requestedMovieId) {
    const filtered: FilteredMovie[] = [];
    let relaxed = false;

    for (const m of movies) {
      const showDay = m.shows.find(s => s.showDate === requestedDate && s.plist.length > 0);
      if (!showDay) continue;

      let plist = showDay.plist;
      if (timeRange) {
        const filteredPlist = filterPlistByTime(plist, timeRange);
        if (filteredPlist.length === 0) {
          // 该影片在该时段无场次，放宽时间过滤（标记 relaxed）
          relaxed = true;
        } else {
          plist = filteredPlist;
        }
      }
      if (!plist.length) continue;

      filtered.push({
        movieId: m.movieId, name: m.name, score: m.score,
        desc: m.desc, globalReleased: m.globalReleased,
        shows: [{ showDate: showDay.showDate, plist }],
      });
    }

    if (!filtered.length) {
      // 指定日期无任何影片有场次 → 切到第一个有排片的日期
      const fa = firstAvailable(movies);
      if (fa) {
        return filterCinemaShow({
          movies, cinemaName, cinemaAddr,
          showDate: fa.show.showDate, timeRange: timeRangeStr,
        });
      }
      return { ...emptyResult, empty: true };
    }

    return {
      cinemaName, cinemaAddr, movies: filtered,
      empty: false, movieChanged: false, dateChanged: false,
      noDateAvailable: false, timeRangeRelaxed: relaxed,
      appliedMovieId: '', appliedShowDate: requestedDate, appliedTimeRange: timeRangeStr || null,
    };
  }

  // ── 传了 movieId：定位影片（带兜底）──────────────────────────

  // 1. 影片不存在 → movieChanged
  let targetMovie = movies.find(m => m.movieId === requestedMovieId);
  let movieChanged = false;
  let noDateAvailable = false;

  if (!targetMovie) {
    const fa = firstAvailable(movies);
    if (!fa) return { ...emptyResult, empty: true };
    targetMovie = fa.movie;
    movieChanged = true;
  } else {
    // 2. 影片存在但无任何排片 → noDateAvailable
    const hasPlist = targetMovie.shows.some(s => s.plist.length > 0);
    if (!hasPlist) {
      const fa = firstAvailable(movies);
      if (!fa) return { ...emptyResult, empty: true };
      targetMovie = fa.movie;
      noDateAvailable = true;
    }
  }

  // 3. 目标日期精确匹配
  let targetShow = targetMovie.shows.find(s => s.showDate === requestedDate && s.plist.length > 0);
  let dateChanged = false;

  // 4. 目标日期无场次 → dateChanged
  if (!targetShow) {
    const firstDate = targetMovie.shows.find(s => s.plist.length > 0);
    if (!firstDate) {
      return { ...emptyResult, empty: true };
    }
    targetShow = firstDate;
    dateChanged = true;
  }

  // 5. timeRange 过滤
  let plist = targetShow.plist;
  let timeRangeRelaxed = false;
  if (timeRange) {
    const filteredPlist = filterPlistByTime(plist, timeRange);
    if (filteredPlist.length === 0) {
      // 时段无场次 → 放宽时间过滤
      timeRangeRelaxed = true;
    } else {
      plist = filteredPlist;
    }
  }

  const resultMovie: FilteredMovie = {
    movieId: targetMovie.movieId, name: targetMovie.name, score: targetMovie.score,
    desc: targetMovie.desc, globalReleased: targetMovie.globalReleased,
    shows: [{ showDate: targetShow.showDate, plist }],
  };

  return {
    cinemaName, cinemaAddr, movies: [resultMovie],
    empty: false, movieChanged, dateChanged, noDateAvailable, timeRangeRelaxed,
    appliedMovieId: targetMovie.movieId, appliedShowDate: targetShow.showDate,
    appliedTimeRange: timeRangeRelaxed ? null : (timeRangeStr || null),
  };
}
