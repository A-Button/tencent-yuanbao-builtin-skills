#!/usr/bin/env python3
"""Atomic deck setup: collapse unpack / select / clean / inspect into one call.

Two modes (both print a deck summary to stdout so the model immediately sees the
shape and refs — no extra inspect round needed):

  # Mode 1 — open a template and see ALL pages (to decide which to keep):
  python scripts/prepare_deck.py RUN --template /data/skills/pptx/templates/<path>

  # Mode 2 — keep/reorder/duplicate selected pages (unpacked must exist):
  python scripts/prepare_deck.py RUN --slides 1,3,5,8

Mode 2 runs select_slides → clean → inspect_deck and writes
``RUN/deck.selected.json`` (the file apply_plan.py expects). Fewer tool rounds =
higher chance weaker models finish the deck before degrading.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _validate_template(tpl: Path) -> tuple[bool, str]:
    """解包前校验模板结构，坏模板立刻失败，避免模型浪费整轮预算。"""
    val = _run([sys.executable, str(SCRIPTS / 'validate_pptx.py'), str(tpl)])
    try:
        rep = json.loads(val.stdout)
    except Exception:
        return True, ''
    if rep.get('blocking_count', 0):
        issues = rep.get('issues', [])[:5]
        detail = '; '.join(f"{i.get('type')}: {i.get('detail')}" for i in issues)
        return False, (
            f'模板结构校验失败（blocking={rep["blocking_count"]}）：{detail}。'
            '请换同场景下另一个风格模板，不要在这份模板上继续。'
        )
    return True, ''


def _scope_cheatsheet(deck: dict, batch_size: int = 3) -> str:
    slides = deck.get('slides') or []
    if not slides:
        return ''
    pairs = [f"order{s.get('order')}→slide{s.get('slide')}" for s in slides
             if s.get('order') is not None and s.get('slide') is not None]
    physical = [s['slide'] for s in slides if s.get('slide') is not None]
    lines = ['--- scope速查（--scope 用 slide 编号，不是 order）---', ', '.join(pairs)]
    if len(physical) > batch_size:
        batches = []
        for i in range(0, len(physical), batch_size):
            chunk = physical[i:i + batch_size]
            batches.append('--scope ' + ','.join(str(x) for x in chunk))
        lines.append('建议分批：' + ' | '.join(batches))
    totals = sum((s.get('capabilities') or {}).get('visual_slots_count', 0) for s in slides)
    charts = sum((s.get('capabilities') or {}).get('chart_slots_count', 0) for s in slides)
    tables = sum((s.get('capabilities') or {}).get('table_slots_count', 0) for s in slides)
    if totals or charts or tables:
        lines.append(f'整副需本地化：visual_slots≈{totals} chart_slots≈{charts} table_slots≈{tables}')
    return '\n'.join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description='Atomic unpack/select/clean/inspect for a PPT run.')
    ap.add_argument('run_dir')
    ap.add_argument('--template', help='Template .pptx to unpack (mode 1).')
    ap.add_argument('--slides', help='Comma-separated slides to keep/duplicate, e.g. 1,3,3,5 (mode 2).')
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    unpacked = run_dir / 'unpacked'
    run_dir.mkdir(parents=True, exist_ok=True)

    if not args.template and not args.slides:
        print('需要 --template（打开模板）或 --slides（选页）。', file=sys.stderr)
        return 2

    # Mode 1: unpack a fresh template.
    if args.template:
        tpl = Path(args.template)
        if not tpl.exists():
            print(f'模板不存在: {tpl}', file=sys.stderr)
            return 2
        ok_tpl, tpl_err = _validate_template(tpl)
        if not ok_tpl:
            print(tpl_err, file=sys.stderr)
            return 2
        up = _run([sys.executable, str(SCRIPTS / 'office' / 'unpack.py'), str(tpl), str(unpacked)])
        if up.returncode != 0:
            print(up.stderr or up.stdout, file=sys.stderr)
            return 2

    if not unpacked.exists():
        print(f'找不到解包目录: {unpacked}（先用 --template 解包）。', file=sys.stderr)
        return 2

    deck_out = run_dir / 'deck.json'

    # Mode 2: select + clean.
    if args.slides:
        sel = _run([sys.executable, str(SCRIPTS / 'select_slides.py'), str(unpacked), '--slides', args.slides])
        if sel.returncode != 0:
            print(sel.stderr or sel.stdout, file=sys.stderr)
            return 2
        cl = _run([sys.executable, str(SCRIPTS / 'clean.py'), str(unpacked)])
        if cl.returncode != 0:
            print(cl.stderr or cl.stdout, file=sys.stderr)
            return 2
        deck_out = run_dir / 'deck.selected.json'

    # Inspect: write full deck JSON + print human summary.
    insp = _run([sys.executable, str(SCRIPTS / 'inspect_deck.py'), str(unpacked)])
    if insp.returncode != 0:
        print(insp.stderr or insp.stdout, file=sys.stderr)
        return 2
    deck_out.write_text(insp.stdout, encoding='utf-8')

    summ = _run([sys.executable, str(SCRIPTS / 'inspect_deck.py'), str(unpacked), '--summary'])
    print(summ.stdout if summ.returncode == 0 else insp.stdout)
    try:
        deck = json.loads(insp.stdout)
        cheat = _scope_cheatsheet(deck)
        if cheat:
            print(cheat)
    except Exception:
        pass
    print(f'\n(deck JSON 已写入 {deck_out})', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
