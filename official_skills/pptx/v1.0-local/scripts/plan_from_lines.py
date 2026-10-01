#!/usr/bin/env python3
"""Create content_plan.json from simple model-written lines.

Input line format (tab OR run-of-spaces between the first two fields):
  ref  action  text

Examples:
  slide1:shape1    replace    2026年中国新能源汽车出海战略分析
  slide2:shape7    replace    结论一||结论二
  slide9:shape5    clear
  slide14:shape1   keep

Robustness (models frequently get these wrong):
- The ref/action separator may be a TAB or one-or-more spaces.
- Multi-paragraph text may use ``||`` OR be written across several physical
  lines (a real newline). Any physical line that does NOT start with a
  ``slideN:shapeM <action>`` header is treated as a continuation paragraph of
  the previous ``replace`` entry, so an accidental ``\n`` no longer breaks the
  whole file.
- A malformed line is skipped with a warning instead of aborting the run, so a
  single bad line never produces an empty/invalid content_plan.json.

This avoids large hand-written JSON and lets Python handle escaping.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


# slideN:shapeM (also tolerates image1/etc as the second token) followed by an action.
_HEADER_RE = re.compile(
    r'^(?P<ref>slide\d+:[A-Za-z]+\d+)[\t ]+(?P<action>replace|clear|keep)\b[\t ]*(?P<text>.*)$'
)
# 形似 ref 开头（但 action/格式可能非法）——用于区分"真·续行段落"和"写坏的 ref 行"。
_REFLIKE_RE = re.compile(r'^slide\d+:[A-Za-z]+\d+\b')
# 段落分隔：显式 ||、以及模型偶尔写成的字面转义 \n / \r\n。
_PARA_SPLIT_RE = re.compile(r'\|\||\\r\\n|\\n')


def _load_deck(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8'))


def _parse_lines(path: Path) -> dict[str, dict]:
    updates: dict[str, dict] = {}
    warnings: list[str] = []
    current_ref: str | None = None  # last 'replace' ref, for continuation lines

    for lineno, raw in enumerate(path.read_text(encoding='utf-8').splitlines(), start=1):
        line = raw.replace('\r', '').strip()
        if not line or line.startswith('#'):
            continue

        m = _HEADER_RE.match(line)
        if not m:
            # 形似 ref 开头却没匹配上 → 八成是写坏的 ref 行（action 拼错/缺分隔），
            # 显式告警并跳过，不再静默并入上一条 replace（避免污染上一段文案）。
            if _REFLIKE_RE.match(line):
                warnings.append(f'第 {lineno} 行像 ref 行但 action/格式非法，已跳过：{line[:60]}')
                current_ref = None
                continue
            # 否则视为上一条 replace 的续行段落（兼容用真实换行写的多段文本）。
            if current_ref and updates.get(current_ref, {}).get('action') == 'replace':
                extra = [p.strip() for p in _PARA_SPLIT_RE.split(line) if p.strip()]
                if extra:
                    updates[current_ref].setdefault('paragraphs', []).extend(extra)
            else:
                warnings.append(f'第 {lineno} 行无法识别，已跳过：{line[:50]}')
            continue

        ref = m.group('ref').strip()
        action = m.group('action').strip()
        text = m.group('text').strip()

        item: dict = {'action': action}
        if action == 'replace':
            paragraphs = [p.strip() for p in _PARA_SPLIT_RE.split(text) if p.strip()]
            item['paragraphs'] = paragraphs  # may be filled by continuation lines
            current_ref = ref
        else:
            current_ref = None
        updates[ref] = item

    # Drop replace entries that never received any text (warn, don't abort).
    for ref, item in list(updates.items()):
        if item.get('action') == 'replace' and not item.get('paragraphs'):
            warnings.append(f'ref {ref} 为 replace 但无文本，已忽略')
            del updates[ref]

    for w in warnings:
        print(w, file=sys.stderr)
    return updates


def main() -> int:
    ap = argparse.ArgumentParser(description='Build content_plan.json from deck JSON and TSV-like lines.')
    ap.add_argument('deck_json')
    ap.add_argument('lines_txt')
    args = ap.parse_args()

    deck = _load_deck(Path(args.deck_json))
    updates = _parse_lines(Path(args.lines_txt))
    seen_refs: set[str] = set()

    out = {
        'version': 1,
        'slides': [],
    }
    for slide in deck.get('slides', []):
        s_out = {
            'order': slide.get('order'),
            'slide': slide.get('slide'),
            'slide_file': slide.get('slide_file'),
            'purpose': '',
            'texts': [],
        }
        for t in slide.get('texts', []):
            ref = t.get('ref')
            seen_refs.add(ref)
            update = updates.get(ref)
            if update:
                item = {
                    'ref': ref,
                    'shape': t.get('shape'),
                    'shape_id': t.get('shape_id'),
                    'kind': t.get('kind'),
                    'current': t.get('text', ''),
                    **update,
                }
            else:
                item = {
                    'ref': ref,
                    'shape': t.get('shape'),
                    'shape_id': t.get('shape_id'),
                    'kind': t.get('kind'),
                    'current': t.get('text', ''),
                    'action': 'keep',
                    'paragraphs': [],
                }
            s_out['texts'].append(item)
        out['slides'].append(s_out)

    unknown = sorted(set(updates) - seen_refs)
    if unknown:
        print('忽略未知 ref: ' + ', '.join(unknown[:12]), file=sys.stderr)

    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
