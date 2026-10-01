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
      [--deck deck.selected.json] [--images images.json] \
      [--output-dir /absolute/user/workspace]

--lines   : build content_plan.json from a TSV via plan_from_lines.py (preferred
            for long decks). When given, --plan is the OUTPUT path.
--images  : JSON array of image ops, each {"slide":N,"index":K,"image":"/path"}
            (or {"ref":"slideN:imageK","image":"/path"}). Optional.

批次工作流（性能优化，2026-07 补丁）：
  --no-finalize  : 应用本批文本/配图/版式后，只对 --scope 指定页跑轻量的
                   verify_content + check_layout 并回传反馈；**不**打包、
                   **不**跑成品减肥(optimize_template_media)/字体内嵌(embed_fonts)。
                   这两步是 finalize_run 里最贵的部分（字体内嵌单次 ~15-20s，
                   且是"每种字体固定要付一次"的开销，和改了多少文字无关）——
                   中间批次不需要一份能直接打开的成品，跳过它们不影响自查准确性，
                   只是不产出/更新 final.pptx。
  --finalize-only: 跳过应用步骤，仅跑一次完整 finalize_run（打包 + 减肥 + 字体
                   内嵌 + 四项硬关卡），写 final.pptx。
  --scope        : 逗号分隔页号（如 1,2,3），仅 --no-finalize 下用于过滤反馈到
                   本批页；同时会累计写入 RUN/.scope_history.json，让本批同时
                   复查"此前所有已处理页"，避免后续批次的改动（比如换了图）
                   让早期已过关的页悄悄回归却要等到最后收尾才发现。
  不传任一开关 = 旧的一次性行为（应用 + finalize），完全向后兼容，不影响任何
  已有调用方。

Note: only the unpacked PPTX tree is redirected to /tmp via run_paths.py.
Small persistent files (deck JSON, content_plan.json, reports, model-authored
inputs such as content_lines.tsv/images.json/layout_ops.json) stay in the
literal RUN directory. The final deliverable is written once to
run_paths.final_pptx_path(), under --output-dir when provided or
PPT_DELIVERY_ROOT otherwise.
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


def _slide_of_ref(ref) -> int | None:
    m = re.match(r'slide(\d+):', str(ref or ''))
    return int(m.group(1)) if m else None


def _touched_scope_history(run_dir: Path, scope: set[int] | None) -> set[int]:
    """累计本 run 内所有 --no-finalize 批次覆盖过的页号，并把本批 scope 并入落盘。"""
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


