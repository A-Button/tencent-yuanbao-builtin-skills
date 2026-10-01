#!/usr/bin/env python3
"""交付前的 OOXML 结构 + 语义校验门：拦住"打开时报需要修复"的损坏。

LibreOffice 渲染对很多损坏很宽容（照常导出），所以纯渲染验证抓不到。这里直接核对
PowerPoint 真正在意的不变量：

结构：
  - zip 完整、每个 .xml/.rels 良构
  - [Content_Types].xml 覆盖所有部件
  - .rels 的非外链 Target 都存在；同一 rels 内 Relationship Id 不重复

PPT 专属（最常触发"修复"的点）：
  - presentation.xml 的 p:sldId@id 全局唯一且在合法范围 [256, 2147483647]
  - p:sldId@r:id 唯一且能在 presentation.xml.rels 解析
  - 每页 p:cNvPr@id 同页唯一
  - <a:t> 文本无非法控制字符（0x00-0x1F，\t\n\r 除外）

可选：--render 用 soffice 转 PDF，作为"能否打开"的实测兜底。

退出码：发现 blocking 返回 2，无 blocking 返回 0，无法读取返回 1。
"""

from __future__ import annotations

import argparse
import collections
import json
import posixpath
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_CT_DEFAULT_RE = re.compile(r'Extension="([^"]+)"')
_CT_OVERRIDE_RE = re.compile(r'PartName="([^"]+)"')
_CTRL_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def _zip_from_dir(unpacked: Path) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix='.pptx', delete=False)
    tmp.close()
    with zipfile.ZipFile(tmp.name, 'w', zipfile.ZIP_DEFLATED) as z:
        for p in unpacked.rglob('*'):
            if p.is_file():
                z.write(p, p.relative_to(unpacked).as_posix())
    return Path(tmp.name)


