#!/usr/bin/env python3
"""One-shot orchestrator for the PPT apply→images→finalize tail.

Collapses what used to be ~5 separate tool calls (plan_from_lines → replace_text
→ replace_image* → verify_content → check_layout → finalize_run) into a single
command. This matters for reliability: weaker models degrade after many tool
rounds, so fewer round-trips = higher chance the deck actually gets finished.

It does NOT add new PPTX logic — it sequences existing modules via in-process
``import`` (see ``orch_lib``), with per-step exception/SystemExit/stdio isolation.
Returns one consolidated JSON report. If text replacement fails, it stops early
and reports the errors so the model can fix only ``content_plan.json`` /
``content_lines.tsv`` and re-run this same command.

Usage:
  python scripts/apply_plan.py RUN --template /data/skills/pptx/templates/<path> \
      [--lines content_lines.tsv] [--plan content_plan.json] \
      [--deck deck.selected.json] [--images images.json]

--lines   : build content_plan.json from a TSV via plan_from_lines.py (preferred
            for long decks). When given, --plan is the OUTPUT path.
--images  : JSON array of image ops, each {"slide":N,"index":K,"image":"/path"}
            (or {"ref":"slideN:imageK","image":"/path"}). Optional.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import orch_lib as orch  # noqa: E402  — 进程内 import 调用各步骤，隔离异常

# 并发只用于互不依赖的 I/O；写 unpacked 的步骤仍串行，避免竞态改逻辑。
_URL_RE = re.compile(r'^https?://', re.IGNORECASE)
_PREFETCH_WORKERS = 8


def _download_one(url: str, dest_dir: Path, idx: int) -> tuple[str, Path | None]:
    """预取单张 URL 图到 dest_dir。失败返回 (url, None)，调用方回退为原 URL（与旧行为一致）。"""
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            ctype = (resp.headers.get('Content-Type') or '').lower()
    except Exception:
        return url, None
    if not data:
        return url, None
    if 'png' in ctype or data[:8] == b'\x89PNG\r\n\x1a\n':
        suffix = '.png'
    elif 'jpeg' in ctype or 'jpg' in ctype or data[:2] == b'\xff\xd8':
        suffix = '.jpg'
    elif 'webp' in ctype or (data[:4] == b'RIFF' and data[8:12] == b'WEBP'):
        suffix = '.webp'
    else:
        suffix = '.png'
    path = dest_dir / f'prefetch_{idx}{suffix}'
    try:
        path.write_bytes(data)
    except OSError:
        return url, None
    return url, path


def _prefetch_image_urls(ops: list[dict], dest_dir: Path) -> dict[str, Path]:
    """并行下载 ops 里出现的 http(s) 图；同 URL 只下一次。返回 url→本地路径。"""
    urls: list[str] = []
    seen: set[str] = set()
    for op in ops:
        img = op.get('image')
        if not img or not _URL_RE.match(str(img)):
            continue
        u = str(img)
        if u not in seen:
            seen.add(u)
            urls.append(u)
    if not urls:
        return {}
    dest_dir.mkdir(parents=True, exist_ok=True)
    mapping: dict[str, Path] = {}
    workers = min(_PREFETCH_WORKERS, len(urls))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(_download_one, u, dest_dir, i) for i, u in enumerate(urls)]
        for fut in as_completed(futs):
            url, path = fut.result()
            if path is not None:
                mapping[url] = path
    return mapping


def _fail(report: dict, code: int = 2) -> int:
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return code


def main() -> int:
    ap = argparse.ArgumentParser(description='Apply a content plan and finalize a PPT run in one shot.')
    ap.add_argument('run_dir')
    ap.add_argument('--template', required=True, help='Original template .pptx path')
    ap.add_argument('--plan', default='content_plan.json',
                    help='content_plan.json path (relative to run_dir). Built from --lines if given.')
    ap.add_argument('--lines', help='content_lines.tsv path (relative to run_dir); builds the plan.')
    ap.add_argument('--deck', default='deck.selected.json', help='deck JSON for plan_from_lines (relative to run_dir).')
    ap.add_argument('--images', help='JSON file with image ops (relative to run_dir).')
    ap.add_argument('--charts', help='JSON file with chart data ops (relative to run_dir).')
    ap.add_argument('--tables', help='JSON file with table cell ops (relative to run_dir).')
    ap.add_argument('--layout', help='JSON file with layout ops (autofit/geometry, relative to run_dir).')
    ap.add_argument('--notes', help='JSON file with speaker notes (relative to run_dir): '
                    '[{"slide":N,"note":"..."}]。收尾（--finalize-only 或一步到位）打包前写入 '
                    'notesSlide，缺 notesSlide 的页自动补建。失败只记录、不阻断交付。')
    # 批次工作流（质量优先、逐批生成）：
    #   --no-finalize  : 应用本批文本/配图/版式后，只对 --scope 指定页跑 verify_content
    #                    + check_layout，按页过滤只回传本批反馈；不打包、不跑成品减肥/字体内嵌。
    #   --finalize-only: 跳过应用步骤，仅跑 finalize_run（整副打包 + 四项硬关卡 + 写 final.pptx）。
    #   不传任一开关 = 旧的一次性行为（应用 + finalize），完全向后兼容。
    ap.add_argument('--no-finalize', action='store_true',
                    help='批次模式：应用本批后只做 scope 页自查反馈，不打包 final.pptx。')
    ap.add_argument('--finalize-only', action='store_true',
                    help='仅打包并跑硬关卡（不重复应用文本/配图）。')
    ap.add_argument('--scope', help='逗号分隔的页号（如 1,2,3），仅 --no-finalize 下用于过滤反馈到本批页。')
    args = ap.parse_args()

    if args.no_finalize and args.finalize_only:
        return _fail({'error': '--no-finalize 与 --finalize-only 互斥，只能给一个。'})

    scope: set[int] | None = None
    if args.scope:
        try:
            scope = {int(x) for x in re.split(r'[\s,]+', args.scope.strip()) if x}
        except ValueError:
            return _fail({'error': f'--scope 解析失败: {args.scope!r}（应是逗号分隔页号，如 1,2,3）'})

    run_dir = Path(args.run_dir)
    unpacked = run_dir / 'unpacked'
    plan_path = run_dir / args.plan
    report: dict = {'run_dir': str(run_dir), 'steps': []}

    if not unpacked.exists():
        report['error'] = f'找不到解包目录: {unpacked}；先 unpack + select_slides + clean。'
        return _fail(report)

    # --finalize-only：跳过应用步骤，直奔成品打包 + 硬关卡。
    if args.finalize_only:
        _apply_notes(args, run_dir, unpacked, report)
        return _finalize(args, run_dir, report, image_results=[], step={})

    # 1) Build plan from TSV lines if requested.
    if args.lines:
        lines_path = run_dir / args.lines
        deck_path = run_dir / args.deck
        if not lines_path.exists():
            report['error'] = f'找不到 lines 文件: {lines_path}'
            return _fail(report)
        if not deck_path.exists():
            report['error'] = f'找不到 deck 文件: {deck_path}（先 inspect_deck > {args.deck}）'
            return _fail(report)
        pl = orch.plan_from_lines(deck_path, lines_path)
        report['steps'].append({'name': 'plan_from_lines', 'returncode': pl.returncode, 'stderr': pl.stderr[-800:]})
        if pl.returncode != 0:
            report['error'] = 'plan_from_lines 失败；检查 content_lines.tsv 行格式。'
            return _fail(report)
        plan_path.write_text(pl.stdout, encoding='utf-8')

    if not plan_path.exists():
        report['error'] = f'找不到 content_plan: {plan_path}（给 --lines 或先生成 {args.plan}）'
        return _fail(report)

    # 2) Apply text. Stop early on errors so the model fixes only the plan.
    apply_report = run_dir / 'apply_report.json'
    rt = orch.replace_text(unpacked, plan_path, report_path=apply_report, quiet=True)
    step = {'name': 'replace_text', 'returncode': rt.returncode}
    if isinstance(rt.data, dict):
        step['report'] = rt.data
    else:
        try:
            step['report'] = json.loads(apply_report.read_text(encoding='utf-8'))
        except Exception:
            step['stderr'] = rt.stderr[-1500:]
    report['steps'].append(step)
    if rt.returncode != 0:
        report['error'] = ('文本替换有错误，已停止。只修 content_plan.json / content_lines.tsv 后重跑本命令；'
                           '不需要替换的项改 keep，要删的改 clear。')
        report['replace_stderr'] = rt.stderr[-1500:]
        return _fail(report)

    # 3) images / charts / tables：跨任务并行；任务内多 case 也并行。
    #    - 换图：同页 slide_lock 串行，不同页并行（orch.replace_images_batch）
    #    - 图表：按 chart XML path_lock，多图并行（edit_chart.apply_ops）
    #    - 表格：按页 slide_lock，多表并行（edit_table.apply_ops）
    #    三者写不同资源或已加锁，可与彼此并行。layout 仍在其后（依赖最终几何）。
    #    early-stop：并行跑完后按 charts→tables 顺序检查；任一门失败则跳过 layout/收尾。
    image_results: list[dict] = []
    prefetch_dir: Path | None = None

    def _run_images() -> tuple[list[dict], Path | None]:
        if not args.images:
            return [], None
        images_path = run_dir / args.images
        try:
            ops = json.loads(images_path.read_text(encoding='utf-8'))
        except Exception as e:
            raise RuntimeError(f'images JSON 解析失败: {e}') from e
        if not isinstance(ops, list):
            ops = []
        pf = run_dir / '.image_prefetch'
        try:
            url_map = _prefetch_image_urls(ops, pf)
        except Exception:
            url_map = {}
        jobs: list[dict] = []
        meta: list[dict] = []  # 与 jobs 对齐的原始字段，供结果回填
        local_results: list[dict] = []
        for op in ops:
            slide = op.get('slide')
            index = op.get('index')
            visual_index = op.get('visual_index')
            ref = op.get('ref')
            if ref and (slide is None or (index is None and visual_index is None)):
                m = re.match(r'slide(\d+):(image|visual)(\d+)', str(ref))
                if m:
                    slide = int(m.group(1))
                    if m.group(2) == 'visual':
                        visual_index = int(m.group(3))
                    else:
                        index = int(m.group(3))
            img = op.get('image')
            if slide is None or (index is None and visual_index is None) or not img:
                local_results.append({'op': op, 'ok': False, 'error': '缺 slide/index/image'})
                continue
            img_arg = str(url_map[str(img)]) if str(img) in url_map else str(img)
            jobs.append({
                'slide': int(slide),
                'image': img_arg,
                'index': None if visual_index is not None else index,
                'visual_index': visual_index,
            })
            meta.append({'slide': slide, 'index': index, 'visual_index': visual_index, 'image': img})
        ris = orch.replace_images_batch(unpacked, jobs) if jobs else []
        for info, ri in zip(meta, ris):
            local_results.append({
                **info,
                'ok': ri.returncode == 0,
                'msg': (ri.stdout or ri.stderr or ri.error or '').strip()[-300:],
            })
        return local_results, pf

    def _run_charts() -> orch.Result | None:
        if not args.charts:
            return None
        charts_path = run_dir / args.charts
        if not charts_path.exists():
            return orch.Result(returncode=2, error=f'找不到 charts 文件: {charts_path}')
        return orch.edit_chart(unpacked, charts_path, report_path=run_dir / 'charts_report.json')

    def _run_tables() -> orch.Result | None:
        if not args.tables:
            return None
        tables_path = run_dir / args.tables
        if not tables_path.exists():
            return orch.Result(returncode=2, error=f'找不到 tables 文件: {tables_path}')
        return orch.edit_table(unpacked, tables_path, report_path=run_dir / 'tables_report.json')

    parallel_jobs: list[tuple[str, object]] = []
    if args.images:
        parallel_jobs.append(('images', _run_images))
    if args.charts:
        parallel_jobs.append(('charts', _run_charts))
    if args.tables:
        parallel_jobs.append(('tables', _run_tables))

    parallel_out: dict[str, object] = {}
    if len(parallel_jobs) == 1:
        name, fn = parallel_jobs[0]
        try:
            parallel_out[name] = fn()
        except Exception as e:
            if name == 'images':
                report['error'] = f'images JSON 解析失败: {e}'
                return _fail(report)
            parallel_out[name] = orch.Result(returncode=1, error=f'{type(e).__name__}: {e}')
    elif parallel_jobs:
        with ThreadPoolExecutor(max_workers=len(parallel_jobs)) as pool:
            futs = {pool.submit(fn): name for name, fn in parallel_jobs}
            for fut in as_completed(futs):
                name = futs[fut]
                try:
                    parallel_out[name] = fut.result()
                except Exception as e:
                    if name == 'images':
                        report['error'] = str(e) if str(e).startswith('images JSON') else f'images JSON 解析失败: {e}'
                        for other in futs:
                            if other is not fut:
                                try:
                                    other.result()
                                except Exception:
                                    pass
                        return _fail(report)
                    parallel_out[name] = orch.Result(returncode=1, error=f'{type(e).__name__}: {e}')

    if 'images' in parallel_out:
        image_results, prefetch_dir = parallel_out['images']  # type: ignore[misc]
        report['image_results'] = image_results
        if prefetch_dir is not None:
            try:
                shutil.rmtree(prefetch_dir)
            except OSError:
                pass

    if args.charts:
        ec = parallel_out.get('charts')
        if not isinstance(ec, orch.Result):
            ec = orch.Result(returncode=1, error='charts 未执行')
        if ec.error and ec.returncode != 0 and not ec.data and '找不到 charts' in (ec.error or ''):
            report['error'] = ec.error
            return _fail(report)
        ec_step = {'name': 'edit_chart', 'returncode': ec.returncode}
        if isinstance(ec.data, dict):
            ec_step['report'] = ec.data
        else:
            try:
                ec_step['report'] = json.loads((run_dir / 'charts_report.json').read_text(encoding='utf-8'))
            except Exception:
                ec_step['stderr'] = (ec.stderr or ec.error or '')[-800:]
        report['steps'].append(ec_step)
        if ec.returncode != 0:
            report['error'] = ('图表数据改写有错误，已停止。只修 charts.json 后重跑本命令；'
                               'ref 用 deck.selected.json 里的 slideN:chartK，点数与类目数对齐。')
            return _fail(report)

    if args.tables:
        et = parallel_out.get('tables')
        if not isinstance(et, orch.Result):
            et = orch.Result(returncode=1, error='tables 未执行')
        if et.error and et.returncode != 0 and not et.data and '找不到 tables' in (et.error or ''):
            report['error'] = et.error
            return _fail(report)
        et_step = {'name': 'edit_table', 'returncode': et.returncode}
        if isinstance(et.data, dict):
            et_step['report'] = et.data
        else:
            try:
                et_step['report'] = json.loads((run_dir / 'tables_report.json').read_text(encoding='utf-8'))
            except Exception:
                et_step['stderr'] = (et.stderr or et.error or '')[-800:]
        report['steps'].append(et_step)
        if et.returncode != 0:
            report['error'] = ('表格内容改写有错误，已停止。只修 tables.json 后重跑本命令；'
                               'ref 用 deck.selected.json 里的 slideN:tableK，cells 二维数组对应行列。')
            return _fail(report)

    # 3.5) Optional layout adjustments (autofit / geometry) before finalize.
    # 不阻断主流程：版式微调失败只记录、继续打包交付（几何报警绝不挡生成）。
    # layout 必须在 images/charts/tables 之后（依赖最终内容几何）。
    if args.layout:
        layout_path = run_dir / args.layout
        if not layout_path.exists():
            report['error'] = f'找不到 layout 文件: {layout_path}'
            return _fail(report)
        la = orch.adjust_shape(unpacked, layout_path, report_path=run_dir / 'layout_ops_report.json')
        la_step = {'name': 'adjust_shape', 'returncode': la.returncode}
        if isinstance(la.data, dict):
            la_step['report'] = la.data
        else:
            try:
                la_step['report'] = json.loads((run_dir / 'layout_ops_report.json').read_text(encoding='utf-8'))
            except Exception:
                la_step['stderr'] = la.stderr[-800:]
        report['steps'].append(la_step)

    # --no-finalize：批次模式——只对 scope 页自查并回传本批反馈，不打包成品。
    if args.no_finalize:
        # 快速兜底：--scope 必须是物理 slide 编号（跟 content_lines.tsv 里 slideN:shapeM
        # 的 N 一致），不是 inspect_deck.py 里的 order（选页顺序号）。这两套编号在有
        # 分节页/重复页时会不一致，模型偶尔会把 order 当成 scope 传进来，导致本批过
        # 滤全落空（悄悄把不该跳过的问题当成"本批已过"）。在跑代价较高的
        # pack+verify+layout 之前，先用本批 plan 里的真实 ref 校验一次，不一致就快速
        # 报错并把两套编号都列出来，让模型一轮内就能自己对上，不必事后排查。
        if scope:
            try:
                plan_doc = json.loads(plan_path.read_text(encoding='utf-8'))
            except Exception:
                plan_doc = {}
            touched = {s.get('slide') for s in plan_doc.get('slides', []) if isinstance(s, dict)}
            touched.discard(None)
            if touched and not (touched & scope):
                deck_slides = _load_deck_slides(run_dir, args.deck)
                scope_map = _scope_map_text(deck_slides)
                report['error'] = (
                    f'--scope {sorted(scope)} 与本批实际改动的物理 slide 编号 {sorted(touched)} '
                    '完全不重合，像是把 inspect_deck.py 的 order（选页顺序号）当成了 --scope（要用'
                    ' content_lines.tsv 里 slideN:shapeM 的物理 slide 编号）。'
                    f' 本批 --scope 应改成 {sorted(touched)}。'
                    + (f' 整副 order→slide 对照：{scope_map}。' if scope_map else '')
                )
                return _fail(report)
        return _batch_qc(args, run_dir, unpacked, report, image_results, step, scope)

    # 3.6) Optional speaker notes（收尾一步：内容定稿后逐页写演讲备注，打包前注入）。
    _apply_notes(args, run_dir, unpacked, report)

    # 4) Finalize (packs + verify_content + check_layout, writes final.pptx).
    return _finalize(args, run_dir, report, image_results, step)


def _apply_notes(args, run_dir: Path, unpacked: Path, report: dict) -> None:
    """把演讲备注写入解包树（打包前）。这是增强项：失败只记录、绝不阻断交付。"""
    if not args.notes:
        return
    notes_path = run_dir / args.notes
    if not notes_path.exists():
        report['steps'].append({'name': 'set_notes', 'skipped': f'找不到 notes 文件: {notes_path}'})
        return
    nr = orch.set_notes(unpacked, notes_path, report_path=run_dir / 'notes_report.json', quiet=True)
    step = {'name': 'set_notes', 'returncode': nr.returncode}
    try:
        if isinstance(nr.data, dict) and 'summary' in nr.data:
            step['report'] = nr.data.get('summary')
        else:
            step['report'] = json.loads((run_dir / 'notes_report.json').read_text(encoding='utf-8')).get('summary')
    except Exception:
        step['stderr'] = nr.stderr[-400:]
    report['steps'].append(step)


def _finalize(args, run_dir: Path, report: dict, image_results: list[dict], step: dict) -> int:
    """整副打包 + 四项硬关卡校验 + 写 final.pptx（一次性模式与 --finalize-only 共用）。"""
    # Forward the same plan so verify_content checks the real pipeline plan,
    # not an auto-created empty one (otherwise only the global stale scan runs).
    import finalize_run as fin_mod
    try:
        fin_code, fin_json = fin_mod.run(
            run_dir, template=args.template, plan=args.plan, deck=args.deck, emit=False,
        )
    except BaseException as exc:  # noqa: BLE001 — finalize 失败不得拖垮编排 headline
        if isinstance(exc, (KeyboardInterrupt, GeneratorExit)):
            raise
        fin_code, fin_json = 1, {'ok': False, 'error': f'{type(exc).__name__}: {exc}'}
    # emit=False 时 run 返回 headline dict；与旧 stdout JSON 对齐
    report['steps'].append({'name': 'finalize_run', 'returncode': fin_code,
                            'stdout': json.dumps(fin_json or {}, ensure_ascii=False)[-1500:],
                            'stderr': (fin_json or {}).get('error', '')})
    final_pptx = run_dir / 'final.pptx'
    report['final_pptx'] = str(final_pptx) if final_pptx.exists() else None
    report['ok'] = bool(fin_json and fin_json.get('ok'))
    report['finalize'] = fin_json or {}

    # 图片插入失败不再静默：可能是 ref 错，也可能是背景/大图/icon 保护策略主动拒绝。
    images_failed = [r for r in image_results if not r.get('ok')]
    img_hint = ''
    if images_failed:
        brief = '; '.join(
            f"slide{r.get('slide')}:{'visual' if r.get('visual_index') else 'image'}"
            f"{r.get('visual_index') or r.get('index')}→{(r.get('error') or r.get('msg') or '').strip()[:80]}"
            for r in images_failed)
        img_hint = (f' 有 {len(images_failed)} 张配图插入失败：{brief}。'
                    '先按错误原文处理：若提示背景/大面积主视觉或图标/装饰保护位，直接从 '
                    'images.json 删除该 ref；否则核对 deck.selected.json 里的重排后 ref。')

    # 大 deck 一步到位但 blocking 一大片：这是"该分批却没分批"的强信号——一次性把几十页
    # 塞进单次 finalize，问题会攒到最后才爆发，且事后用一个巨大 layout_ops/content_lines
    # 硬修的返工成本远高于当批解决。step 非空代表这是"一步到位"调用（而非 --finalize-only
    # 复检），此时才提醒，避免在纯复检场景重复刷屏。
    batch_hint = ''
    if step and not report['ok']:
        gate_counts = [
            (fin_json or {}).get(k) for k in (
                'verify_blocking', 'layout_blocking', 'validate_blocking',
                'image_blocking', 'chart_blocking', 'table_blocking',
                'content_semantic_blocking',
            )
        ]  # contrast_blocking 不计入：对比度现为 advisory，不阻断交付
        total_blocking = sum(c for c in gate_counts if isinstance(c, int))
        page_count = None
        try:
            deck_data = json.loads((run_dir / args.deck).read_text(encoding='utf-8'))
            page_count = len(deck_data.get('slide_order') or deck_data.get('slides') or [])
        except Exception:
            pass
        if total_blocking >= 10 and (page_count is None or page_count > 6):
            batch_hint = (
                f' ⚠️ 一次性 blocking 达 {total_blocking} 条（deck 约 {page_count or "?"} 页）：'
                '说明本该走「分批循环」却用了一步到位。不要用一个巨大的 layout_ops.json/'
                'content_lines.tsv 硬啃全部问题——按页号拆成几组（每组约 3~5 页），'
                '对每组用 `--no-finalize --scope <这几页>` 单独自查修复、确认该组 ok:true '
                '后再处理下一组，最后再 --finalize-only 收尾。')

    # Surface the headline so the model doesn't need to open more files.
    print(json.dumps({
        'ok': report['ok'],
        'final_pptx': report['final_pptx'],
        'verify_blocking': (fin_json or {}).get('verify_blocking'),
        'layout_blocking': (fin_json or {}).get('layout_blocking'),
        'validate_blocking': (fin_json or {}).get('validate_blocking'),
        'image_blocking': (fin_json or {}).get('image_blocking'),
        'chart_blocking': (fin_json or {}).get('chart_blocking'),
        'table_blocking': (fin_json or {}).get('table_blocking'),
        'contrast_advisory': (fin_json or {}).get('contrast_advisory'),  # 不计入 ok，仅供参考
        'content_semantic_blocking': (fin_json or {}).get('content_semantic_blocking'),
        'structure_advisory': (fin_json or {}).get('structure_advisory'),
        'applied': step.get('report', {}).get('applied'),
        'images_ok': sum(1 for r in image_results if r.get('ok')),
        'images_failed': len(images_failed),
        'cleanup': (fin_json or {}).get('cleanup'),
        'hint': (('交付 final.pptx。' if report['ok'] else
                  'final.pptx 已生成但有 blocking：看 finalize_report.json，按预算最多修 2 轮后重跑。')
                 + img_hint + batch_hint),
    }, ensure_ascii=False, indent=2))
    # full report on stderr for debugging without polluting the headline
    print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
    return 0 if report['ok'] else 2


def _slide_of_ref(ref) -> int | None:
    m = re.match(r'slide(\d+):', str(ref or ''))
    return int(m.group(1)) if m else None


def _load_deck_slides(run_dir: Path, deck_rel: str) -> list[dict]:
    try:
        return json.loads((run_dir / deck_rel).read_text(encoding='utf-8')).get('slides', [])
    except Exception:
        return []


def _scope_map_text(slides: list[dict]) -> str:
    pairs = [f"order{s['order']}→slide{s['slide']}" for s in slides
             if s.get('order') is not None and s.get('slide') is not None]
    return ', '.join(pairs)


def _next_batch_hint(slides: list[dict], done: set[int] | None, batch_size: int = 3) -> str | None:
    physical = [s['slide'] for s in slides if s.get('slide') is not None]
    remaining = [p for p in physical if not done or p not in done]
    if not remaining:
        return '全部页已在 checked_scope 内覆盖，下一步 --finalize-only 打包交付。'
    chunk = remaining[:batch_size]
    rest = remaining[batch_size:]
    hint = f'下一批建议 --scope {",".join(str(x) for x in chunk)}'
    if rest:
        hint += f'（其后还有 {len(rest)} 页：{",".join(str(x) for x in rest[:9])}'
        if len(rest) > 9:
            hint += ',...'
        hint += '）'
    return hint


def _touched_scope_history(run_dir: Path, scope: set[int] | None) -> set[int]:
    """累计本 run 内所有 --no-finalize 批次覆盖过的页号，并把本批 scope 并入落盘。

    跨批次（如后面批次生成的配图/主题级改动）可能让*已经过关*的页重新出现对比度/
    布局问题，但之前只按当前批 scope 过滤自查反馈，这类回归要等到 --finalize-only
    才暴露——那时轮次预算所剩无几。改成"已处理过的页都持续复检"，让回归在预算还
    充裕时就被发现，而不是在收尾时才集中爆发。
    """
    hist_path = run_dir / '.scope_history.json'
    try:
        history = set(json.loads(hist_path.read_text(encoding='utf-8')))
    except Exception:
        history = set()
    if scope:
        history |= scope
        try:
            hist_path.write_text(json.dumps(sorted(history)), encoding='utf-8')
        except OSError:
            pass
    return history


def _batch_qc(args, run_dir: Path, unpacked: Path, report: dict,
              image_results: list[dict], step: dict, scope: set[int] | None) -> int:
    """批次自查：对已处理过的所有页（本批 + 历史累计）跑 verify_content + check_layout。

    跳过成品减肥/字体内嵌，仅打一个临时预览包供 check_layout 解析几何，保持批次轻快。
    未填充的其它页因 deck 带 orig_sha 会被 verify 判 untouched_template_text(blocking)，
    通过累计 scope 过滤排除，避免误把"还没轮到的页"当成本批失败；同时因为累计 scope
    包含此前所有已完成批次的页，能顺带发现后续批次对早期页造成的回归。
    """
    preview = run_dir / '.batch_preview.pptx'
    pack = orch.pack_pptx(unpacked, preview, original=args.template)
    report['steps'].append({'name': 'pack_preview', 'returncode': pack.returncode, 'stderr': pack.stderr[-400:]})

    deck_path = run_dir / args.deck
    plan_path = run_dir / args.plan
    cumulative_scope = _touched_scope_history(run_dir, scope)
    verify_report = run_dir / 'verify_content.batch.json'

    # pack 之后的检查互不依赖（只读 unpacked / preview），并行跑以压缩批次墙钟；
    # 汇总过滤逻辑与原先完全一致。每步经 orch.safe_call 隔离，互不影响。
    named: list[tuple[str, object]] = [
        ('verify_content', lambda: orch.verify_content(
            unpacked, deck_path, plan_path, report_path=verify_report, scope=cumulative_scope)),
    ]
    if preview.exists():
        named.extend([
            ('check_layout', lambda: orch.check_layout(preview, baseline_template=args.template)),
            ('check_images', lambda: orch.check_images(preview, args.template)),
            ('check_contrast', lambda: orch.check_contrast(preview, baseline_template=args.template)),
        ])
    procs = orch.run_parallel(named)

    vr = procs.get('verify_content')
    try:
        verify_data = (vr.data if vr and isinstance(vr.data, dict)
                       else json.loads(verify_report.read_text(encoding='utf-8')))
    except Exception:
        err = (vr.stderr[-300:] if vr else 'verify_content missing')
        verify_data = {'issues': [{'severity': 'blocking', 'type': 'verify_parse', 'detail': err}]}

    layout_data = {'issues': []}
    contrast_data = {'issues': []}
    images_data = {'issues': []}
    if preview.exists():
        lr = procs.get('check_layout')
        try:
            layout_data = lr.data if lr and isinstance(lr.data, dict) else json.loads(lr.stdout) if lr else {'issues': []}
        except Exception:
            layout_data = {'issues': [{'severity': 'blocking', 'type': 'layout_parse',
                                       'detail': (lr.stdout[:300] if lr else '')}]}
        # 只跑 replaced_protected_backdrop 这类"保护性背景被换"检查，本批就能发现，不必
        # 等到 --finalize-only 才暴露——早发现早撤回，省一轮"改完才发现要回滚"的浪费。
        ir = procs.get('check_images')
        try:
            images_data = ir.data if ir and isinstance(ir.data, dict) else (
                json.loads(ir.stdout) if ir and ir.stdout else {'issues': []})
        except Exception:
            images_data = {'issues': []}
        cr = procs.get('check_contrast')
        try:
            contrast_data = cr.data if cr and isinstance(cr.data, dict) else (
                json.loads(cr.stdout) if cr and cr.stdout else {'issues': []})
        except Exception:
            contrast_data = {'issues': []}

    def _in_scope_ref(issue: dict) -> bool:
        if not cumulative_scope:
            return True
        s = _slide_of_ref(issue.get('ref'))
        return s is None or s in cumulative_scope

    def _in_scope_slide(issue: dict) -> bool:
        if not cumulative_scope:
            return True
        s = issue.get('slide')
        return s is None or s in cumulative_scope

    v_issues = [i for i in verify_data.get('issues', []) if _in_scope_ref(i)]
    l_issues = [i for i in layout_data.get('issues', []) if _in_scope_slide(i)]
    # 批次阶段只拦“禁止替换却被换”的两类策略错误；untouched_template_image 等
    # “还没配图”的提醒本批可能还没轮到，留给 --finalize-only 统一查，避免误伤。
    img_issues = [i for i in images_data.get('issues', []) if _in_scope_ref(i)
                  and i.get('type') in {
                      'replaced_protected_backdrop', 'replaced_protected_small_visual',
                  }]
    # 对比度仅作参考（advisory），不计入 ok：多数低对比来自"给文字当背景的图"，
    # check_images.py 已默认硬性禁止换这类背景图（replaced_protected_backdrop
    # blocking），模型保留模板背景即天然安全；不再让对比度报告拖着模型来回改
    # 字色/重生图，消耗轮次预算。
    c_issues = [i for i in contrast_data.get('issues', []) if _in_scope_slide(i)]
    v_block = sum(1 for i in v_issues if i.get('severity') == 'blocking')
    l_block = sum(1 for i in l_issues if i.get('severity') == 'blocking')
    img_block = sum(1 for i in img_issues if i.get('severity') == 'blocking')

    # 预览包用完即删，避免被误当成品交付。
    try:
        preview.unlink()
    except OSError:
        pass

    images_failed = [r for r in image_results if not r.get('ok')]
    ok = (v_block == 0 and l_block == 0 and img_block == 0 and not images_failed)
    deck_slides = _load_deck_slides(run_dir, args.deck)
    next_batch = _next_batch_hint(deck_slides, cumulative_scope) if ok else None
    headline = {
        'mode': 'no-finalize (batch)',
        'scope': sorted(scope) if scope else None,
        'checked_scope': sorted(cumulative_scope) if cumulative_scope else None,
        'ok': ok,
        'applied': step.get('report', {}).get('applied'),
        'images_ok': sum(1 for r in image_results if r.get('ok')),
        'images_failed': len(images_failed),
        'verify_blocking': v_block,
        'layout_blocking': l_block,
        'image_policy_blocking': img_block,
        'protected_backdrop_blocking': img_block,
        'verify_issues': v_issues[:20],
        'layout_issues': l_issues[:20],
        'image_policy_issues': img_issues[:10],
        'protected_backdrop_issues': img_issues[:10],
        'contrast_issues_advisory': c_issues[:10],
        'hint': ('本批及此前所有已处理页均通过，继续下一批；全部批次完成后用 --finalize-only 统一打包过硬关卡。'
                 + (f' {next_batch}' if next_batch else '')
                 if ok else
                 'checked_scope（本批+此前所有已处理页）内有 blocking：注意部分 issue 可能来自更早的批次'
                 '（比如后面批次的配图/主题改动影响了早期页），按上面 issues 修 content_lines/images/'
                 'charts/tables/layout_ops 后重跑本批 --no-finalize。'
                 'image_policy_issues 非空说明背景/大图或 icon/装饰小图被误换——'
                 '把对应 ref 从 images.json 里删掉并 restore，禁止再生成替换它。'
                 '（contrast_issues_advisory 仅供参考，不阻断，不必为它单独返工）'),
    }
    if ok and next_batch:
        headline['next_batch'] = next_batch
    print(json.dumps(headline, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