def _batch_qc(run_dir: Path, unpacked: Path, template: str, plan_path: Path, deck_path: Path,
               report: dict, image_results: list, applied, scope: set[int] | None) -> int:
    """批次自查：只跑 verify_content + check_layout（轻量），不打包/不减肥/不嵌字体。

    与旧版一次性行为共用同一套解析脚本（verify_content.py / check_layout.py），
    CLI 完全不变，只是这里额外传入 --deck/--plan 让 verify_content 能对上真正的
    应用计划，而不是 finalize_run 兜底生成的空计划。
    """
    preview = run_dir / '.batch_preview.pptx'
    pack = _run([sys.executable, str(SCRIPTS / 'office' / 'pack.py'),
                 str(unpacked), str(preview), '--original', template])
    report['steps'].append({'name': 'pack_preview', 'returncode': pack.returncode, 'stderr': pack.stderr[-400:]})

    verify_report = run_dir / 'verify_content.batch.json'
    vr = _run([sys.executable, str(SCRIPTS / 'verify_content.py'), str(unpacked),
               '--deck', str(deck_path), '--plan', str(plan_path), '--report', str(verify_report)])
    try:
        verify_data = json.loads(verify_report.read_text(encoding='utf-8'))
    except Exception:
        verify_data = {'issues': [{'severity': 'blocking', 'type': 'verify_parse', 'detail': vr.stderr[-300:]}]}

    layout_data = {'issues': []}
    if preview.exists():
        lr = _run([sys.executable, str(SCRIPTS / 'check_layout.py'), str(preview),
                   '--baseline-template', template, '--json'])
        try:
            layout_data = json.loads(lr.stdout)
        except Exception:
            layout_data = {'issues': [{'severity': 'blocking', 'type': 'layout_parse', 'detail': lr.stdout[:300]}]}

    cumulative_scope = _touched_scope_history(run_dir, scope)

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
    v_block = sum(1 for i in v_issues if i.get('severity') == 'blocking')
    l_block = sum(1 for i in l_issues if i.get('severity') == 'blocking')

    try:
        preview.unlink()
    except OSError:
        pass

    images_failed = [r for r in image_results if not r.get('ok')]
    ok = (v_block == 0 and l_block == 0 and not images_failed)
    print(json.dumps({
        'mode': 'no-finalize (batch, 跳过打包/减肥/字体内嵌)',
        'scope': sorted(scope) if scope else None,
        'checked_scope': sorted(cumulative_scope) if cumulative_scope else None,
        'ok': ok,
        'applied': applied,
        'images_ok': sum(1 for r in image_results if r.get('ok')),
        'images_failed': len(images_failed),
        'verify_blocking': v_block,
        'layout_blocking': l_block,
        'verify_issues': v_issues[:20],
        'layout_issues': l_issues[:20],
        'hint': ('本批及此前所有已处理页均通过，继续下一批；全部批次完成后用 --finalize-only 统一打包过硬关卡。'
                 if ok else
                 'checked_scope（本批+此前所有已处理页）内有 blocking：按上面 issues 修 content_lines/images/'
                 'layout_ops 后重跑本批 --no-finalize。'),
    }, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
    return 0 if ok else 2


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
    ap.add_argument('--output-dir',
                    help='Directory for the final <run_id>.pptx; defaults to PPT_DELIVERY_ROOT.')
    ap.add_argument('--no-finalize', action='store_true',
                    help='批次模式：应用本批后只做轻量自查反馈，不打包/不减肥/不嵌字体，不产出 final.pptx。')
    ap.add_argument('--finalize-only', action='store_true',
                    help='仅打包并跑完整 finalize（含减肥/字体内嵌/四项硬关卡），不重复应用文本/配图。')
    ap.add_argument('--scope', help='逗号分隔的页号（如 1,2,3），仅 --no-finalize 下用于过滤反馈到本批页。')
    args = ap.parse_args()

    if args.no_finalize and args.finalize_only:
        print(json.dumps({'error': '--no-finalize 和 --finalize-only 不能同时传'}, ensure_ascii=False))
        return 2

    scope: set[int] | None = None
    if args.scope:
        try:
            scope = {int(s) for s in args.scope.split(',') if s.strip()}
        except ValueError:
            print(json.dumps({'error': f'--scope 解析失败: {args.scope}'}, ensure_ascii=False))
            return 2

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    unpacked = unpacked_dir(args.run_dir)
    plan_path = run_dir / args.plan
    report: dict = {'run_dir': str(run_dir), 'steps': []}

    if not unpacked.exists():
        report['error'] = f'找不到解包目录: {unpacked}；先 unpack + select_slides + clean。'
        return _fail(report)

    image_results: list[dict] = []
    step: dict = {}

    if not args.finalize_only:
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

    if args.no_finalize:
        # 批次自查：跳过打包/减肥媒体/字体内嵌（finalize_run 里最贵的部分），
        # 只用 verify_content + check_layout 校验本批（+ 累计历史）页，快速回传。
        deck_path = run_dir / args.deck
        return _batch_qc(run_dir, unpacked, args.template, plan_path, deck_path,
                         report, image_results, step.get('report', {}).get('applied'), scope)

    # 4) Finalize (packs + verify_content + check_layout, writes final.pptx).
    # Forward the same plan so verify_content checks the real pipeline plan,
    # not an auto-created empty one (otherwise only the global stale scan runs).
    fin_cmd = [sys.executable, str(SCRIPTS / 'finalize_run.py'), str(run_dir),
               '--template', args.template, '--plan', args.plan, '--deck', args.deck]
    if args.output_dir:
        fin_cmd.extend(['--output-dir', args.output_dir])
    fin = _run(fin_cmd)
    fin_json = None
    try:
        fin_json = json.loads(fin.stdout)
    except Exception:
        pass
    report['steps'].append({'name': 'finalize_run', 'returncode': fin.returncode,
                            'stdout': fin.stdout[-1500:], 'stderr': fin.stderr[-800:]})
    final_pptx = final_pptx_path(args.run_dir, args.output_dir)
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
        'hint': ((f"交付路径：{report['final_pptx']}。" if report['ok'] else
                  'final.pptx 已生成但有 blocking：看 finalize_report.json，按预算最多修 2 轮后重跑。')
                 + img_hint),
    }, ensure_ascii=False, indent=2))
    # full report on stderr for debugging without polluting the headline
    print(json.dumps(report, ensure_ascii=False), file=sys.stderr)
    return 0 if report['ok'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
