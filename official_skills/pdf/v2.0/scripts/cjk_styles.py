"""中文 PDF 排版样式工厂 + 中英分离渲染。

使用边界：
- 仅用于已有 PDF 编辑流程中的中文 overlay、表单填写兜底、调试脚本。
- 不用于从 0 创建新 PDF；新建 PDF 必须走 SKILL.md 的 HTML→PDF 通路。

解决以下顽疾：

1. **中英文/数字混排间距异常** —— 全部样式注入 ``wordWrap="CJK"``。
2. **段落缩进错位** —— 统一 ``firstLineIndent`` / ``leading`` / ``spaceBefore-After``。
3. **英文字体不美观** —— ``mix_text()`` 自动用 ``<font name="LatinSans">`` 把英文/数字
   切到精致拉丁字体，中文留给思源。
4. **引用块/代码块中文变方块** —— 一键 patch 全部 ``getSampleStyleSheet()`` 内置样式
   的 ``fontName``，消灭"漏网样式"。

最常用调用::

    from cjk_styles import make_cjk_styles, cjk_paragraph
    styles = make_cjk_styles()
    story.append(cjk_paragraph("我们在 2026 年发布了 Claude 4.5。", styles["Body"]))
    story.append(cjk_paragraph("引用内容", styles["Quote"]))

设计取舍：
- **正文两端对齐（``TA_JUSTIFY``）** —— 中文排版的标准是两侧对齐。配合
  ``wordWrap="CJK"``（中文可在任意字符断行），每行被拉散的幅度很小，观感正；
  ReportLab 不会拉散段落最后一行，所以不会出现"末行散开"的丑态。
- **语言区分**（``make_cjk_styles(lang=...)``）：
  - ``"zh"``（默认）：正文首行缩进 21pt（≈2 个汉字），引用/代码/表格等非正文
    不缩进；全部两端对齐；``wordWrap="CJK"``。
  - ``"en"``：正文不缩进；两端对齐；``wordWrap`` 走默认（按单词断行），
    避免英文单词被从中间截断。
- 段落缩进一律用 ``firstLineIndent``，调用方在文本里**不要**再加全角空格。
- 行距 ``leading`` 取字号的 1.6–1.7 倍，比英文宽。
- 代码块例外：始终左对齐（不 justify）—— 两端对齐会拉散 token 间空格、破坏代码缩进。
"""

from __future__ import annotations

import re
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.styles import ParagraphStyle, StyleSheet1, getSampleStyleSheet
from reportlab.platypus import Paragraph

from fonts import register_all_fonts

# ---------------------------------------------------------------------------
# 文本预处理
# ---------------------------------------------------------------------------

# 匹配"连续的拉丁字符段"（英文字母/数字/常见英文标点/空格）。
# 用于把英文段切到 LatinSans 字体。注意：包含空格能让 "Claude 4.5" 整段切换。
_LATIN_RUN = re.compile(
    r"[A-Za-z0-9"
    r"\-\+\*/=<>%$#@!?.,:;'\"`~^&|()\[\]{}]"
    r"(?:[A-Za-z0-9 \-\+\*/=<>%$#@!?.,:;'\"`~^&|()\[\]{}]*"
    r"[A-Za-z0-9\-\+\*/=<>%$#@!?.,:;'\"`~^&|()\[\]{}])?"
)

# 全角空格（U+3000）—— LLM 经常用它做缩进，必须清掉
_FULLWIDTH_SPACE = "　"

# 匹配任意 CJK 表意文字（含扩展区 + 兼容区）。只要段落里有一个汉字，
# 就必须按中文标准（wordWrap="CJK"）排版，否则整段中文会被当成超长 token，
# 在英文/数字两侧逼出大段空白。
_CJK_RE = re.compile(
    r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ffff]"
)


def contains_cjk(text: str) -> bool:
    """文本中是否含有 CJK 表意文字（汉字）。"""
    return bool(text) and bool(_CJK_RE.search(text))


