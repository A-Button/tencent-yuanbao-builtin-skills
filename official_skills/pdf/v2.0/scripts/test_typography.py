"""端到端验证 PDF 生成质量。

生成 verify.pdf，覆盖 5 个修复点：
1. 中英文/数字混排间距异常
2. 段落首行/左侧缩进不对齐
3. 流程图样式不美观（沙盒外可能因缺 graphviz 跳过）
4. 英文字体不美观
5. 引用块/代码块中文变方块

跑法：
    cd scripts && python3 test_typography.py
    open ../verify.pdf

通过标准：
- 中英文/数字之间无明显空白突起
- 英文部分肉眼可见比思源拉丁更精致
- 所有正文段落首行缩进对齐到同一垂直线
- 引用块、代码块中所有中文正常显示，无任何方块
- 流程图节点圆角、配色统一、连线为直角折线
"""

import os
import sys

# 把 scripts 目录加进 path
THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, THIS_DIR)

from cjk_styles import make_cjk_styles, cjk_paragraph, cjk_codeblock
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Spacer, PageBreak,
)


def build():
    out_path = os.path.join(THIS_DIR, "..", "verify.pdf")
    out_path = os.path.abspath(out_path)

    styles = make_cjk_styles()
    cjk = styles["Body"].fontName

    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=50, rightMargin=50,
        topMargin=50, bottomMargin=50,
    )
    story = []

    # ==================== 1. 中英混排 ====================
    story.append(cjk_paragraph("PDF 排版验证报告", styles["Title"]))
    story.append(cjk_paragraph(
        "本文档用于验证 PDF skill 的 5 项排版修复，每节对应一个修复点。",
        styles["Body"]))

    story.append(cjk_paragraph("一、中英文与数字混排", styles["Heading1"]))
    story.append(cjk_paragraph(
        "我们在 2026 年 6 月发布了 Anthropic Claude 4.5 Sonnet，"
        "API P95 延迟由 1200ms 降至 850ms，DAU 增长 23.4%，"
        "对应 GDP +3.2% 的目标区间。GitHub stars 突破 12,000，"
        "完整 changelog 见 https://anthropic.com/changelog。",
        styles["Body"]))
    story.append(cjk_paragraph(
        "上面这一段如果出现夸张空白（数字或英文前后突然多一大段空隙），"
        "说明 wordWrap=CJK 没生效；如果英文字体看起来比中文方正生硬，"
        "说明 mix_text 的拉丁段切换没起作用。两者都正常时，整段视觉应该是连贯的。",
        styles["Body"]))

    # ==================== 2. 段落缩进 ====================
    story.append(cjk_paragraph("二、段落首行缩进与行距", styles["Heading1"]))
    long_text = (
        "互联网产品的核心是用户体验。所谓体验，不是堆砌功能，"
        "而是让用户在每一次接触中都感到顺畅、可控、值得信赖。"
        "这一原则在 AI 产品中尤其重要 —— 当模型能力足够强时，"
        "决定产品成败的不再是模型本身，而是承载模型能力的交互层、"
        '提示词架构、错误兜底、状态反馈这些「看不见的脚手架」。'
    )
    for i in range(3):
        story.append(cjk_paragraph(long_text, styles["Body"]))
    story.append(cjk_paragraph(
        "上面三段如果首行缩进对齐到同一条垂直线，且行距均匀，说明缩进/行距修复生效。",
        styles["Caption"]))

    # ==================== 3. 引用块（重点：中文不变方块） ====================
    story.append(cjk_paragraph("三、引用块", styles["Heading1"]))
    story.append(cjk_paragraph(
        "下面是一段中英混排的引用，重点检查：中文是否正常显示（不变方块），"
        "引用块是否有浅灰背景与左侧色条：",
        styles["Body"]))
    story.append(cjk_paragraph(
        "用户体验是所有产品的最高准则，优先级高于技术偏好、代码整洁度、架构优雅度。"
        "后端可以很复杂，但用户触碰到的每一层必须丝滑。"
        "这不只是 GUI —— CLI、对话式交互、Skill、系统反馈，都是交互体验。",
        styles["Quote"]))

    # ==================== 4. 代码块（重点：中文注释不变方块） ====================
    story.append(cjk_paragraph("四、代码块", styles["Heading1"]))
    story.append(cjk_paragraph(
        "重点检查：等宽字体显示、中文注释正常显示（不变方块）：",
        styles["Body"]))
    code = (
        "def cjk_paragraph(text: str, style) -> Paragraph:\n"
        "    \"\"\"创建中英分离的 Paragraph。\n"
        "    自动清理脏字符 + 把英文段切到 LatinSans 字体。\n"
        "    \"\"\"\n"
        "    text = normalize_cjk_text(text)   # 去全角空格 / Tab\n"
        "    text = mix_text(text)             # 包裹 <font name=\"LatinSans\">\n"
        "    return Paragraph(text, style)"
    )
    story.append(cjk_codeblock(code, styles["CodeBlock"]))

    story.append(cjk_paragraph(
        "行内代码示例：配置文件位于 "
        "<font name=\"MonoCJK\" backColor=\"#f4f4f5\">scripts/cjk_styles.py</font> "
        "中，可以通过环境变量 "
        "<font name=\"MonoCJK\" backColor=\"#f4f4f5\">CJK_FONT_PATH</font> 自定义。",
        styles["Body"]))

    # ==================== 5. 表格（中文不变方块） ====================
    story.append(PageBreak())
    story.append(cjk_paragraph("五、表格", styles["Heading1"]))
    data = [
        ["指标", "上周", "本周", "环比", "备注"],
        ["DAU", "12,400", "15,300", "+23.4%", "Claude 4.5 上线后"],
        ["API P95", "1.2s", "850ms", "-29.2%", "新增缓存层"],
        ["留存率", "68%", "71%", "+3pt", "符合预期"],
        ["NPS", "42", "48", "+6", "中文用户提升明显"],
    ]
    table = Table(data, colWidths=[80, 70, 70, 70, 130])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1e293b")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('FONTNAME', (0, 0), (-1, -1), cjk),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (1, 0), (-2, -1), 'CENTER'),
        ('ALIGN', (-1, 1), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(table)
    story.append(Spacer(1, 12))

    # ==================== 6. 流程图 ====================
    story.append(cjk_paragraph("六、流程图", styles["Heading1"]))
    try:
        from flowchart import embed_flowchart_in_pdf
        nodes = [
            {"id": "start", "label": "用户提交申请", "shape": "ellipse"},
            {"id": "check", "label": "材料齐全？", "shape": "diamond"},
            {"id": "review", "label": "进入审核"},
            {"id": "reject", "label": "退回补充"},
            {"id": "end", "label": "审批完成", "shape": "ellipse"},
        ]
        edges = [
            {"from": "start", "to": "check"},
            {"from": "check", "to": "review", "label": "是"},
            {"from": "check", "to": "reject", "label": "否"},
            {"from": "reject", "to": "start"},
            {"from": "review", "to": "end"},
        ]
        embed_flowchart_in_pdf(story, nodes, edges,
                                theme="clean", direction="TB",
                                caption="图 1：申请审批流程（clean 主题）")
    except Exception as e:
        story.append(cjk_paragraph(
            f"流程图渲染跳过（本地未安装 graphviz）：{e}。沙盒环境会正常渲染。",
            styles["Caption"]))

    # ==================== 7. 上下标 ====================
    story.append(cjk_paragraph("七、上下标", styles["Heading2"]))
    story.append(cjk_paragraph(
        "化学公式：H<sub>2</sub>O 是水，CO<sub>2</sub> 是二氧化碳。",
        styles["Body"]))
    story.append(cjk_paragraph(
        "勾股定理：a<super>2</super> + b<super>2</super> = c<super>2</super>。",
        styles["Body"]))

    doc.build(story)
    print(f"已生成: {out_path}")
    return out_path


if __name__ == "__main__":
    build()
