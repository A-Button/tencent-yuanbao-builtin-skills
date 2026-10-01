#!/usr/bin/env python3
"""按计划把表格内容本地化：改写选中页里表格的单元格文本。

输入 tables.json（JSON 数组，每项一个表格 ref）：
[
  {"ref":"slide8:table1",
   "cells":[
     ["场景","2023","2024","2025"],
     ["销量(万辆)","689","950","1649"],
     ["同比增速","37.9%","37.5%","73.6%"]
   ]}
]

- ref 用 deck.selected.json 每页 `table_slots` 里的 `slideN:tableK`（选页/复制后的新编号）。
- cells 是二维数组，行×列须与该表格结构对应；某格填 null 表示保留原内容。
- 表头/数据都要改成贴合主题的真实内容，别留模板示例文字。
- 只改单元格文本，保留表格样式/边框/字体；合并单元格的占位格也按物理顺序计入下标。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:
    from table_utils import apply_table_edit, iter_tables
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from table_utils import apply_table_edit, iter_tables

try:
    from pptx_locks import slide_lock
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pptx_locks import slide_lock

_REF_RE = re.compile(r'^slide(\d+):table(\d+)$')
_MAX_WORKERS = 8


def _slide_path(unpacked: Path, slide_no: int) -> Path:
    return unpacked / 'ppt' / 'slides' / f'slide{slide_no}.xml'


def _apply_one(unpacked: Path, i: int, op: dict) -> dict:
    """单条 table op；成功返回 {'ok': True, ...}，失败返回 {'ok': False, 'error': ...}。"""
    ref = op.get('ref')
    try:
        m = _REF_RE.match(str(ref) or '')
        if not m:
            raise ValueError(f'非法 ref: {ref!r}，应形如 slideN:tableK')
        slide_no, k = int(m.group(1)), int(m.group(2))
        path = _slide_path(unpacked, slide_no)
        if not path.exists():
            raise FileNotFoundError(f'找不到 slide{slide_no}.xml')
        # 同页多表串行；不同页并行。
        with slide_lock(slide_no):
            xml = path.read_text(encoding='utf-8')
            matches = list(iter_tables(xml, slide_no))
            target = next((mm for r, mm in matches if r == ref), None)
            if target is None:
                avail = ', '.join(r for r, _ in matches) or '无'
                raise FileNotFoundError(f'{ref} 未找到对应表格；该页可用表格 ref: {avail}')
            new_tbl, summary = apply_table_edit(target.group(0), op)
            if summary.get('rows_found', 0) == 0:
                raise ValueError(f'{ref} 表格无 <a:tr> 行，无法改写')
            new_xml = xml[:target.start()] + new_tbl + xml[target.end():]
            path.write_text(new_xml, encoding='utf-8')
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
    ap = argparse.ArgumentParser(description='Localize table cell text by ref.')
    ap.add_argument('unpacked')
    ap.add_argument('tables_json', help='JSON 数组文件；每项含 ref + cells 二维数组')
    ap.add_argument('--report', help='把 JSON 报告写到该路径')
    args = ap.parse_args()

    try:
        ops = json.loads(Path(args.tables_json).read_text(encoding='utf-8'))
    except json.JSONDecodeError as exc:
        print(f'tables JSON 解析失败: {exc}', file=sys.stderr)
        return 2
    if not isinstance(ops, list):
        print('tables.json 必须是 JSON 数组', file=sys.stderr)
        return 2

    report = apply_ops(Path(args.unpacked), ops)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding='utf-8')
    print(text)
    return 2 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