def _ensure_cjk_wrap(style: ParagraphStyle, text: str) -> ParagraphStyle:
    """语言自适应：段落含中文却没用 CJK 断行时，克隆一份强制 ``wordWrap="CJK"``。

    这是"lang 跟着内容主语言走"的兜底——即使调用方误把中英混排内容传进了
    ``lang="en"`` 的样式表，只要段落里有汉字，就自动按中文标准排版，
    从根上杜绝"英文/数字前后冒出大段空白"。不改原 style 对象，避免污染共享样式。
    """
    if contains_cjk(text) and getattr(style, "wordWrap", None) != "CJK":
        return style.clone(style.name + "__cjkwrap", wordWrap="CJK")
    return style


def normalize_cjk_text(text: str) -> str:
    """清理 LLM 生成的脏文本：去全角空格、压缩多余空格、Tab 转单空格。

    不做"中英文之间自动加空格"（盘古之白）—— 那是 mix_text 的活儿。
    """
    if not text:
        return text
    # 去全角空格（如果用户真的需要全角空格做对齐，请用 firstLineIndent 替代）
    text = text.replace(_FULLWIDTH_SPACE, "")
    # Tab 转 4 空格（防止 LLM 用 Tab 缩进 Paragraph）
    text = text.replace("\t", "    ")
    # 压缩 3 个以上连续空格为单空格（保留双空格做轻微停顿）
    text = re.sub(r" {3,}", " ", text)
    return text


def mix_text(text: str, latin_font: str = "LatinSans") -> str:
    """把英文/数字段包裹 ``<font name="LatinSans">…</font>``，实现中英分离渲染。

    示例::

        mix_text("我们在 2026 年发布了 Claude 4.5")
        # → '我们在 <font name="LatinSans">2026</font> 年发布了 <font name="LatinSans">Claude 4.5</font>'

    Paragraph 渲染时：
    - 未包裹的中文走 ``style.fontName``（一般是 SourceHanSans）
    - 被包裹的英文/数字走 ``LatinSans``

    注意：调用方传入的文本已经包含 ReportLab XML 标签时（比如手写了 ``<font>``、
    ``<b>``、``<sub>``），本函数只切外层 ASCII 段，不动标签内部 —— 简单起见，
    用一个状态机跳过 ``<...>`` 区间。
    """
    if not text:
        return text

    out = []
    i = 0
    n = len(text)
    plain_buf = []  # 累积非标签的纯文本

    def flush_plain():
        if not plain_buf:
            return
        plain = "".join(plain_buf)
        plain_buf.clear()
        # 在纯文本段落内做拉丁包裹
        last_end = 0
        for m in _LATIN_RUN.finditer(plain):
            out.append(plain[last_end:m.start()])
            run = m.group(0)
            # 单个英文字符或纯标点不值得包（避免 "中文,English" 中的 ","也被包）
            if len(run) >= 2 or (len(run) == 1 and run.isascii() and run.isalnum()):
                out.append(f'<font name="{latin_font}">{run}</font>')
            else:
                out.append(run)
            last_end = m.end()
        out.append(plain[last_end:])

    while i < n:
        ch = text[i]
        if ch == "<":
            # 进入标签区间，整段透传
            flush_plain()
            j = text.find(">", i)
            if j == -1:
                # 未闭合标签，剩余作为纯文本
                plain_buf.append(text[i:])
                i = n
            else:
                out.append(text[i:j + 1])
                i = j + 1
        else:
            plain_buf.append(ch)
            i += 1
    flush_plain()
    return "".join(out)


