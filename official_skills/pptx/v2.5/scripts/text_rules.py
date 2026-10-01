#!/usr/bin/env python3
"""PPT 技能的共享文本规则（单一事实来源）。

replace_text.py / verify_content.py / inspect_deck.py 都从这里导入文本归一化、
清洗与哈希逻辑，避免历史上各处私有副本相互漂移。

设计原则：这里**不**维护任何"模板专属残留短语清单"——残留判定改由数据驱动
（成品文本逐字 == 模板原文，见 verify_content.py 的 untouched_template_text），
换素材时无需在此改动任何内容词。
"""

from __future__ import annotations

import hashlib
import re

# 带圈/带括号序号——模板通常自带编号，模型不应再往文案里塞这些。
_CIRCLED = (
    '①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕'
    '❶❷❸❹❺❻❼❽❾❿➀➁➂➃➄➅➆➇➈➉⓵⓶⓷⓸⓹⓺⓻⓼⓽⓾'
    '⒈⒉⒊⒋⒌⒍⒎⒏⒐⒑⓪'
)
_LEADING_MARK_RE = re.compile(r'^\s*[' + re.escape(_CIRCLED) + r'][\s、。.．::]*')

# 模型偶尔把换行/制表写成**字面转义**（反斜杠+n 两个字符）而非真实换行，
# 原样落入 XML 后在 CJK 字体里反斜杠字形是 ¥，显示成 "¥n"。这里统一还原为真字符。
_LITERAL_ESCAPE_RE = re.compile(r'\\r\\n|\\n|\\r|\\t')
_LITERAL_ESCAPE_MAP = {'\\r\\n': '\n', '\\n': '\n', '\\r': '\n', '\\t': '\t'}


def _norm(s: str) -> str:
    """去掉所有空白，用于写入后宽松校验（软换行/空白差异不应算失败）。"""
    return re.sub(r'\s+', '', s or '')


def sha_norm(s: str) -> str:
    """归一化全文的 sha1，用于精确判断"成品文本是否逐字等于模板原文"。"""
    return hashlib.sha1(_norm(s).encode('utf-8')).hexdigest()


def _unescape_literals(s: str) -> str:
    """把字面 `\\r\\n`/`\\n`/`\\r`/`\\t` 还原为真换行/制表。"""
    if not s or '\\' not in s:
        return s
    return _LITERAL_ESCAPE_RE.sub(lambda m: _LITERAL_ESCAPE_MAP[m.group(0)], s)


def _sanitize_text(s: str) -> str:
    """清洗模型常见的脏输出，保持文案干净。

    - 把字面转义 `\\n`/`\\t` 还原为真换行/制表（修 ¥n）
    - 去掉行首及句中的带圈序号 ①②…（模板自带编号）
    - 修复误插的斜杠：标点后紧跟 `/`、拉丁字母与中文之间的 `/`
    """
    if not s:
        return s
    s = _unescape_literals(s)
    s = _LEADING_MARK_RE.sub('', s)
    s = re.sub('[' + re.escape(_CIRCLED) + ']', '', s)
    # 标点后误插斜杠： "，/" → "，"
    s = re.sub(r'([，。、；：！？,.;:!?])\s*/', r'\1', s)
    # 拉丁字母↔中文之间误插的斜杠： "AI/真正" → "AI真正"
    s = re.sub(r'(?<=[A-Za-z0-9])/(?=[\u4e00-\u9fff])', '', s)
    s = re.sub(r'(?<=[\u4e00-\u9fff])/(?=[A-Za-z0-9])', '', s)
    return s
