#!/usr/bin/env python3
"""按计划把图表数据本地化：改写选中页里图表的类目/系列/数值缓存。

输入 charts.json（JSON 数组，每项一个图表 ref）：
[
  {"ref":"slide5:chart1",
   "categories":["2021","2022","2023","2024"],
   "series":[{"name":"营收(亿元)","values":[12,18,27,41]},
             {"name":"毛利(亿元)","values":[3,5,9,15]}],
   "title":"近四年营收与毛利"},
  {"ref":"slide8:chart1", "categories":["华东","华南","华北"], "values":[0.45,0.33,0.22]}
]

ref 用 deck.selected.json 每页 `chart_slots` 里的 `slideN:chartK`（选页/复制后的新编号）。
点数须与类目数对齐；占比类图表按模板原量纲填（如 0~1 的小数）。
只改显示用缓存（strLit/numLit 或 strCache/numCache），不动图表样式/坐标轴/内嵌工作簿。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from chart_utils import apply_chart_edit, slide_charts_unpacked
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from chart_utils import apply_chart_edit, slide_charts_unpacked

try:
    from pptx_locks import path_lock
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pptx_locks import path_lock

_REF_RE = re.compile(r'^slide(\d+):chart(\d+)$')
_MAX_WORKERS = 8


def _resolve(unpacked: Path, ref: str) -> Path | None:
    m = _REF_RE.match(ref or '')
    if not m:
        return None
    slide_no, k = int(m.group(1)), int(m.group(2))
    charts = slide_charts_unpacked(unpacked, slide_no)
    for r, path in charts:
        if r == ref:
            return path
    if 1 <= k <= len(charts):
        return charts[k - 1][1]
    return None


def _apply_one(unpacked: Path, i: int, op: dict) -> dict:
    ref = op.get('ref')
    try:
        part = _resolve(unpacked, str(ref))
        if part is None or not part.exists():
            avail = []
            m = _REF_RE.match(str(ref) or '')
            if m:
                avail = [r for r, _ in slide_charts_unpacked(unpacked, int(m.group(1)))]
            raise FileNotFoundError(
                f'{ref} 未找到对应图表；该页可用图表 ref: {", ".join(avail) or "无"}')
        with path_lock(part):
            xml = part.read_text(encoding='utf-8')
            new_xml, summary = apply_chart_edit(xml, op)
            if summary.get('series_found', 0) == 0:
                raise ValueError(f'{ref} 对应图表无 c:ser 系列，无法改数据')
            part.write_text(new_xml, encoding='utf-8')
        return {'index': i, 'ref': ref, 'ok': True, **summary}
    except Exception as exc:  # noqa: BLE001
        return {'index': i, 'ref': ref, 'ok': False, 'error': str(exc)}


def apply_ops(unpacked: Path, ops: list[dict]) -> dict:
    report = {'planned': len(ops), 'applied': 0, 'ops': [], 'errors': []}
    if not ops:
        return report
    unpacked = Path(unpacked)
    workers = min(_MAX_WORKERS, len(ops))
    results: list[dict | None] = [None] * len(ops)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_apply_one, unpacked, i, op): i - 1
                for i, op in enumerate(ops, start=1)}
        for fut in as_completed(futs):
            idx = futs[fut]
            try:
                results[idx] = fut.result()
            except Exception as exc:  # noqa: BLE001
                op = ops[idx]
                results[idx] = {'index': idx + 1, 'ref': op.get('ref'), 'ok': False, 'error': str(exc)}
    for item in results:
        if not item:
            continue
        if item.get('ok'):
            summary = {k: v for k, v in item.items() if k not in {'index', 'ok'}}
            report['ops'].append(summary)
            report['applied'] += 1
        else:
            report['errors'].append({'index': item.get('index'), 'ref': item.get('ref'),
                                     'error': item.get('error')})
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description='Localize chart cache data by ref.')
    ap.add_argument('unpacked')
    ap.add_argument('charts_json', help='JSON 数组文件；每项含 ref + categories/series 或 values')
    ap.add_argument('--report', help='把 JSON 报告写到该路径')
    args = ap.parse_args()

    try:
        ops = json.loads(Path(args.charts_json).read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        print(f'charts JSON 解析失败: {exc}', file=sys.stderr)
        return 2
    if not isinstance(ops, list):
        print('charts.json 必须是 JSON 数组', file=sys.stderr)
        return 2

    report = apply_ops(Path(args.unpacked), ops)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding='utf-8')
    print(text)
    return 2 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
