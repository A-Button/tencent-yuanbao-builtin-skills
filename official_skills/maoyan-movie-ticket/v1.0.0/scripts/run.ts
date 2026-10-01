#!/usr/bin/env node
/**
 * 猫眼影讯查询统一入口
 *
 * 用法: node dist/run.js <command> [options]
 * 所有命令输出 JSON 到 stdout，错误输出到 stderr（也是 JSON）。
 *
 * 参数解析：--city-id 1 --keyword 万达 → { cityId: 1, keyword: '万达' }
 *   - key 转驼峰：city-id → cityId
 *   - 值为纯数字时转 number
 */

import './lib/env.js';

type Args = Record<string, string | number | boolean>;

function parseArgs(argv: string[]): Args {
  const args: Args = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) continue;
    const key = a.slice(2).replace(/-([a-z])/g, (_, c) => c.toUpperCase());
    const next = argv[i + 1];
    if (next && !next.startsWith('--')) {
      args[key] = /^\d+(\.\d+)?$/.test(next)
        ? (/^\d+$/.test(next) && BigInt(next) > BigInt(Number.MAX_SAFE_INTEGER) ? next : Number(next))
        : next;
      i++;
    } else {
      args[key] = true;
    }
  }
  return args;
}

const commands: Record<string, (args: Args) => Promise<unknown>> = {
  init:                   (a) => import('./apis/init.js').then(m => m.init(a)),
  get_city_by_name:       (a) => import('./apis/help.js').then(m => m.getCityByName(a)),
  get_location:           (a) => import('./apis/help.js').then(m => m.getLocation(a)),
  recommend_hot_movies:   (a) => import('./apis/movie.js').then(m => m.recommendHotMovies(a)),
  search_movies:          (a) => import('./apis/movie.js').then(m => m.searchMovies(a)),
  get_movie_detail:       (a) => import('./apis/movie.js').then(m => m.getMovieDetail(a)),
  get_movie_show_days:    (a) => import('./apis/movie.js').then(m => m.getMovieShowDays(a)),
  get_nearby_cinemas:     (a) => import('./apis/cinema.js').then(m => m.getNearbyCinemas(a)),
  search_cinemas:         (a) => import('./apis/cinema.js').then(m => m.searchCinemas(a)),
  get_cinema_detail:      (a) => import('./apis/cinema.js').then(m => m.getCinemaDetail(a)),
  get_cinemas_by_movie:   (a) => import('./apis/cinema.js').then(m => m.getCinemasByMovie(a)),
  get_cinema_show:        (a) => import('./apis/shows.js').then(m => m.getCinemaShow(a)),
  recommend_nearby_shows: (a) => import('./apis/shows.js').then(m => m.recommendNearbyShows(a)),
};

async function main() {
  const [cmd, ...rest] = process.argv.slice(2);
  if (!cmd || cmd === '--help' || cmd === '-h') {
    console.log('Usage: node dist/run.js <command> [options]\n');
    console.log('Commands:');
    Object.keys(commands).sort().forEach(c => console.log(`  ${c}`));
    process.exit(0);
  }

  const fn = commands[cmd];
  if (!fn) {
    console.error(JSON.stringify({
      success: false,
      error: 'UNKNOWN_COMMAND',
      command: cmd,
      available: Object.keys(commands).sort(),
    }));
    process.exit(1);
  }

  const args = parseArgs(rest);
  try {
    const result = await fn(args);
    console.log(JSON.stringify(result));
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    console.error(JSON.stringify({ success: false, message: msg }));
    process.exit(1);
  }
}

main();
