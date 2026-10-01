#!/usr/bin/env python3
"""Verify that a text plan was actually applied to an unpacked PPTX.

Checks:
  - replace targets no longer contain the old template text and contain new text
  - clear targets are empty
  - keep targets remain unchanged when possible
  - title/body shapes left byte-for-byte identical to the template original (and not
    handled by the plan) are blocked as untouched_template_text (data-driven, no phrase list)
  - long uncovered template texts and dirty outputs (circled numbers, stray slashes,
    literal \\n escapes) are flagged as warnings
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

from text_rules import _CIRCLED, _norm, _sanitize_text, sha_norm

_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
_REF_RE = re.compile(r'^slide(\d+):shape(\d+)$')

# 脏文本/无效字段：模型常见的输出瑕疵（反馈 row6 / row9 / row14）
_DIRTY_PATTERNS = [
    (re.compile('[' + re.escape(_CIRCLED) + ']'),
     'circled_number', '文案里含带圈序号①②，请删除（模板自带编号）'),
    (re.compile(r'[，。、；：！？]\s*/'),
     'stray_slash', '标点后误插斜杠，请删除 /'),
    (re.compile(r'[A-Za-z0-9]/[\u4e00-\u9fff]|[\u4e00-\u9fff]/[A-Za-z0-9]'),
     'stray_slash', '中英文之间误插斜杠（如 AI/真正），请删除 /'),
    (re.compile(r'(N/A|暂无数据|待填|待补充|待定|TODO|undefined|null|\bNaN\b)', re.I),
     'invalid_data', '疑似无效/占位数据字段，请填入真实内容或删除'),
    (re.compile(r'\\n|\\t|\\r'),
     'literal_escape', '文案含字面转义 \\n/\\t（会显示成 ¥n）：请用真实换行或 || 分段'),
]


# "短数据/数字"槽位：模板原文是纯数字+可选短单位（如 117 / 60% / 21万 / 36.6万吨）、且很短。
# 这类槽位只该放短数据，被塞进长句（典型：把整段文案塞进数字位）会炸框压字——blocking。
_DATA_TOKEN_RE = re.compile(
    r'^[+\-]?[\d]+(?:[.,]\d+)?\s*'
    r'[百千万亿]?\s*'
    r'[%‰°℃元亩吨年天月日个件人次台套户家分秒倍米㎡平方公里千克克吨]?$')


def _is_short_data_slot(original: str) -> bool:
    o = (original or '').strip()
    return 0 < len(o) <= 6 and bool(_DATA_TOKEN_RE.match(o))


def _is_long_prose(wanted: str) -> bool:
    w = (wanted or '').strip()
    return len(w) >= 12 or bool(re.search(r'[，。、；：！？]', w))


def _parse_ref(ref: str) -> tuple[int, int]:
    m = _REF_RE.match(ref)
    if not m:
        raise ValueError(f'非法 ref: {ref}')
    return int(m.group(1)), int(m.group(2))


def _shape_text(shape: ET.Element) -> str:
    paragraphs: list[str] = []
    for para in shape.findall(f'.//{{{_A}}}p'):
        text = ''.join(t.text or '' for t in para.findall(f'.//{{{_A}}}t')).strip()
        if text:
            paragraphs.append(text)
    return '\n'.join(paragraphs).strip()


def _read_ref_text(unpacked: Path, ref: str) -> str:
    slide, shape = _parse_ref(ref)
    path = unpacked / 'ppt' / 'slides' / f'slide{slide}.xml'
    if not path.exists():
        raise FileNotFoundError(f'找不到 {path}')
    root = ET.parse(path).getroot()
    shapes = list(root.iter(f'{{{_P}}}sp'))
    if shape < 1 or shape > len(shapes):
        raise IndexError(f'{ref} 不存在，第 {slide} 页只有 {len(shapes)} 个 shape')
    return _shape_text(shapes[shape - 1])


def _normalize_plan(plan: dict) -> list[dict]:
    ops: list[dict] = []
    if isinstance(plan.get('replacements'), list):
        for rep in plan['replacements']:
            op = dict(rep)
            op.setdefault('action', 'replace')
            ops.append(op)
        return ops
    for slide in plan.get('slides', []):
        slide_no = slide.get('slide')
        for key in ('texts', 'replacements'):
            for item in slide.get(key, []) or []:
                op = dict(item)
                if 'slide' not in op and slide_no is not None:
                    op['slide'] = slide_no
                op.setdefault('action', 'replace')
                ops.append(op)
    return ops


def _op_ref(op: dict) -> str:
    if op.get('ref'):
        return str(op['ref'])
    return f"slide{int(op['slide'])}:shape{int(op['shape'])}"


def _wanted_text(op: dict) -> str:
    if 'paragraphs' in op and isinstance(op['paragraphs'], list):
        return '\n'.join(str(v) for v in op['paragraphs']).strip()
    return str(op.get('text', '')).strip()


def _all_text_refs(unpacked: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    slide_dir = unpacked / 'ppt' / 'slides'
    for path in sorted(slide_dir.glob('slide*.xml'), key=lambda p: int(re.search(r'\d+', p.name).group())):
        slide = int(re.search(r'\d+', path.name).group())
        root = ET.parse(path).getroot()
        for idx, shape in enumerate(root.iter(f'{{{_P}}}sp'), start=1):
            text = _shape_text(shape)
            if text:
                out[f'slide{slide}:shape{idx}'] = text
    return out


def verify(unpacked: Path, deck_json: Path, plan_json: Path) -> dict:
    deck = json.loads(deck_json.read_text(encoding='utf-8'))
    plan = json.loads(plan_json.read_text(encoding='utf-8'))
    ops = _normalize_plan(plan)
    issues: list[dict] = []
    touched: set[str] = set()

    # 模板原文信息（来自 inspect 期、未编辑的选页 deck）：
    #   text : 截断样本，仅用于消息展示与 uncovered 长度判断
    #   sha  : 未截断全文的归一化哈希，用于精确判断"成品是否逐字等于模板原文"
    #   kind : title/body/decorative_candidate/empty
    orig_info: dict[str, dict] = {}
    original_by_ref: dict[str, str] = {}
    for slide in deck.get('slides', []):
        for text in slide.get('texts', []):
            ref = text.get('ref')
            if not ref:
                continue
            ref = str(ref)
            orig_info[ref] = {
                'text': str(text.get('text', '')).strip(),
                'sha': text.get('orig_sha'),
                'kind': text.get('kind'),
            }
            original_by_ref[ref] = orig_info[ref]['text']

    for op in ops:
        try:
            ref = _op_ref(op)
            touched.add(ref)
            current = _read_ref_text(unpacked, ref)
        except Exception as exc:
            issues.append({'severity': 'blocking', 'type': 'ref_error', 'ref': op.get('ref'), 'current_text': '', 'suggestion': str(exc)})
            continue

        action = str(op.get('action', 'replace')).lower()
        original = str(op.get('current') or original_by_ref.get(ref, '')).strip()
        wanted = _wanted_text(op)
        # 与写入端一致：清洗目标文案 + 去空白后比较（兼容自动清洗与框内软换行）
        wanted_norm = _norm(_sanitize_text(wanted))
        current_norm = _norm(current)
        if action == 'replace':
            if not wanted:
                issues.append({'severity': 'blocking', 'type': 'empty_replace', 'ref': ref, 'current_text': current, 'suggestion': 'replace 需要填写 paragraphs'})
            elif wanted_norm and wanted_norm not in current_norm:
                issues.append({'severity': 'blocking', 'type': 'replace_not_applied', 'ref': ref, 'current_text': current, 'suggestion': '重新运行 replace_text.py 或修正 ref'})
            # old_text_left：旧模板文字在替换后仍残留。但若旧文本本就是新文案有意
            # 包含的子串（_norm(original) in wanted_norm），则属正常，不报，避免误伤。
            orig_n = _norm(original)
            if (original and orig_n in current_norm and orig_n != wanted_norm
                    and orig_n not in wanted_norm):
                issues.append({'severity': 'blocking', 'type': 'old_text_left', 'ref': ref, 'current_text': current, 'suggestion': '旧模板文字仍存在，缩小或修正替换目标'})
            # 槽位容量错配：模板原槽位是短数据/数字，却被塞进长句 → 炸框压字（blocking）。
            if wanted and _is_short_data_slot(original) and _is_long_prose(wanted):
                issues.append({'severity': 'blocking', 'type': 'data_slot_misuse', 'ref': ref,
                               'current_text': current,
                               'suggestion': f'该槽位是数字/短数据位（模板原文"{original}"），只放短数据；'
                                             '长叙述请改放正文/要点区，勿塞进数字位'})
        elif action == 'clear':
            if current.strip():
                issues.append({'severity': 'blocking', 'type': 'clear_not_applied', 'ref': ref, 'current_text': current, 'suggestion': '该 ref 应被清空'})
        elif action == 'keep':
            # keep 只该用于品牌/页码等装饰文本。用 keep 显式保留标题/正文的模板原文，
            # 同样属于"漏改模板示范文案"——逐字等于模板原文则 blocking（与不在 plan 内的
            # untouched_template_text 同等对待，堵住用 keep 绕过阻断的漏洞）。
            info = orig_info.get(ref)
            if (info and info.get('sha') and info.get('kind') in {'title', 'body'}
                    and sha_norm(current) == info['sha']):
                issues.append({'severity': 'blocking', 'type': 'untouched_template_text', 'ref': ref,
                               'current_text': current,
                               'suggestion': '标题/正文不能 keep 模板原文：改成 replace 成你的内容或 clear；'
                                             'keep 仅用于品牌/页码等装饰文本'})
            elif original and current != original:
                issues.append({'severity': 'warning', 'type': 'keep_changed', 'ref': ref, 'current_text': current, 'suggestion': '确认是否需要 keep'})
        else:
            issues.append({'severity': 'blocking', 'type': 'bad_action', 'ref': ref, 'current_text': current, 'suggestion': 'action 只能是 replace/clear/keep'})

    for ref, text in _all_text_refs(unpacked).items():
        for pat, kind, sugg in _DIRTY_PATTERNS:
            if pat.search(text):
                issues.append({'severity': 'warning', 'type': kind, 'ref': ref, 'current_text': text[:240], 'suggestion': sugg})

        info = orig_info.get(ref)
        # 数据驱动的残留判定：某 ref 不在 plan 中、是标题/正文、且成品文本**逐字等于**
        # 模板原文 → 模型确实漏改了模板示范文案，blocking（逐字相等不会误伤新内容）。
        untouched = False
        if (ref not in touched and info and info.get('sha')
                and info.get('kind') in {'title', 'body'}
                and sha_norm(text) == info['sha']):
            issues.append({'severity': 'blocking', 'type': 'untouched_template_text', 'ref': ref,
                           'current_text': text[:240],
                           'suggestion': '该标题/正文与模板原文完全一致，疑似漏替换：在 plan 中 replace 或 clear'})
            untouched = True

        # uncovered（warning）：较长且未在 plan 处理的原文，提示但不阻断；
        # 已命中 untouched(blocking) 的同一 ref 不再重复 warning。
        original = (info or {}).get('text', '').strip()
        if not untouched and ref not in touched and original and len(original) >= 18:
            issues.append({'severity': 'warning', 'type': 'uncovered_template_text', 'ref': ref, 'current_text': text[:240], 'suggestion': '如非品牌/页码装饰，请在 plan 中 replace 或 clear'})

    blocking = sum(1 for i in issues if i['severity'] == 'blocking')
    warning = sum(1 for i in issues if i['severity'] == 'warning')
    return {
        'unpacked': str(unpacked),
        'blocking_count': blocking,
        'warning_count': warning,
        'issues': issues,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description='Verify PPT content replacement result.')
    ap.add_argument('unpacked')
    ap.add_argument('--deck', required=True, help='deck.selected.json from inspect_deck.py')
    ap.add_argument('--plan', required=True, help='content_plan.json')
    ap.add_argument('--report', help='Write report JSON to this path')
    args = ap.parse_args()

    report = verify(Path(args.unpacked), Path(args.deck), Path(args.plan))
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(text, encoding='utf-8')
    print(text)
    return 2 if report['blocking_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