def validate(pptx_path: str, render: bool = False) -> dict:
    issues: list[dict] = []
    path_obj = Path(pptx_path)
    tmp_path: Path | None = None
    real = pptx_path
    if path_obj.is_dir():
        tmp_path = _zip_from_dir(path_obj)
        real = str(tmp_path)

    def add(kind: str, detail: str):
        issues.append({'severity': 'blocking', 'type': kind, 'detail': detail})

    try:
        with zipfile.ZipFile(real) as z:
            names = z.namelist()
            nameset = set(names)
            bad = z.testzip()
            if bad:
                add('zip_crc', f'CRC 校验失败: {bad}')

            for n in names:
                if n.endswith('.xml') or n.endswith('.rels'):
                    try:
                        ET.fromstring(z.read(n))
                    except ET.ParseError as e:
                        add('xml_malformed', f'{n}: {e}')

            # Content_Types 覆盖
            try:
                ct = z.read('[Content_Types].xml').decode('utf-8', 'ignore')
                defaults = {e.lower() for e in _CT_DEFAULT_RE.findall(ct)}
                overrides = set(_CT_OVERRIDE_RE.findall(ct))
                for n in names:
                    if n == '[Content_Types].xml' or n.endswith('/'):
                        continue
                    ext = n.rsplit('.', 1)[-1].lower() if '.' in n else ''
                    if ('/' + n) not in overrides and ext not in defaults:
                        add('content_type_missing', n)
            except KeyError:
                add('content_types_missing', '缺 [Content_Types].xml')

            # rels：Target 存在 + Id 不重复
            for n in names:
                if not n.endswith('.rels'):
                    continue
                base = re.sub(r'_rels/[^/]+$', '', n)
                raw = z.read(n).decode('utf-8', 'ignore')
                ids = re.findall(r'Id="([^"]+)"', raw)
                dups = [k for k, c in collections.Counter(ids).items() if c > 1]
                if dups:
                    add('duplicate_rel_id', f'{n}: {dups}')
                for t, mode in re.findall(r'Target="([^"]+)"(?:\s+TargetMode="([^"]+)")?', raw):
                    if mode == 'External' or t.startswith('http') or t.startswith('../'):
                        tgt = posixpath.normpath(posixpath.join(base, t)) if not t.startswith('http') else None
                    else:
                        tgt = posixpath.normpath(posixpath.join(base, t))
                    if mode == 'External' or t.startswith('http'):
                        continue
                    if tgt and tgt not in nameset:
                        add('dangling_rel', f'{n} -> {t}')

            # presentation：sldId @id 唯一/范围、r:id 唯一/可解析
            if 'ppt/presentation.xml' in nameset:
                pres = z.read('ppt/presentation.xml').decode('utf-8', 'ignore')
                sld_ids = re.findall(r'<p:sldId[^>]*\bid="(\d+)"', pres)
                dup_sid = [k for k, c in collections.Counter(sld_ids).items() if c > 1]
                if dup_sid:
                    add('duplicate_sldId', f'重复 sldId id: {dup_sid}')
                for sid in sld_ids:
                    v = int(sid)
                    if v < 256 or v > 2147483647:
                        add('sldId_out_of_range', f'sldId id={v} 超出 [256, 2147483647]')
                rids = re.findall(r'<p:sldId[^>]*r:id="([^"]+)"', pres)
                dup_rid = [k for k, c in collections.Counter(rids).items() if c > 1]
                if dup_rid:
                    add('duplicate_sldId_rid', f'重复 sldId r:id: {dup_rid}')
                rel_name = 'ppt/_rels/presentation.xml.rels'
                if rel_name in nameset:
                    rel_ids = set(re.findall(r'Id="([^"]+)"', z.read(rel_name).decode('utf-8', 'ignore')))
                    for rid in rids:
                        if rid not in rel_ids:
                            add('sldId_rid_unresolved', f'sldId r:id={rid} 在 presentation rels 中无定义')

            # 每页 cNvPr id 唯一 + 控制字符
            for n in names:
                if not re.fullmatch(r'ppt/slides/slide\d+\.xml', n):
                    continue
                raw = z.read(n).decode('utf-8', 'ignore')
                cn = re.findall(r'<p:cNvPr[^>]*\bid="(\d+)"', raw)
                dup_cn = [k for k, c in collections.Counter(cn).items() if c > 1]
                if dup_cn:
                    add('duplicate_cNvPr_id', f'{n}: 同页重复 cNvPr id {dup_cn}')
                for t in re.findall(r'<a:t>(.*?)</a:t>', raw, re.S):
                    if _CTRL_RE.search(t):
                        add('control_char', f'{n}: <a:t> 含非法控制字符')
                        break
    except (zipfile.BadZipFile, OSError) as e:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
        return {'pptx': pptx_path, 'readable': False, 'blocking_count': 1,
                'issues': [{'severity': 'blocking', 'type': 'unreadable', 'detail': str(e)}]}

    if render:
        try:
            with tempfile.TemporaryDirectory() as td:
                proc = subprocess.run(['soffice', '--headless', '--convert-to', 'pdf', '--outdir', td, real],
                                      capture_output=True, text=True, timeout=120)
                pdf = list(Path(td).glob('*.pdf'))
                if proc.returncode != 0 or not pdf:
                    add('render_failed', (proc.stderr or proc.stdout)[:300])
        except Exception as e:  # soffice 不可用等：记 warning 不阻断
            issues.append({'severity': 'warning', 'type': 'render_skipped', 'detail': str(e)[:200]})

    if tmp_path is not None:
        tmp_path.unlink(missing_ok=True)

    blocking = sum(1 for i in issues if i['severity'] == 'blocking')
    warning = sum(1 for i in issues if i['severity'] == 'warning')
    return {'pptx': pptx_path, 'readable': True, 'blocking_count': blocking,
            'warning_count': warning, 'issue_count': len(issues), 'issues': issues}


def main() -> int:
    ap = argparse.ArgumentParser(description='Validate a .pptx (or unpacked dir) for corruption.')
    ap.add_argument('pptx')
    ap.add_argument('--render', action='store_true', help='额外用 soffice 转 PDF 实测能否打开')
    ap.add_argument('--report', help='把 JSON 报告写到该路径')
    args = ap.parse_args()

    report = validate(args.pptx, render=args.render)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding='utf-8')
    print(text)
    return 2 if report['blocking_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