# ---------------------------------------------------------------------------
# 样式工厂
# ---------------------------------------------------------------------------
def _patch_existing_styles(stylesheet: StyleSheet1, cjk: str, word_wrap) -> None:
    """把 ``getSampleStyleSheet()`` 内的所有内置样式 fontName 切换到 CJK 字体。

    针对问题 5（引用块/代码块中文变方块）的根治：原本 BlockQuote/Code/Italic 等
    指向 Helvetica/Times/Courier，遇中文必方块。这里强制全部切换。

    **重要**：所有样式（包括 Code 类）都切到 ``cjk``，**不切到 ``mono``**。
    原因：常见的等宽字体（Menlo / JetBrainsMono / DejaVu Sans Mono / Courier）
    都不含中文字形，遇到中文 docstring/注释会变方块。思源黑体的中文本身就是
    等宽的，作为代码块字体牺牲了英文严格等宽，但保证中文不变方块（更高优先级）。

    若用户装了含 CJK 的真正等宽字体（如 Sarasa Mono SC），可通过 MONO_FONT_PATH
    指向它，然后手动覆盖：``styles["CodeBlock"].fontName = mono``。

    ``word_wrap`` 随语言变化：中文用 ``"CJK"``（字符级断行），英文用 ``None``
    （按单词断行，避免英文单词被从中间截断）。
    """
    for name in stylesheet.byName:
        style = stylesheet.byName[name]
        style.fontName = cjk
        # 顺手也改下 wordWrap，避免有人复用内置样式
        style.wordWrap = word_wrap


