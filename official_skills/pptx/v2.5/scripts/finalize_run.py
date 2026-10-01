#!/usr/bin/env python3
"""Finalize a PPT run directory with one command.

This script is the final gate for the PPT skill:
  1. pack the /tmp unpacked tree to the single deliverable path (see run_paths.py)
  2. verify content has no blocking stale-template issues
  3. verify layout has no blocking issues
  4. write RUN/finalize_report.json

It intentionally tolerates content warnings, because many final decks contain
long user-written text that did not come from the latest small repair plan.

Note: only the unpacked PPTX tree is redirected to /tmp via run_paths.py.
Small persistent files (deck JSON, content_plan.json, reports) stay in the
literal RUN directory under /data/workspace. The packed .pptx is written
exactly once, directly to run_paths.final_pptx_path() — a flat file under
/data/workspace, never under RUN itself. See run_paths.py.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))

from run_paths import final_pptx_path, unpacked_dir  # noqa: E402


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def main() -> int:
    ap = argparse.ArgumentParser(description='Finalize a PPT run and enforce delivery gates.')
    ap.add_argument('run_dir')
    ap.add_argument('--template', required=True, help='Original template .pptx path')
    ap.add_argument('--deck', default='deck.selected.json')
    ap.add_argument('--plan', default='content_plan.json',
                    help='Plan used for content verification; matches the pipeline plan. '
                         'Auto-created as empty only if missing.')
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    unpacked = unpacked_dir(args.run_dir)
    final_pptx = final_pptx_path(args.run_dir)
    deck_json = run_dir / args.deck
    plan_json = run_dir / args.plan
    report_json = run_dir / 'finalize_report.json'

    scripts = SCRIPTS
    if not unpacked.exists():
        print(f'找不到解包目录: {unpacked}', file=sys.stderr)
        return 1
    if not deck_json.exists():
        print(f'找不到 deck 文件: {deck_json}', file=sys.stderr)
        return 1

    # A final gate plan only exists to let verify_content scan stale text and
    # verify explicit late repairs. It is safe to be empty.
    if not plan_json.exists():
        plan_json.write_text(json.dumps({'version': 1, 'slides': []}, ensure_ascii=False, indent=2), encoding='utf-8')

    steps: list[dict] = []

    pack = _run([
        sys.executable, str(scripts / 'office' / 'pack.py'),
        str(unpacked), str(final_pptx), '--original', args.template,
    ])
    steps.append({'name': 'pack', 'returncode': pack.returncode, 'stdout': pack.stdout, 'stderr': pack.stderr})
    if pack.returncode != 0:
        report_json.write_text(json.dumps({'ok': False, 'steps': steps}, ensure_ascii=False, indent=2), encoding='utf-8')
        print(pack.stderr or pack.stdout, file=sys.stderr)
        return 2

    size_before = final_pptx.stat().st_size if final_pptx.exists() else 0

    # 命名空间归一化（关键）：editing 步骤用 ElementTree 重序列化时会把标准前缀
    # (a/p/r/p14/c/a16…) 改成自动前缀 ns0/ns2/ns3，PowerPoint(尤其 Mac)据此判损坏→报修复。
    # 这里兜底把所有 XML part 的自动前缀按 URI 改回标准前缀。
    try:
        from ooxml_ns import normalize_pptx, fix_paragraph_order, deshare_owned_parts
        ns_rep = normalize_pptx(final_pptx)
        # 段落 endParaRPr 必须在最后，否则 PowerPoint 判 schema 损坏→修复时删内容
        po_rep = fix_paragraph_order(final_pptx)
        # 复制页若共享图表/SmartArt/内嵌对象 → PowerPoint 判损坏，这里为额外引用方克隆独立副本
        ds_rep = deshare_owned_parts(final_pptx)
        steps.append({'name': 'normalize_ns', 'returncode': 0,
                      'stdout': json.dumps({'ns': ns_rep, 'para_order': po_rep, 'deshare': ds_rep}, ensure_ascii=False)[:500]})
    except Exception as exc:  # noqa: BLE001
        steps.append({'name': 'normalize_ns', 'returncode': 1, 'stderr': f'{type(exc).__name__}: {exc}'})

    # 成品减肥：对整副成品的**所有** media 降分辨率+重压缩+清孤儿(含 .wdp)。
    # 不依赖模板是否提前减肥——模板再胖，背景/装饰大图也会在这里被压小。
    slim = _run([
        sys.executable, str(scripts / 'optimize_template_media.py'), str(final_pptx),
        '--in-place', '--max-edge', '1600', '--quality', '80',
    ])
    steps.append({'name': 'optimize_media', 'returncode': slim.returncode, 'stdout': slim.stdout[-400:], 'stderr': slim.stderr[-400:]})

    # 字体内嵌：把成品用到的字体按字重子集化内嵌进 pptx，保证换机打开字重一致、
    # 不再出现"部分常规/部分合成粗体"的混排。失败不阻断交付（只是回到未内嵌状态）。
    fonts = _run([
        sys.executable, str(scripts / 'embed_fonts.py'), str(final_pptx), '--in-place',
    ])
    steps.append({'name': 'embed_fonts', 'returncode': fonts.returncode, 'stdout': fonts.stdout[-400:], 'stderr': fonts.stderr[-400:]})

    size_after = final_pptx.stat().st_size if final_pptx.exists() else 0

    verify_report = run_dir / 'verify_content.finalize.json'
    verify = _run([
        sys.executable, str(scripts / 'verify_content.py'), str(unpacked),
        '--deck', str(deck_json), '--plan', str(plan_json), '--report', str(verify_report),
    ])
    steps.append({'name': 'verify_content', 'returncode': verify.returncode, 'stdout': verify.stdout, 'stderr': verify.stderr})
    verify_data = _read_json(verify_report) if verify_report.exists() else {}

    layout_report = run_dir / 'layout_report.json'
    layout = _run([
        sys.executable, str(scripts / 'check_layout.py'), str(final_pptx),
        '--baseline-template', args.template, '--json',
    ])
    layout_report.write_text(layout.stdout, encoding='utf-8')
    steps.append({'name': 'check_layout', 'returncode': layout.returncode, 'stdout': layout.stdout, 'stderr': layout.stderr})
    try:
        layout_data = json.loads(layout.stdout)
    except json.JSONDecodeError:
        layout_data = {'blocking_count': 1, 'issues': [{'type': 'layout_json_parse', 'detail': layout.stdout[:500]}]}

    # 结构 + 语义校验门：拦住"打开报损坏"（重复 sldId/cNvPr、rels 悬空、控制字符等）。
    validate_report = run_dir / 'validate_report.json'
    validate = _run([
        sys.executable, str(scripts / 'validate_pptx.py'), str(final_pptx),
        '--report', str(validate_report),
    ])
    steps.append({'name': 'validate_pptx', 'returncode': validate.returncode, 'stdout': validate.stdout[:500], 'stderr': validate.stderr})
    try:
        validate_data = json.loads(validate.stdout)
    except json.JSONDecodeError:
        validate_data = _read_json(validate_report) if validate_report.exists() else {'blocking_count': 1, 'issues': [{'type': 'validate_json_parse', 'detail': validate.stdout[:500]}]}

    # 配图门：选中页的显著图位必须换成主题图，不能留模板库存照片（blocking）。
    images_report = run_dir / 'images_report.json'
    images = _run([
        sys.executable, str(scripts / 'check_images.py'), str(final_pptx),
        '--template', args.template, '--report', str(images_report),
    ])
    steps.append({'name': 'check_images', 'returncode': images.returncode, 'stdout': images.stdout[:500], 'stderr': images.stderr})
    try:
        images_data = json.loads(images.stdout)
    except json.JSONDecodeError:
        images_data = _read_json(images_report) if images_report.exists() else {'blocking_count': 0, 'issues': []}

    ok = (int(verify_data.get('blocking_count', 1)) == 0
          and int(layout_data.get('blocking_count', 1)) == 0
          and int(validate_data.get('blocking_count', 1)) == 0
          and int(images_data.get('blocking_count', 0)) == 0)
    report = {
        'ok': ok,
        'final_pptx': str(final_pptx),
        'size_mb': round(size_after / 1e6, 2),
        'size_before_mb': round(size_before / 1e6, 2),
        'verify_content': verify_data,
        'layout': layout_data,
        'validate': validate_data,
        'images': images_data,
        'steps': steps,
    }
    report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')

    print(json.dumps({
        'ok': ok,
        'final_pptx': str(final_pptx),
        'verify_blocking': verify_data.get('blocking_count'),
        'layout_blocking': layout_data.get('blocking_count'),
        'validate_blocking': validate_data.get('blocking_count'),
        'image_blocking': images_data.get('blocking_count'),
        'size_mb': round(size_after / 1e6, 2),
        'finalize_report': str(report_json),
    }, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == '__main__':
    raise SystemExit(main())
