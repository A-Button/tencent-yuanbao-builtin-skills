#!/usr/bin/env python3
"""交付门：选中页里的表格内容必须按主题本地化，不能沿用模板示例内容。

做法：把**原模板**所有表格的内容签名（全部单元格文本，去空白）作为基线集合；
成品里若某表格的内容签名仍命中模板基线，判定为 `untouched_template_table`(blocking)——
提示模型用 edit_table 把该表格内容改成贴合主题的真实内容。

- 改过任一单元格签名即变，不会误判。
- 无表格的副本天然通过（blocking=0）。

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
    from table_utils import read_table_grid, slide_tables_zip, table_signature
    from table_utils import _TBL_RE
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from table_utils import read_table_grid, slide_tables_zip, table_signature
    from table_utils import _TBL_RE


def _template_table_signatures(template: str) -> set[str]:
    sigs: set[str] = set()
    try:
        with zipfile.ZipFile(template) as z:
            for n in z.namelist():
                if re.fullmatch(r'ppt/slides/slide\d+\.xml', n):
                    xml = z.read(n).decode('utf-8', 'ignore')
                    for m in _TBL_RE.finditer(xml):
                        sig = table_signature(read_table_grid(m.group(0)))
                        if sig.strip('/|'):
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
    tpl_sigs = _template_table_signatures(template)
    try:
        z = zipfile.ZipFile(final_pptx)
    except (zipfile.BadZipFile, OSError) as e:
        return {'blocking_count': 0, 'issues': [], 'note': f'无法读取 {final_pptx}: {e}'}

    tables_seen = 0
    for sn in _slide_numbers(z):
        for tbl in slide_tables_zip(z, sn):
            tables_seen += 1
            sig = table_signature(tbl['cells'])
            if not sig.strip('/|'):
                continue
            if sig in tpl_sigs:
                head = ' / '.join(str(c) for c in (tbl['cells'][0] if tbl['cells'] else [])[:4])
                issues.append({
                    'severity': 'blocking', 'type': 'untouched_template_table',
                    'ref': tbl['ref'],
                    'detail': f"{tbl['ref']} 表格仍是模板示例内容（表头：{head}…）；"
                              '用 edit_table 按本页主题改写各单元格，写进 tables.json 重跑。',
                })
    z.close()
    blocking = sum(1 for i in issues if i['severity'] == 'blocking')
    return {'blocking_count': blocking, 'tables_seen': tables_seen,
            'issue_count': len(issues), 'issues': issues}


def main() -> int:
    ap = argparse.ArgumentParser(description='Check selected-deck tables were localized off template content.')
    ap.add_argument('final_pptx')
    ap.add_argument('--template', required=True, help='原模板 .pptx（用于表格内容基线）')
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
