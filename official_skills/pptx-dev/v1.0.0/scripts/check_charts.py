#!/usr/bin/env python3
"""交付门：选中页里的图表数据必须按主题本地化，不能沿用模板示例数据。

做法：把**原模板**所有图表的数据签名（类目+系列名+数值，去空白）作为基线集合；
成品里若某图表的数据签名仍命中模板基线，判定为 `untouched_template_chart`(blocking)——
提示模型用 edit_chart 把该图表数据改成贴合主题的真实数值。

- 改过数据（哪怕只改类目或数值）签名即变，不会误判。
- 无图表的副本天然通过（blocking=0）。

退出码：有 blocking 返回 2，否则 0。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path

try:
    from chart_utils import chart_signature, read_chart_data, slide_charts_zip
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from chart_utils import chart_signature, read_chart_data, slide_charts_zip


def _template_chart_signatures(template: str) -> set[str]:
    sigs: set[str] = set()
    try:
        with zipfile.ZipFile(template) as z:
            for n in z.namelist():
                if re.fullmatch(r'ppt/charts/chart\d+\.xml', n):
                    try:
                        data = read_chart_data(z.read(n).decode('utf-8', 'ignore'))
                    except Exception:
                        continue
                    sig = chart_signature(data)
                    if sig.strip('#|'):
                        sigs.add(sig)
    except (zipfile.BadZipFile, OSError):
        pass
    return sigs


def _slide_numbers(z: zipfile.ZipFile) -> list[int]:
    nums = []
    for n in z.namelist():
        m = re.fullmatch(r'ppt/slides/slide(\d+)\.xml', n)
        if m:
            nums.append(int(m.group(1)))
    return sorted(nums)


def check(final_pptx: str, template: str) -> dict:
    issues: list[dict] = []
    tpl_sigs = _template_chart_signatures(template)
    try:
        z = zipfile.ZipFile(final_pptx)
    except (zipfile.BadZipFile, OSError) as e:
        return {'blocking_count': 0, 'issues': [], 'note': f'无法读取 {final_pptx}: {e}'}

    charts_seen = 0
    for sn in _slide_numbers(z):
        for ref, part in slide_charts_zip(z, sn):
            try:
                data = read_chart_data(z.read(part).decode('utf-8', 'ignore'))
            except KeyError:
                continue
            charts_seen += 1
            sig = chart_signature(data)
            if not sig.strip('#|'):
                continue
            if sig in tpl_sigs:
                cats = '/'.join(str(c) for c in data.get('categories', [])[:4])
                issues.append({
                    'severity': 'blocking', 'type': 'untouched_template_chart',
                    'ref': ref,
                    'detail': f'{ref} 图表仍是模板示例数据（类目：{cats}…）；'
                              '用 edit_chart 按本页主题改写类目/系列/数值，写进 charts.json 重跑。',
                })
    z.close()
    blocking = sum(1 for i in issues if i['severity'] == 'blocking')
    return {'blocking_count': blocking, 'charts_seen': charts_seen,
            'issue_count': len(issues), 'issues': issues}


def main() -> int:
    ap = argparse.ArgumentParser(description='Check selected-deck charts were localized off template data.')
    ap.add_argument('final_pptx')
    ap.add_argument('--template', required=True, help='原模板 .pptx（用于图表数据基线）')
    ap.add_argument('--report', help='把 JSON 报告写到该路径')
    args = ap.parse_args()

    report = check(args.final_pptx, args.template)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding='utf-8')
    print(text)
    return 2 if report['blocking_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