def make_cjk_styles(lang: str = "zh") -> StyleSheet1:
    """构建一套 CJK 友好的样式表。

    Args:
        lang: 目标语言。``"zh"``（默认，中文）正文首行缩进、字符级断行；
            ``"en"``（英文）正文不缩进、按单词断行。两种语言正文都两端对齐。
            **中文 / 中英混排文档保持默认即可，不要传 ``"en"``。** 即使误传了，
            ``cjk_paragraph`` / ``cjk_codeblock`` 也会对含汉字的段落自动套用中文标准
            （``wordWrap="CJK"``），所以中英混排不会出现大段空白；``"en"`` 仅适合
            纯英文文档（让英文按单词断行、不被从中间截断）。

    返回的 stylesheet 包含：
    - 内置样式（Normal / Title / Heading1-6 / BodyText / BlockQuote / Code / ...）
      —— fontName 已 patch 为 CJK，wordWrap 随语言设定
    - 新增样式（Body / BodyNoIndent / Quote / Caption / CodeBlock / ListItem ...）
      —— 针对中文排版优化的预设

    排版差异（zh vs en）：
    - 正文 ``Body`` 首行缩进：zh = 21pt，en = 0
    - 正文/引用对齐：两者都 ``TA_JUSTIFY``（两端对齐）
    - ``wordWrap``：zh = ``"CJK"``，en = ``None``（按单词断行）
    - 引用块、代码块、表格等非正文：不缩进
    """
    is_en = str(lang).lower().startswith("en")
    word_wrap = None if is_en else "CJK"
    body_first_line_indent = 0 if is_en else 21

    fonts = register_all_fonts()
    cjk = fonts["cjk"]
    latin = fonts["latin"]
    mono = fonts["mono"]

    # 1. 拿到内置 stylesheet 并 patch
    ss = getSampleStyleSheet()
    _patch_existing_styles(ss, cjk, word_wrap)

    # 2. 新增 / 覆盖关键样式
    common = dict(
        fontName=cjk,
        wordWrap=word_wrap,
    )

    # --- 正文（两端对齐；中文首行缩进，英文不缩进） ---
    ss.add(ParagraphStyle(
        name="Body",
        parent=ss["Normal"],
        fontSize=10.5,
        leading=18,                  # 1.7×
        firstLineIndent=body_first_line_indent,  # zh≈2 个汉字（10.5 * 2），en=0
        spaceBefore=0,
        spaceAfter=6,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#1f2937"),
        **common,
    ))
    ss.add(ParagraphStyle(
        name="BodyNoIndent",
        parent=ss["Body"],
        firstLineIndent=0,
    ))

    # --- 标题 ---
    # 注意：内置 Title/Heading1-3 已被 patch，但它们的字号/行距/间距还是英文经验值
    # 这里覆盖关键参数让中文标题更舒展
    ss["Title"].fontSize = 22
    ss["Title"].leading = 30
    ss["Title"].alignment = TA_CENTER
    ss["Title"].spaceAfter = 18
    ss["Title"].textColor = colors.HexColor("#0f172a")

    ss["Heading1"].fontSize = 18
    ss["Heading1"].leading = 26
    ss["Heading1"].spaceBefore = 18
    ss["Heading1"].spaceAfter = 10
    ss["Heading1"].textColor = colors.HexColor("#1a1a1a")

    ss["Heading2"].fontSize = 14
    ss["Heading2"].leading = 22
    ss["Heading2"].spaceBefore = 14
    ss["Heading2"].spaceAfter = 8
    ss["Heading2"].textColor = colors.HexColor("#1a1a1a")

    ss["Heading3"].fontSize = 12
    ss["Heading3"].leading = 20
    ss["Heading3"].spaceBefore = 10
    ss["Heading3"].spaceAfter = 6
    ss["Heading3"].textColor = colors.HexColor("#1a1a1a")

    # --- 引用块（非正文：首行不缩进，两端对齐，带左右内缩与浅灰底） ---
    ss.add(ParagraphStyle(
        name="Quote",
        parent=ss["Normal"],
        fontSize=10,
        leading=18,
        firstLineIndent=0,           # 非正文：不做首行缩进
        leftIndent=24,
        rightIndent=24,
        spaceBefore=8,
        spaceAfter=8,
        alignment=TA_JUSTIFY,
        textColor=colors.HexColor("#475569"),
        backColor=colors.HexColor("#f8fafc"),
        borderColor=colors.HexColor("#3b82f6"),
        borderWidth=0,
        borderPadding=10,
        # 左边框模拟：用 leftIndent + 重写 background 不太行，
        # 实际效果靠 backColor + borderPadding 给出"块感"，颜色用 #f8fafc 浅灰
        **common,
    ))

    # --- 代码块（中文不变方块优先；严格等宽次之） ---
    # 重要：默认 fontName 用 cjk（不是 mono）。
    # 原因：常见的等宽字体（Menlo / JetBrainsMono / DejaVu Sans Mono / Courier）
    #       **都不含中文字形**，直接用会让中文 docstring/注释变方块。
    # 思源黑体本身中文是等宽的，英文不严格等宽但视觉可接受，作为兜底最稳。
    # 如果用户装了含 CJK 的等宽字体（如 Sarasa Mono SC），通过 MONO_FONT_PATH
    # 环境变量指向它，fonts.register_mono_font() 会优先加载，此时可手动改 fontName=mono。
    # 代码块例外：始终左对齐（不 justify）—— 两端对齐会拉散 token 间空格、破坏代码缩进。
    ss.add(ParagraphStyle(
        name="CodeBlock",
        parent=ss["Normal"],
        fontName=cjk,
        fontSize=9,
        leading=14,
        firstLineIndent=0,           # 非正文：不缩进
        leftIndent=12,
        rightIndent=12,
        spaceBefore=6,
        spaceAfter=6,
        alignment=TA_LEFT,
        textColor=colors.HexColor("#1e293b"),
        backColor=colors.HexColor("#f4f4f5"),
        borderPadding=8,
        wordWrap=word_wrap,
    ))

    # --- 图表说明 ---
    ss.add(ParagraphStyle(
        name="Caption",
        parent=ss["Normal"],
        fontSize=9,
        leading=14,
        alignment=TA_CENTER,
        spaceBefore=4,
        spaceAfter=12,
        textColor=colors.HexColor("#6b7280"),
        **common,
    ))

    # --- 列表项（不缩进首行，spaceAfter 紧凑） ---
    ss.add(ParagraphStyle(
        name="ListItem",
        parent=ss["Body"],
        firstLineIndent=0,
        leftIndent=18,
        bulletIndent=0,
        spaceAfter=3,
    ))

    return ss


