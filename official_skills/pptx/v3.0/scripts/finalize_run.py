#!/usr/bin/env python3
"""Finalize a PPT run directory with one command.

This script is the final gate for the PPT skill:
  1. pack RUN/unpacked to RUN/final.pptx
  2. verify content has no blocking stale-template issues
  3. verify layout has no blocking issues
  4. write RUN/finalize_report.json

It intentionally tolerates content warnings, because many final decks contain
long user-written text that did not come from the latest small repair plan.

编排通过 orch_lib 进程内 import 调用各检查模块；每步异常隔离，互不影响。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import orch_lib as orch  # noqa: E402


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _read_semantic_report(run_dir: Path) -> dict:
    path = run_dir / 'content_semantic.json'
    if not path.exists():
        return {
            'available': False,
            'blocking_count': 0,
            'warning_count': 1,
            'issues': [{
                'severity': 'warning',
                'type': 'semantic_check_missing',
                'detail': 'content_semantic.json not found; model semantic delivery review was not recorded.',
            }],
        }
    try:
        data = _read_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            'available': True,
            'blocking_count': 1,
            'warning_count': 0,
            'issues': [{
                'severity': 'blocking',
                'type': 'semantic_check_invalid',
                'detail': f'{type(exc).__name__}: {exc}',
            }],
        }
    issues = data.get('issues', []) if isinstance(data.get('issues', []), list) else []
    blocking = sum(1 for item in issues if item.get('severity') == 'blocking')
    warning = sum(1 for item in issues if item.get('severity') == 'warning')
    data['available'] = True
    data['blocking_count'] = blocking
    data['warning_count'] = warning
    return data


def _gate_data(res: orch.Result, report_path: Path | None = None,
               default_blocking: int = 0) -> dict:
    if isinstance(res.data, dict):
        return res.data
    if report_path and report_path.exists():
        try:
            return _read_json(report_path)
        except Exception:
            pass
    if res.stdout:
        try:
            return json.loads(res.stdout)
        except json.JSONDecodeError:
            pass
    return {'blocking_count': default_blocking, 'issues': []}


_SLIM_CACHE_DIR = Path(tempfile.gettempdir()) / 'pptx_media_slim_cache'
_SLIM_EDGE = 1600
_SLIM_QUALITY = 80


def _slim_cache_file(template: Path, max_edge: int, quality: int) -> Path:
    st = template.stat()
    # 不含 path：copytree 克隆的同内容模板可命中同一缓存。
    key = f'{st.st_size}|{st.st_mtime_ns}|{max_edge}|{quality}'
    digest = hashlib.sha256(key.encode('utf-8')).hexdigest()[:24]
    return _SLIM_CACHE_DIR / f'{digest}.pptx'


def _copy_cached_or_slim_template(template: Path, dest: Path, *,
                                  max_edge: int, quality: int) -> orch.Result:
    """check_images 基线：按模板身份缓存 slim 结果，避免每次 finalize 重压同一模板。"""
    cache = _slim_cache_file(template, max_edge, quality)
    try:
        if cache.is_file() and cache.stat().st_size > 0:
            shutil.copyfile(cache, dest)
            return orch.Result(returncode=0, stdout=f'cached slim template {cache.name}')
    except OSError:
        pass
    try:
        shutil.copyfile(template, dest)
    except Exception as exc:
        return orch.Result(returncode=1, stderr=str(exc), error=str(exc))
    res = orch.optimize_media_inplace(dest, max_edge=max_edge, quality=quality)
    if res.returncode == 0:
        try:
            _SLIM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            tmp = cache.with_suffix('.tmp.pptx')
            shutil.copyfile(dest, tmp)
            tmp.replace(cache)
        except OSError:
            pass
    return res


def run(run_dir: Path | str, *, template: str, deck: str = 'deck.selected.json',
        plan: str = 'content_plan.json', emit: bool = True) -> tuple[int, dict]:
    """执行 finalize。返回 (exit_code, headline_dict)。emit=True 时打印 headline JSON。"""
    run_dir = Path(run_dir)
    unpacked = run_dir / 'unpacked'
    final_pptx = run_dir / 'final.pptx'
    deck_json = run_dir / deck
    plan_json = run_dir / plan
    report_json = run_dir / 'finalize_report.json'

    if not unpacked.exists():
        msg = f'找不到解包目录: {unpacked}'
        if emit:
            print(msg, file=sys.stderr)
        return 1, {'ok': False, 'error': msg}
    if not deck_json.exists():
        msg = f'找不到 deck 文件: {deck_json}'
        if emit:
            print(msg, file=sys.stderr)
        return 1, {'ok': False, 'error': msg}

    # A final gate plan only exists to let verify_content scan stale text and
    # verify explicit late repairs. It is safe to be empty.
    if not plan_json.exists():
        plan_json.write_text(json.dumps({'version': 1, 'slides': []}, ensure_ascii=False, indent=2), encoding='utf-8')

    steps: list[dict] = []

    pack = orch.pack_pptx(unpacked, final_pptx, original=template)
    steps.append({'name': 'pack', 'returncode': pack.returncode,
                  'stdout': pack.stdout, 'stderr': pack.stderr})
    if pack.returncode != 0:
        report_json.write_text(json.dumps({'ok': False, 'steps': steps}, ensure_ascii=False, indent=2), encoding='utf-8')
        if emit:
            print(pack.stderr or pack.stdout, file=sys.stderr)
        return 2, {'ok': False, 'steps': steps}

    size_before = final_pptx.stat().st_size if final_pptx.exists() else 0

    # 先瘦身再 normalize：normalize 会整包重写 zip，fat 包上白压媒体更贵。
    # 成品减肥与 check_images 基线减肥写不同文件，可并行；embed_fonts 必须等成品减肥+归一化完成。
    optimized_image_template = run_dir / '.check_images_template.pptx'

    def _slim_final() -> orch.Result:
        return orch.optimize_media_inplace(final_pptx, max_edge=_SLIM_EDGE, quality=_SLIM_QUALITY)

    def _slim_baseline() -> orch.Result:
        return _copy_cached_or_slim_template(
            Path(template), optimized_image_template,
            max_edge=_SLIM_EDGE, quality=_SLIM_QUALITY)

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_final = pool.submit(_slim_final)
        fut_base = pool.submit(_slim_baseline)
        slim = fut_final.result()
        opt_tpl = fut_base.result()

    steps.append({'name': 'optimize_media', 'returncode': slim.returncode,
                  'stdout': (slim.stdout or '')[-400:], 'stderr': (slim.stderr or '')[-400:]})

    image_template = Path(template)
    steps.append({'name': 'optimize_image_baseline', 'returncode': opt_tpl.returncode,
                  'stdout': (opt_tpl.stdout or '')[-400:], 'stderr': (opt_tpl.stderr or opt_tpl.error or '')[-400:]})
    if opt_tpl.returncode == 0:
        image_template = optimized_image_template

    ns = orch.normalize_ooxml(final_pptx)
    if ns.returncode == 0:
        steps.append({'name': 'normalize_ns', 'returncode': 0, 'stdout': (ns.stdout or '')[:500]})
    else:
        steps.append({'name': 'normalize_ns', 'returncode': ns.returncode,
                      'stderr': ns.stderr or ns.error or ''})

    fonts = orch.embed_fonts_inplace(final_pptx)
    steps.append({'name': 'embed_fonts', 'returncode': fonts.returncode,
                  'stdout': (fonts.stdout or '')[-400:], 'stderr': (fonts.stderr or '')[-400:]})

    size_after = final_pptx.stat().st_size if final_pptx.exists() else 0
    content_semantic_data = _read_semantic_report(run_dir)

    verify_report = run_dir / 'verify_content.finalize.json'
    layout_report = run_dir / 'layout_report.json'
    validate_report = run_dir / 'validate_report.json'
    images_report = run_dir / 'images_report.json'
    contrast_report = run_dir / 'contrast_report.json'
    charts_report = run_dir / 'charts_report.gate.json'
    tables_report = run_dir / 'tables_report.gate.json'
    structure_report = run_dir / 'structure_report.json'

    # 检查门互不依赖；每步 orch.safe_call 隔离，并行不改变 ok 判定。
    gates = orch.run_parallel([
        ('verify_content', lambda: orch.verify_content(
            unpacked, deck_json, plan_json, report_path=verify_report)),
        ('check_layout', lambda: orch.check_layout(final_pptx, baseline_template=template)),
        ('validate_pptx', lambda: orch.validate_pptx(final_pptx, report_path=validate_report)),
        ('check_images', lambda: orch.check_images(
            final_pptx, str(image_template), report_path=images_report)),
        ('check_contrast', lambda: orch.check_contrast(
            final_pptx, baseline_template=template, report_path=contrast_report)),
        ('check_charts', lambda: orch.check_charts(
            final_pptx, template, report_path=charts_report)),
        ('check_tables', lambda: orch.check_tables(
            final_pptx, template, report_path=tables_report)),
        ('check_structure', lambda: orch.check_structure(
            final_pptx, report_path=structure_report)),
    ])

    verify = gates['verify_content']
    steps.append({'name': 'verify_content', 'returncode': verify.returncode,
                  'stdout': verify.stdout, 'stderr': verify.stderr})
    verify_data = _gate_data(verify, verify_report, default_blocking=1)

    layout = gates['check_layout']
    layout_report.write_text(layout.stdout or json.dumps(layout.data or {}, ensure_ascii=False),
                             encoding='utf-8')
    steps.append({'name': 'check_layout', 'returncode': layout.returncode,
                  'stdout': layout.stdout, 'stderr': layout.stderr})
    layout_data = _gate_data(layout, default_blocking=1)
    if 'blocking_count' not in layout_data and layout.returncode != 0:
        layout_data = {'blocking_count': 1, 'issues': [{'type': 'layout_json_parse',
                                                        'detail': (layout.stdout or '')[:500]}]}

    validate = gates['validate_pptx']
    steps.append({'name': 'validate_pptx', 'returncode': validate.returncode,
                  'stdout': (validate.stdout or '')[:500], 'stderr': validate.stderr})
    validate_data = _gate_data(validate, validate_report, default_blocking=1)

    images = gates['check_images']
    steps.append({'name': 'check_images', 'returncode': images.returncode,
                  'stdout': (images.stdout or '')[:500], 'stderr': images.stderr})
    images_data = _gate_data(images, images_report, default_blocking=0)

    contrast = gates['check_contrast']
    steps.append({'name': 'check_contrast', 'returncode': contrast.returncode,
                  'stdout': (contrast.stdout or '')[:500], 'stderr': contrast.stderr})
    contrast_data = _gate_data(contrast, contrast_report, default_blocking=0)

    charts = gates['check_charts']
    steps.append({'name': 'check_charts', 'returncode': charts.returncode,
                  'stdout': (charts.stdout or '')[:500], 'stderr': charts.stderr})
    charts_data = _gate_data(charts, charts_report, default_blocking=0)

    tables = gates['check_tables']
    steps.append({'name': 'check_tables', 'returncode': tables.returncode,
                  'stdout': (tables.stdout or '')[:500], 'stderr': tables.stderr})
    tables_data = _gate_data(tables, tables_report, default_blocking=0)

    structure = gates['check_structure']
    structure_data = _gate_data(structure, structure_report, default_blocking=0)
    if 'advisory_count' not in structure_data:
        structure_data.setdefault('advisory_count', 0)
        structure_data.setdefault('advisories', [])
    steps.append({'name': 'check_structure', 'returncode': structure.returncode,
                  'stdout': (structure.stdout or '')[:300]})

    ok = (int(verify_data.get('blocking_count', 1)) == 0
          and int(layout_data.get('blocking_count', 1)) == 0
          and int(validate_data.get('blocking_count', 1)) == 0
          and int(images_data.get('blocking_count', 0)) == 0
          and int(charts_data.get('blocking_count', 0)) == 0
          and int(tables_data.get('blocking_count', 0)) == 0
          and int(content_semantic_data.get('blocking_count', 0)) == 0)
          # 注意：对比度（contrast_data）不计入 ok，仅供参考。

    cleanup_note = None
    if ok and unpacked.exists():
        try:
            shutil.rmtree(unpacked)
            cleanup_note = f'已清空 {unpacked}（交付成功，解包树不再需要）'
        except OSError as exc:
            cleanup_note = f'清空 {unpacked} 失败（不影响交付）：{exc}'

    report = {
        'ok': ok,
        'final_pptx': str(final_pptx),
        'size_mb': round(size_after / 1e6, 2),
        'size_before_mb': round(size_before / 1e6, 2),
        'verify_content': verify_data,
        'layout': layout_data,
        'validate': validate_data,
        'images': images_data,
        'charts': charts_data,
        'tables': tables_data,
        'contrast': contrast_data,
        'content_semantic': content_semantic_data,
        'structure': structure_data,
        'steps': steps,
        'cleanup': cleanup_note,
    }
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    headline = {
        'ok': ok,
        'final_pptx': str(final_pptx),
        'cleanup': cleanup_note,
        'verify_blocking': verify_data.get('blocking_count'),
        'layout_blocking': layout_data.get('blocking_count'),
        'validate_blocking': validate_data.get('blocking_count'),
        'image_blocking': images_data.get('blocking_count'),
        'chart_blocking': charts_data.get('blocking_count'),
        'table_blocking': tables_data.get('blocking_count'),
        'contrast_advisory': contrast_data.get('blocking_count'),
        'content_semantic_blocking': content_semantic_data.get('blocking_count'),
        'structure_advisory': structure_data.get('advisory_count'),
        'size_mb': round(size_after / 1e6, 2),
        'finalize_report': str(report_json),
    }
    if emit:
        print(json.dumps(headline, ensure_ascii=False, indent=2))
    return (0 if ok else 2), headline


def main() -> int:
    ap = argparse.ArgumentParser(description='Finalize a PPT run and enforce delivery gates.')
    ap.add_argument('run_dir')
    ap.add_argument('--template', required=True, help='Original template .pptx path')
    ap.add_argument('--deck', default='deck.selected.json')
    ap.add_argument('--plan', default='content_plan.json',
                    help='Plan used for content verification; matches the pipeline plan. '
                         'Auto-created as empty only if missing.')
    args = ap.parse_args()
    code, _ = run(args.run_dir, template=args.template, deck=args.deck, plan=args.plan, emit=True)
    return code


if __name__ == '__main__':
    raise SystemExit(main())
