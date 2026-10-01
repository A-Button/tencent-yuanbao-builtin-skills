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

Note: only the unpacked PPTX tree is redirected to /tmp via run_paths.py.
Small persistent files such as deck.json/deck.selected.json stay in the
literal RUN directory under /data/workspace.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from run_paths import unpacked_dir  # noqa: E402


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def main() -> int:
    ap = argparse.ArgumentParser(description='Atomic unpack/select/clean/inspect for a PPT run.')
    ap.add_argument('run_dir')
    ap.add_argument('--template', help='Template .pptx to unpack (mode 1).')
    ap.add_argument('--slides', help='Comma-separated slides to keep/duplicate, e.g. 1,3,3,5 (mode 2).')
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    unpacked = unpacked_dir(args.run_dir)

    if not args.template and not args.slides:
        print('需要 --template（打开模板）或 --slides（选页）。', file=sys.stderr)
        return 2

    # Mode 1: unpack a fresh template.
    if args.template:
        tpl = Path(args.template)
        if not tpl.exists():
            print(f'模板不存在: {tpl}', file=sys.stderr)
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
    print(f'\n(deck JSON 已写入 {deck_out})', file=sys.stderr)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
