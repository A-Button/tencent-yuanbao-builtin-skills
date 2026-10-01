#!/usr/bin/env python3
"""One-shot orchestrator for the PPT apply→images→finalize tail.

Collapses what used to be ~5 separate tool calls (plan_from_lines → replace_text
→ replace_image* → verify_content → check_layout → finalize_run) into a single
command. This matters for reliability: weaker models degrade after many tool
rounds, so fewer round-trips = higher chance the deck actually gets finished.

It does NOT add new PPTX logic — it just sequences the existing scripts and
returns one consolidated JSON report. If text replacement fails, it stops early
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

Note: only the unpacked PPTX tree is redirected to /tmp via run_paths.py.
Small persistent files (deck JSON, content_plan.json, reports, model-authored
inputs such as content_lines.tsv/images.json/layout_ops.json) stay in the
literal RUN directory under /data/workspace. The final deliverable is written
once to run_paths.final_pptx_path(), a flat file directly under
/data/workspace.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from run_paths import final_pptx_path, unpacked_dir  # noqa: E402


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


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
    ap.add_argument('--layout', help='JSON file with layout ops (autofit/geometry, relative to run_dir).')
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    unpacked = unpacked_dir(args.run_dir)
    plan_path = run_dir / args.plan
    report: dict = {'run_dir': str(run_dir), 'steps': []}

    if not unpacked.exists():
        report['error'] = f'找不到解包目录: {unpacked}；先 unpack + select_slides + clean。'
        return _fail(report)

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
        pl = _run([sys.executable, str(SCRIPTS / 'plan_from_lines.py'), str(deck_path), str(lines_path)])
        report['steps'].append({'name': 'plan_from_lines', 'returncode': pl.returncode, 'stderr': pl.stderr[-800:]})
        if pl.returncode != 0:
            report['error'] = 'plan_from_lines 失败；检查 content_lines.tsv 行格式。'
            return _fail(report)
        plan_path.write_text(pl.stdout, encoding='utf-8')

    if not plan_path.exists():
        report['error'] = f'找不到 content_plan: {plan_path}（给 --lines 或先在 RUN 下生成 {args.plan}）'
        return _fail(report)

    # 2) Apply text. Stop early on errors so the model fixes only the plan.
    apply_report = run_dir / 'apply_report.json'
    rt = _run([sys.executable, str(SCRIPTS / 'replace_text.py'), str(unpacked), str(plan_path),
               '--report', str(apply_report), '-q'])
    step = {'name': 'replace_text', 'returncode': rt.returncode}
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

    # 3) Optional images.
    image_results: list[dict] = []
    if args.images:
        images_path = run_dir / args.images
        try:
            ops = json.loads(images_path.read_text(encoding='utf-8'))
        except Exception as e:
            report['error'] = f'images JSON 解析失败: {e}'
            return _fail(report)
        for op in ops if isinstance(ops, list) else []:
            slide = op.get('slide')
            index = op.get('index')
            ref = op.get('ref')
            if ref and (slide is None or index is None):
                m = re.match(r'slide(\d+):image(\d+)', str(ref))
                if m:
                    slide, index = int(m.group(1)), int(m.group(2))
            img = op.get('image')
            if slide is None or index is None or not img:
                image_results.append({'op': op, 'ok': False, 'error': '缺 slide/index/image'})
                continue
            ri = _run([sys.executable, str(SCRIPTS / 'replace_image.py'), 'set', str(unpacked),
                       '--slide', str(slide), '--index', str(index), '--image', str(img)])
            image_results.append({'slide': slide, 'index': index, 'image': img,
                                  'ok': ri.returncode == 0,
                                  'msg': (ri.stdout or ri.stderr).strip()[-300:]})
        report['image_results'] = image_results

    # 3.5) Optional layout adjustments (autofit / geometry) before finalize.
    # 不阻断主流程：版式微调失败只记录、继续打包交付（几何报警绝不挡生成）。
    if args.layout:
        layout_path = run_dir / args.layout
        if not layout_path.exists():
            report['error'] = f'找不到 layout 文件: {layout_path}'
            return _fail(report)
        la = _run([sys.executable, str(SCRIPTS / 'adjust_shape.py'), str(unpacked), str(layout_path),
                   '--report', str(run_dir / 'layout_ops_report.json')])
        la_step = {'name': 'adjust_shape', 'returncode': la.returncode}
        try:
            la_step['report'] = json.loads((run_dir / 'layout_ops_report.json').read_text(encoding='utf-8'))
        except Exception:
            la_step['stderr'] = la.stderr[-800:]
        report['steps'].append(la_step)

    # 4) Finalize (packs + verify_content + check_layout, writes final.pptx).
    # Forward the same plan so verify_content checks the real pipeline plan,
    # not an auto-created empty one (otherwise only the global stale scan runs).
    fin = _run([sys.executable, str(SCRIPTS / 'finalize_run.py'), str(run_dir),
                '--template', args.template, '--plan', args.plan, '--deck', args.deck])
    fin_json = None
    try:
        fin_json = json.loads(fin.stdout)
    except Exception:
        pass
    report['steps'].append({'name': 'finalize_run', 'returncode': fin.returncode,
                            'stdout': fin.stdout[-1500:], 'stderr': fin.stderr[-800:]})
    final_pptx = final_pptx_path(args.run_dir)
    report['final_pptx'] = str(final_pptx) if final_pptx.exists() else None
    report['ok'] = bool(fin_json and fin_json.get('ok'))
    report['finalize'] = fin_json or {}

    # 图片插入失败不再静默：单列出来并给可操作提示（八成是页号用错——要用
    # deck.selected.json 里重排后的 slideN:imageK，而不是原模板页号）。
    images_failed = [r for r in image_results if not r.get('ok')]
    img_hint = ''
    if images_failed:
        brief = '; '.join(
            f"slide{r.get('slide')}:image{r.get('index')}→{(r.get('error') or r.get('msg') or '').strip()[:80]}"
            for r in images_failed)
        img_hint = (f' 有 {len(images_failed)} 张配图插入失败：{brief}。'
                    '请改用 deck.selected.json 里重排后的 ref(slideN:imageK)，'
                    '页号是选页后的新编号、不是原模板页号；index 是该页第几个图位。')

    # Surface the headline so the model doesn't need to open more files.
    print(json.dumps({
        'ok': report['ok'],
        'final_pptx': report['final_pptx'],
        'verify_blocking': (fin_json or {}).get('verify_blocking'),
        'layout_blocking': (fin_json or {}).get('layout_blocking'),
        'validate_blocking': (fin_json or {}).get('validate_blocking'),
        'image_blocking': (fin_json or {}).get('image_blocking'),
        'applied': step.get('report', {}).get('applied'),
        'images_ok': sum(1 for r in image_results if r.get('ok')),
        'images_failed': len(images_failed),
        'hint': (('交付 final.pptx。' if report['ok'] else
                  'final.pptx 已生成但有 blocking：看 finalize_report.json，按预算最多修 2 轮后重跑。')
                 + img_hint),
    }, ensure_ascii=False, indent=2))
    # full report on stderr for debugging without polluting the headline
    print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
