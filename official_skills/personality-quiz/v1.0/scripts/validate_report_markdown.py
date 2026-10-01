#!/usr/bin/env python3
"""Validate a user-facing divination report written in portable Markdown."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path


SYSTEM_TITLES = {"bazi": "生辰八字", "western": "天体星座"}
LAYOUT_LIMITS = {
    "desktop": {"target": 100, "hard": 130, "highlight": 36},
    "mobile": {"target": 70, "hard": 90, "highlight": 28},
}
SYSTEM_SECTIONS = {
    "bazi": {
        "foundation": ("整体解读", "性格与做事方式"),
        "focus": "关注主题",
        "optional": "大运与阶段分析",
        "closing": "观察与建议",
    },
    "western": {
        "foundation": ("整体解读", "表达与互动方式"),
        "focus": "关注主题",
        "optional": None,
        "closing": "观察与建议",
    },
}
TOPIC_HEADINGS = {
    "career": "事业发展",
    "emotion": "情感婚恋",
    "family": "家庭亲情",
    "economy": "经济状况",
    "social": "社会关系",
    "talent": "天赋挖掘",
    "spiritual": "精神成长",
    "study": "学业考试",
    "health": "身体健康",
}
FORBIDDEN_METADATA = (
    "evidence_paths",
    "supporting_signals",
    "counter_signals",
    "cannot_support",
    "chart.details",
    "schema_version",
    "luck_cycle_context",
    "luck_cycle_focus",
    "as_of_local_date",
    "option_a",
    "option_b",
    "gender_for_bazi",
    "birth_date",
    "birth_time",
    "local_datetime",
    "timezone",
    "lunar-python",
    "Astronomy Engine",
    "wrapper.",
)
FORBIDDEN_BODY_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"必然",
        r"注定",
        r"一定会",
        r"必定",
        r"百分百",
        r"一代传奇",
        r"开宗立派",
        r"财富滚滚",
        r"暴富",
        r"破财",
        r"确诊",
        r"患有",
        r"寿命",
        r"死亡时间",
        r"心脏|肝脏|肠胃|血压|癌症",
        r"录取|考上",
        r"事业指数|情感指数|\d+\s*/\s*100",
        r"买入|卖出|加仓|减仓",
        r"\b(?:19|20)\d{2}[-/.]\d{1,2}(?:[-/.]\d{1,2})?\b",
        r"(?:19|20)\d{2}年\d{1,2}月(?:\d{1,2}日)?",
        r"\b(?:19|20)\d{2}\b",
        r"\b\d{1,2}:\d{2}(?::\d{2})?\b",
        r"\b\d{1,2}时(?:\d{1,2}分)?",
        r"\b(?:forward|backward|male|female)\b",
    )
)
FORBIDDEN_HEADING = re.compile(
    r"三句话|证据|依据|支持信号|反对信号|反证|限制|不能支持|"
    r"计算口径|不确定性|引擎|边界检查|方法评分|AI\s*深度分析报告"
)
LABELED_INTERNAL_BLOCK = re.compile(
    r"^\s*(?:[-*]\s*)?(?:\*\*)?"
    r"(?:依据|证据路径|支持|支持信号|反证|反对信号|限制|不能支持)"
    r"(?:\*\*)?\s*[:：]"
)
RAW_LAYOUT_HTML = re.compile(
    r"<\s*/?\s*(?:div|section|article|table|details|summary)\b", re.I
)
MARKDOWN_TABLE_RULE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$"
)
BOLD_SPAN = re.compile(r"\*\*([^*\n]+)\*\*")
GENERIC_VERDICTS = re.compile(
    r"有机遇也有挑战|机遇与挑战并存|综合来看|总体而言|因人而异|扬长避短|保持平衡|顺其自然"
)
CONSULTANT_TERMS = re.compile(
    r"交付|复用|边界|闭环|抓手|赋能|方法论|关闭条件|价值兑现|资源配置"
)


class ValidationError(ValueError):
    pass


ADVISORY_DIAGNOSTICS = tuple(
    re.compile(pattern)
    for pattern in (
        r"^加粗判断",
        r"^加粗重点",
        r"^第 \d+ 个正文段落",
        r"^(?:desktop|mobile) 版",
        r"^正文至少需要",
        r"^有 \d+% 的重点",
        r"^详细报告正文(?:不足|超过)",
        r"^“.+”必须保留",
        r"^“整体解读”",
        r"^命理或星象底层章节合计",
        r"^“.+”分析不足",
        r"^“.+”必须包含 \d+—\d+ 个段内重点",
        r"^用户关注领域正文占比",
        r"^“观察与建议”超过",
        r"^“观察与建议”必须包含",
        r"^“大运与阶段分析”超过",
        r"^正文出现 \d+ 个咨询式抽象词",
    )
)


def split_diagnostics(details: list[str]) -> tuple[list[str], list[str]]:
    """Keep safety/contract failures blocking; return prose/layout lint as warnings."""
    errors: list[str] = []
    warnings: list[str] = []
    for detail in details:
        target = warnings if any(pattern.search(detail) for pattern in ADVISORY_DIAGNOSTICS) else errors
        target.append(detail)
    return errors, warnings


def visible_length(text: str) -> int:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"[#>*_`\[\]()|\-]", "", text)
    return len(re.sub(r"\s+", "", text))


def heading_ranges(
    lines: list[str], level: int, start_at: int = 0, end_at: int | None = None
) -> list[tuple[str, int, int]]:
    end_at = len(lines) if end_at is None else end_at
    marker = "#" * level
    starts: list[tuple[str, int]] = []
    for index in range(start_at, end_at):
        match = re.match(rf"^{marker}\s+(.+?)\s*$", lines[index])
        if match:
            starts.append((match.group(1).strip(), index))
    result: list[tuple[str, int, int]] = []
    for position, (title, start) in enumerate(starts):
        end = starts[position + 1][1] if position + 1 < len(starts) else end_at
        result.append((title, start, end))
    return result


def first_content_line(lines: list[str], start: int, end: int) -> str:
    for line in lines[start:end]:
        stripped = line.strip()
        if stripped and not re.match(r"^(?:---+|\*\*\*+)$", stripped):
            return stripped
    return ""


def prose_blocks(content: str) -> list[str]:
    """Return article paragraphs, excluding headings, lists and the disclaimer."""
    blocks: list[str] = []
    for raw in re.split(r"\n\s*\n", content):
        block = raw.strip()
        if not block or block.startswith("#") or block.startswith("AI生成内容｜"):
            continue
        block_lines = [line.strip() for line in block.splitlines() if line.strip()]
        if block_lines and all(re.match(r"^\d+\.\s+", line) for line in block_lines):
            continue
        blocks.append(" ".join(block_lines))
    return blocks


def validate_markdown(
    content: str,
    system: str,
    topics: list[str],
    layout: str,
    min_topic_ratio: float = 0.50,
    min_characters: int = 850,
    max_characters: int = 2400,
) -> tuple[list[str], dict[str, float | int]]:
    errors: list[str] = []
    content = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = content.splitlines()
    nonempty = [(index, line) for index, line in enumerate(lines) if line.strip()]
    if not nonempty:
        return ["报告不能为空"], {}

    h1s = [
        (index, match.group(1).strip())
        for index, line in enumerate(lines)
        if (match := re.match(r"^#\s+(.+?)\s*$", line))
    ]
    expected_title = SYSTEM_TITLES[system]
    if len(h1s) != 1:
        errors.append("报告必须恰好包含一个一级标题")
    elif h1s[0][1] != expected_title:
        errors.append(f"一级标题必须是：{expected_title}")
    if h1s and h1s[0][0] != nonempty[0][0]:
        errors.append("一级标题必须是报告第一行有效内容")

    h2_sections = heading_ranges(lines, 2)
    if h1s and h2_sections:
        between = lines[h1s[0][0] + 1 : h2_sections[0][1]]
        if any(line.strip() for line in between):
            errors.append("一级标题后不得放副标题、摘要、元数据或说明，应直接进入正文章节")
    if any(re.match(r"^#{4,}\s+", line) for line in lines):
        errors.append("报告不得使用四级或更深标题")

    schema = SYSTEM_SECTIONS[system]
    actual_h2 = [title for title, _, _ in h2_sections]
    expected_h2 = [*schema["foundation"]]
    optional_heading = schema["optional"]
    if optional_heading and optional_heading in actual_h2:
        expected_h2.append(optional_heading)
    expected_h2.append(schema["focus"])
    expected_h2.append(schema["closing"])
    if actual_h2 != expected_h2:
        errors.append(
            "二级章节必须按固定顺序出现：" + " → ".join(expected_h2)
        )

    all_headings = actual_h2 + [
        match.group(1).strip()
        for line in lines
        if (match := re.match(r"^###\s+(.+?)\s*$", line))
    ]
    for heading in all_headings:
        if FORBIDDEN_HEADING.search(heading):
            errors.append(f"用户可见标题不应出现内部过程或重复摘要：{heading}")

    for token in FORBIDDEN_METADATA:
        if token.lower() in content.lower():
            errors.append(f"报告泄露了后台字段或引擎元数据：{token}")
    policy_content = re.sub(
        r"(?m)^阶段参考日：\d{4}-\d{2}-\d{2}\s*$",
        "阶段参考日：<deterministic>",
        content,
    )
    for pattern in FORBIDDEN_BODY_PATTERNS:
        if match := pattern.search(policy_content):
            errors.append(f"报告包含越界、夸大或虚假精确表达：{match.group(0)}")
    for bold_text in BOLD_SPAN.findall(content):
        if match := GENERIC_VERDICTS.search(bold_text):
            errors.append(f"加粗判断是无辨识度套话：{match.group(0)}")
        if not 6 <= visible_length(bold_text) <= LAYOUT_LIMITS[layout]["highlight"]:
            errors.append(
                f"加粗重点应为 6—{LAYOUT_LIMITS[layout]['highlight']} 个可见字符，当前为 {visible_length(bold_text)}"
            )
    if RAW_LAYOUT_HTML.search(content):
        errors.append("Markdown 正文不得包含卡片或布局 HTML")
    if any(MARKDOWN_TABLE_RULE.match(line) for line in lines):
        errors.append("默认报告不得使用表格；证据与盘面字段应保留在后台")
    for index, line in enumerate(lines, start=1):
        if LABELED_INTERNAL_BLOCK.match(line):
            errors.append(f"第 {index} 行把内部验证项直接展示给了用户")

    paragraphs = prose_blocks(content)
    paragraph_lengths = [visible_length(block) for block in paragraphs]
    target = LAYOUT_LIMITS[layout]["target"]
    hard = LAYOUT_LIMITS[layout]["hard"]
    over_hard = [(index + 1, length) for index, length in enumerate(paragraph_lengths) if length > hard]
    for index, length in over_hard:
        errors.append(f"第 {index} 个正文段落有 {length} 个可见字符，超过 {layout} 版硬上限 {hard}")
    over_target = sum(length > target for length in paragraph_lengths)
    allowed_over_target = len(paragraphs) // 10
    if over_target > allowed_over_target:
        errors.append(f"{layout} 版有 {over_target} 段超过建议上限 {target} 字；当前段落数最多允许 {allowed_over_target} 段")

    highlight_locations: list[tuple[str, str]] = []
    for index, block in enumerate(paragraphs, start=1):
        spans = BOLD_SPAN.findall(block)
        if len(spans) > 1:
            errors.append(f"第 {index} 个正文段落包含多个加粗重点；每段最多一个")
        for span in spans:
            plain = re.sub(r"\*\*", "", block)
            if visible_length(plain) and visible_length(span) / visible_length(plain) > 0.45:
                errors.append(f"第 {index} 个正文段落加粗超过本段 45%，不要整段加粗")
            highlight_locations.append((block, span))
    start_highlights = sum(block.startswith("**") for block, _ in highlight_locations)
    start_ratio = start_highlights / len(highlight_locations) if highlight_locations else 0.0
    if len(highlight_locations) < 3:
        errors.append("正文至少需要 3 处真正有信息量的段内重点")
    if highlight_locations and start_ratio > 0.50:
        errors.append(f"有 {start_ratio:.0%} 的重点位于段首；不得超过 50%，应按内容价值在段内自然高亮")

    visible_body = "\n".join(paragraphs + [line for line in lines if re.match(r"^\s*\d+\.\s+", line)])
    total_chars = sum(
        visible_length("\n".join(lines[start + 1 : end]))
        for _, start, end in h2_sections
    )
    if total_chars < min_characters:
        errors.append(f"详细报告正文不足 {min_characters} 个可见字符")
    if total_chars > max_characters:
        errors.append(f"详细报告正文超过 {max_characters} 个可见字符")

    section_by_title = {title: (start, end) for title, start, end in h2_sections}
    reference_lines = [
        (index, line.strip())
        for index, line in enumerate(lines)
        if line.strip().startswith("阶段参考日：")
    ]
    if len(reference_lines) > 1:
        errors.append("阶段参考日只能出现一次")
    for index, line in reference_lines:
        if not re.fullmatch(r"阶段参考日：\d{4}-\d{2}-\d{2}", line):
            errors.append("阶段参考日必须使用 YYYY-MM-DD")
        else:
            try:
                datetime.strptime(line.removeprefix("阶段参考日："), "%Y-%m-%d")
            except ValueError:
                errors.append("阶段参考日不是有效日期")
        if optional_heading not in section_by_title:
            errors.append("阶段参考日只能出现在大运与阶段分析章节")
        else:
            start, end = section_by_title[optional_heading]
            if not start < index < end:
                errors.append("阶段参考日只能出现在大运与阶段分析章节")
    foundation_chars = 0
    for foundation_title in schema["foundation"]:
        if foundation_title not in section_by_title:
            continue
        start, end = section_by_title[foundation_title]
        body_start = start + 1
        foundation_chars += visible_length("\n".join(lines[body_start:end]))

    if len(schema["foundation"]) >= 2:
        overview_title = schema["foundation"][0]
        patterns_title = schema["foundation"][1]
        if overview_title in section_by_title:
            start, end = section_by_title[overview_title]
            overview_bold = BOLD_SPAN.findall("\n".join(lines[start + 1 : end]))
            if not 1 <= len(overview_bold) <= 2:
                errors.append(f"“{overview_title}”必须保留一至两个段内核心重点")
        if patterns_title in section_by_title:
            start, end = section_by_title[patterns_title]
            pattern_bold = BOLD_SPAN.findall("\n".join(lines[start + 1 : end]))
            if not 1 <= len(pattern_bold) <= 2:
                errors.append(f"“{patterns_title}”必须保留一至两个具体行为模式")

    overview_chars = 0
    if system == "bazi" and "整体解读" in section_by_title:
        start, end = section_by_title["整体解读"]
        overview_chars = visible_length("\n".join(lines[start + 1 : end]))
        if overview_chars > 280:
            errors.append("“整体解读”应控制在 280 个可见字符以内")
        if total_chars and overview_chars / total_chars > 0.18:
            errors.append("“整体解读”不得超过正文的 18%")
    foundation_ratio = foundation_chars / total_chars if total_chars else 0.0
    if total_chars and foundation_ratio > 0.40:
        errors.append("命理或星象底层章节合计不得超过正文的 40%")

    focus_chars = 0
    topic_highlights = 0
    focus_title = schema["focus"]
    if focus_title not in section_by_title:
        errors.append(f"缺少“{focus_title}”章节")
    else:
        focus_start, focus_end = section_by_title[focus_title]
        focus_chars = visible_length("\n".join(lines[focus_start + 1 : focus_end]))
        topic_sections = heading_ranges(lines, 3, focus_start + 1, focus_end)
        actual_topics = [title for title, _, _ in topic_sections]
        expected_topics = [TOPIC_HEADINGS[topic] for topic in topics]
        if actual_topics != expected_topics:
            errors.append(
                "关注主题必须作为三级章节按选择顺序出现："
                + " → ".join(expected_topics)
            )
        all_h3 = heading_ranges(lines, 3)
        outside_h3 = [
            title
            for title, start, _ in all_h3
            if not focus_start < start < focus_end
        ]
        if outside_h3:
            errors.append("三级标题只用于关注主题，不得出现在其他章节：" + "、".join(outside_h3))

        minimum_topic_chars = 340 if len(topics) == 1 else 260
        for title, start, end in topic_sections:
            body = "\n".join(lines[start + 1 : end])
            body_chars = visible_length(body)
            if body_chars < minimum_topic_chars:
                errors.append(f"“{title}”分析不足 {minimum_topic_chars} 个可见字符")
            bold_spans = BOLD_SPAN.findall(body)
            topic_highlights += len(bold_spans)
            minimum_highlights = 2 if len(topics) == 1 else 1
            maximum_highlights = 3 if len(topics) == 1 else 2
            if not minimum_highlights <= len(bold_spans) <= maximum_highlights:
                errors.append(f"“{title}”必须包含 {minimum_highlights}—{maximum_highlights} 个段内重点")

    topic_ratio = focus_chars / total_chars if total_chars else 0.0
    if topics and total_chars and topic_ratio < min_topic_ratio:
        errors.append(
            f"用户关注领域正文占比仅 {topic_ratio:.0%}，应至少达到 {min_topic_ratio:.0%}"
        )

    closing_title = schema["closing"]
    if closing_title in section_by_title:
        start, end = section_by_title[closing_title]
        closing_lines = lines[start + 1 : end]
        closing_chars = visible_length("\n".join(closing_lines))
        if closing_chars > 400:
            errors.append(f"“{closing_title}”超过 400 个可见字符，应只保留一至三条观察点或建议和一次免责声明")
        numbered = [line for line in closing_lines if re.match(r"^\s*\d+\.\s+", line)]
        if not 1 <= len(numbered) <= 3:
            errors.append(f"“{closing_title}”必须包含一至三条编号观察点或建议")

    if optional_heading and optional_heading in section_by_title:
        start, end = section_by_title[optional_heading]
        timing_chars = visible_length("\n".join(lines[start + 1 : end]))
        if timing_chars > 400:
            errors.append(f"“{optional_heading}”超过 400 个可见字符，应只解释一个最相关阶段")

    consultant_count = len(CONSULTANT_TERMS.findall(content))
    if consultant_count > 6:
        errors.append(
            f"正文出现 {consultant_count} 个咨询式抽象词，超过上限 6；应改成具体偏好、反应或取舍"
        )

    metrics: dict[str, float | int] = {
        "layout": layout,
        "visible_characters": total_chars,
        "section_count": len(h2_sections),
        "paragraph_count": len(paragraphs),
        "paragraphs_over_target": over_target,
        "highlight_count": len(highlight_locations),
        "highlight_at_start_ratio": round(start_ratio, 4),
        "overview_characters": overview_chars,
        "foundation_ratio": round(foundation_ratio, 4),
        "focus_ratio": round(topic_ratio, 4),
        "topic_highlights": topic_highlights,
        "consultant_term_count": consultant_count,
    }
    return errors, metrics


def atomic_write(path: Path, content: str) -> None:
    if path.exists():
        raise ValidationError(f"输出文件已存在：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content.rstrip() + "\n")
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a portable Markdown report.")
    parser.add_argument("report", type=Path)
    parser.add_argument("--system", choices=sorted(SYSTEM_TITLES), required=True)
    parser.add_argument("--topic", choices=sorted(TOPIC_HEADINGS), action="append", required=True)
    parser.add_argument("--layout", choices=sorted(LAYOUT_LIMITS), default="desktop")
    parser.add_argument("--min-topic-ratio", type=float)
    parser.add_argument("--min-characters", type=int)
    parser.add_argument("--max-characters", type=int, default=2400)
    parser.add_argument("--strict", action="store_true", help="把篇幅和排版建议也作为阻断错误；仅用于离线验证")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        topics = list(dict.fromkeys(args.topic))
        if not 1 <= len(topics) <= len(TOPIC_HEADINGS):
            raise ValidationError("--topic 必须包含至少一个且不超过全部可用主题")
        min_characters = args.min_characters if args.min_characters is not None else (850 if len(topics) == 1 else 1100)
        min_topic_ratio = args.min_topic_ratio if args.min_topic_ratio is not None else (0.50 if len(topics) == 1 else 0.60)
        if not 0 <= min_topic_ratio <= 1:
            raise ValidationError("--min-topic-ratio 必须在 0 与 1 之间")
        if min_characters < 0 or args.max_characters < min_characters:
            raise ValidationError("篇幅上下限无效")
        content = args.report.read_text(encoding="utf-8")
        diagnostics, metrics = validate_markdown(
            content,
            args.system,
            topics,
            args.layout,
            min_topic_ratio,
            min_characters,
            args.max_characters,
        )
        errors, warnings = split_diagnostics(diagnostics)
        if args.strict and warnings:
            errors.extend(warnings)
        if errors:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "error": "E_REPORT_MARKDOWN",
                        "details": errors,
                        "warnings": warnings,
                        "metrics": metrics,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 2
        atomic_write(args.output, content)
        print(
            json.dumps(
                {"ok": True, "output": str(args.output), "warnings": warnings, "metrics": metrics},
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "E_REPORT_MARKDOWN_RUNTIME",
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