# ---------------------------------------------------------------------------
# 便捷封装
# ---------------------------------------------------------------------------
def cjk_paragraph(
    text: str,
    style: ParagraphStyle,
    *,
    normalize: bool = True,
    latinize: bool = True,
) -> Paragraph:
    """一键创建 Paragraph：自动 normalize → mix → Paragraph。

    Args:
        text: 原始文本（可含 ReportLab XML 标签如 ``<b>`` ``<font>``）
        style: 通过 ``make_cjk_styles()`` 拿到的样式
        normalize: 是否清理全角空格、Tab 等脏字符（默认开）
        latinize: 是否把英文/数字段切到 LatinSans 字体（默认开）

    语言自适应：段落含汉字时自动套用中文标准 ``wordWrap="CJK"``（即使样式来自
    ``lang="en"`` 的样式表），保证中英混排不出现大段空白。
    """
    if normalize:
        text = normalize_cjk_text(text)
    if latinize:
        text = mix_text(text)
    style = _ensure_cjk_wrap(style, text)
    return Paragraph(text, style)


def cjk_codeblock(
    code: str,
    style: ParagraphStyle,
    *,
    mono_font: str = "MonoCJK",
) -> Paragraph:
    """创建一个**中英分离的代码块**（替代 ``Preformatted``）。

    对代码内容做三件事：
    1. HTML 转义（< > & 保留为字面量）
    2. 缩进/换行转 XML（多空格 → &nbsp;，\\n → <br/>，\\t → 4 个 &nbsp;）
    3. 用 ``mix_text`` 把英文/数字段切到 ``MonoCJK`` 等宽字体

    渲染结果：
    - 中文（docstring、注释）走 ``style.fontName``（一般是 SourceHanSans）→ 不变方块
    - 英文（关键字、变量名、字符串）走 ``MonoCJK`` → 等宽

    比 ``Preformatted(code, CodeBlock)`` 更适合中英混排代码，但失去了
    Preformatted 的严格行级布局保证（自动换行可能会拆词）。

    Args:
        code: 原始代码字符串（不要预先转义）
        style: 通过 ``make_cjk_styles()`` 拿到的 ``CodeBlock`` 样式
        mono_font: 等宽字体名（默认 MonoCJK）
    """
    import html
    text = html.escape(code)
    # 多空格保留（HTML 默认会折叠空格）
    text = re.sub(r" {2,}", lambda m: "&nbsp;" * len(m.group(0)), text)
    text = text.replace("\t", "&nbsp;" * 4)
    text = text.replace("\n", "<br/>")
    # 把英文/数字段切到等宽字体（覆盖 mix_text 的默认 LatinSans）
    text = mix_text(text, latin_font=mono_font)
    style = _ensure_cjk_wrap(style, text)
    return Paragraph(text, style)


__all__ = [
    "make_cjk_styles",
    "cjk_paragraph",
    "cjk_codeblock",
    "mix_text",
    "normalize_cjk_text",
    "contains_cjk",
]


if __name__ == "__main__":
    # 烟测：打印一些样式参数 + 测试 mix_text 转换
    styles = make_cjk_styles()
    print("已构建样式数:", len(styles.byName))
    for name in ("Body", "Title", "Heading1", "Quote", "CodeBlock", "Caption"):
        s = styles[name]
        print(f"  {name:<12} fontName={s.fontName} size={s.fontSize} leading={s.leading} wordWrap={s.wordWrap}")
    print()
    sample = "我们在 2026 年使用 Anthropic Claude 4.5 实现了 GDP +3.2% 的增长"
    print("mix_text 输出:")
    print("  ", mix_text(sample))
