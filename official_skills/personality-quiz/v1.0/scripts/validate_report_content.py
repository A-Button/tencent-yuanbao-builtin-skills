#!/usr/bin/env python3
"""Validate short-paragraph report copy assembled from selected hypotheses."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bazi_dayun_facts import (
    EARTHLY_BRANCHES,
    GROWTH_OFFSETS,
    GROWTH_STAGES,
    HEAVENLY_STEMS,
    HIDDEN_ROLES,
    PILLAR_KEYS,
    UNAVAILABLE_REASONS,
)
from vendor.lunar_python.util import LunarUtil


TOPICS = {"career", "emotion", "family", "economy", "social", "talent", "spiritual", "study", "health"}
LAYOUT_LIMITS = {
    "desktop": {"target": 100, "hard": 130, "highlight": 36},
    "mobile": {"target": 70, "hard": 90, "highlight": 28},
}
GENERIC = re.compile(r"有机遇也有挑战|机遇与挑战并存|综合来看|总体而言|因人而异|扬长避短|保持平衡|顺其自然")
BANNED = re.compile(
    r"必然|注定|一定会|必定|百分百|一代传奇|开宗立派|商业帝国|财富滚滚|暴富|"
    r"确诊|患有|寿命|死亡时间|心脏|肝脏|肠胃|血压|癌症|疾病|"
    r"录取|考上|事业指数|情感指数|\d+\s*/\s*100|买入|卖出|加仓|减仓"
)
CONSULTANT_TERMS = re.compile(r"交付|复用|边界|闭环|抓手|赋能|方法论|关闭条件|价值兑现|资源配置")
MARKUP = re.compile(r"(?:^|\s)#{1,6}\s|\*\*|<\s*/?\s*(?:div|section|article)\b", re.I)
MARKDOWN_LINK_OR_IMAGE = re.compile(r"!?\[[^\]\r\n]*\]\s*\([^\)\r\n]*\)")
SENSITIVE_MODEL_TEXT = re.compile(
    r"\b(?:birth_date|birth_time|birth_place|birth_city|local_datetime|"
    r"lunar_datetime|timezone|gender_for_bazi|as_of_local_date|"
    r"option_a|option_b|forward|backward|male|female)\b|"
    r"chart\.(?:details|pillars|stable|possible)\b|"
    r"\b(?:19|20)\d{2}[-/.]\d{1,2}(?:[-/.]\d{1,2})?\b|"
    r"(?:19|20)\d{2}年\d{1,2}月(?:\d{1,2}日)?|"
    r"\b(?:19|20)\d{2}\b|"
    r"\b\d{1,2}:\d{2}(?::\d{2})?\b|"
    r"\b\d{1,2}时(?:\d{1,2}分)?",
    re.I,
)
CONDITIONAL_SELECTION = re.compile(
    r"(?:确定|认定|判定|选择|采用|应以|实际(?:是|为)|真正(?:是|为)|就是)"
    r".{0,12}(?:前者|后者|第一种|第二种|分支|口径|顺排|逆排)|"
    r"(?:前者|后者|第一种|第二种|分支|口径|顺排|逆排)"
    r".{0,12}(?:才是|更符合|为准|正确)",
)
CONDITIONAL_PRIVATE_LABEL = re.compile(
    r"顺排|逆排|顺行|逆行|男命|女命|乾造|坤造|男性|女性|男生|女生|性别|"
    r"\b(?:forward|backward|male|female)\b",
    re.I,
)
LUCK_CYCLE_STATUSES = {
    "available",
    "conditional",
    "unavailable",
    "excluded",
    "not_applicable",
}
DAYUN_FOCUS_PREFIX = "chart.details.luck_cycle_focus."
BRANCH_RELATION_TYPES = {
    "six_harmony",
    "six_clash",
    "six_harm",
    "break",
    "punishment",
    "self_punishment",
    "three_harmony",
    "three_meeting",
    "three_punishment",
}


class ValidationError(ValueError):
    pass


def resolve_path(payload: Any, path: str) -> bool:
    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            return False
    return True


def visible_length(value: str) -> int:
    return len(re.sub(r"\s+", "", value))


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValidationError(f"找不到文件：{path}") from exc
    except json.JSONDecodeError as exc:
        raise ValidationError(f"JSON 解析失败：{path} 第 {exc.lineno} 行第 {exc.colno} 列") from exc


def require_text(
    value: Any,
    field: str,
    errors: list[str],
    warnings: list[str],
    minimum: int,
    maximum: int,
    decisive: bool = False,
) -> str:
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{field} 必须是非空字符串")
        return ""
    text = value.strip()
    length = visible_length(text)
    if not minimum <= length <= maximum:
        warnings.append(f"{field} 建议为 {minimum}—{maximum} 个可见字符，当前为 {length}")
    if (
        "\n" in text
        or "\r" in text
        or "`" in text
        or MARKUP.search(text)
        or MARKDOWN_LINK_OR_IMAGE.search(text)
    ):
        errors.append(
            f"{field} 必须是单段纯文本，不得包含 Markdown 链接、图片、反引号代码或布局 HTML"
        )
    if match := BANNED.search(text):
        errors.append(f"{field} 包含越界、夸大或传记式表达：{match.group(0)}")
    if match := SENSITIVE_MODEL_TEXT.search(text):
        errors.append(f"{field} 泄露了身份、出生日期或内部大运字段：{match.group(0)}")
    if decisive:
        if match := GENERIC.search(text):
            warnings.append(f"{field} 可能是无辨识度套话：{match.group(0)}")
        if len(CONSULTANT_TERMS.findall(text)) >= 2:
            warnings.append(f"{field} 堆叠咨询式抽象词，建议改成可观察的偏好、反应或取舍")
    return text


def reject_extra(obj: dict[str, Any], allowed: set[str], field: str, errors: list[str]) -> None:
    extras = sorted(set(obj) - allowed)
    if extras:
        errors.append(f"{field} 包含未允许字段：{'、'.join(extras)}")


def _focus_from_chart(chart: Any) -> Any:
    if not isinstance(chart, dict):
        return None
    chart_payload = chart.get("chart")
    if not isinstance(chart_payload, dict):
        return None
    details = chart_payload.get("details")
    return details.get("luck_cycle_focus") if isinstance(details, dict) else None


def _natal_day_master(chart: Any) -> str | None:
    if not isinstance(chart, dict):
        return None
    details = chart.get("chart", {}).get("details", {})
    value = details.get("day_master", {}).get("stem") if isinstance(details, dict) else None
    return value if value in HEAVENLY_STEMS else None


def _exact_keys(value: dict[str, Any], keys: set[str], field: str, errors: list[str]) -> None:
    missing = sorted(keys - set(value))
    extras = sorted(set(value) - keys)
    if missing:
        errors.append(f"{field} 缺少字段：{'、'.join(missing)}")
    if extras:
        errors.append(f"{field} 包含未允许字段：{'、'.join(extras)}")


def _valid_gan_zhi(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 2
        and value[0] in HEAVENLY_STEMS
        and value[1] in EARTHLY_BRANCHES
        and HEAVENLY_STEMS.index(value[0]) % 2
        == EARTHLY_BRANCHES.index(value[1]) % 2
    )


def _expected_polarity(stem: str) -> str:
    return "yang" if HEAVENLY_STEMS.index(stem) % 2 == 0 else "yin"


def _expected_growth_stage(day_master: str, branch: str) -> str:
    branch_index = EARTHLY_BRANCHES.index(branch)
    day_master_index = HEAVENLY_STEMS.index(day_master)
    step = branch_index if day_master_index % 2 == 0 else -branch_index
    return GROWTH_STAGES[(GROWTH_OFFSETS[day_master] + step) % 12]


def _validate_stem_fact(
    value: Any,
    field: str,
    day_master: str,
    errors: list[str],
    *,
    role: str | None = None,
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{field} 必须是对象")
        return
    keys = (
        {"value", "element", "polarity", "ten_god"}
        if role is None
        else {"stem", "element", "polarity", "ten_god", "role"}
    )
    _exact_keys(value, keys, field, errors)
    stem = value.get("value") if role is None else value.get("stem")
    if stem not in HEAVENLY_STEMS:
        errors.append(f"{field} 天干无效")
        return
    if value.get("element") != LunarUtil.WU_XING_GAN.get(stem):
        errors.append(f"{field}.element 与天干不一致")
    if value.get("polarity") != _expected_polarity(stem):
        errors.append(f"{field}.polarity 与天干不一致")
    if value.get("ten_god") != LunarUtil.SHI_SHEN.get(day_master + stem):
        errors.append(f"{field}.ten_god 与日主、天干不一致")
    if role is not None and value.get("role") != role:
        errors.append(f"{field}.role 必须是 {role}")


def _validate_pillars(value: Any, field: str, errors: list[str]) -> None:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or item not in PILLAR_KEYS for item in value)
        or (all(isinstance(item, str) for item in value) and len(value) != len(set(value)))
    ):
        errors.append(f"{field} 必须是 1—4 个不重复原局柱位")


def _validate_relations(
    value: Any,
    field: str,
    cycle_stem: str,
    cycle_branch: str,
    errors: list[str],
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{field} 必须是对象")
        return
    _exact_keys(value, {"stems", "branches"}, field, errors)
    stems = value.get("stems")
    if not isinstance(stems, list):
        errors.append(f"{field}.stems 必须是数组")
    else:
        for index, relation in enumerate(stems):
            relation_field = f"{field}.stems.{index}"
            if not isinstance(relation, dict):
                errors.append(f"{relation_field} 必须是对象")
                continue
            _exact_keys(
                relation,
                {
                    "type",
                    "cycle_member",
                    "natal_member",
                    "natal_pillars",
                    "transformation_claimed",
                },
                relation_field,
                errors,
            )
            if relation.get("type") != "five_stem_combination":
                errors.append(f"{relation_field}.type 无效")
            if relation.get("cycle_member") != cycle_stem:
                errors.append(f"{relation_field}.cycle_member 与大运天干不一致")
            if relation.get("natal_member") not in HEAVENLY_STEMS:
                errors.append(f"{relation_field}.natal_member 无效")
            _validate_pillars(relation.get("natal_pillars"), f"{relation_field}.natal_pillars", errors)
            if relation.get("transformation_claimed") is not False:
                errors.append(f"{relation_field}.transformation_claimed 必须为 false")
    branches = value.get("branches")
    if not isinstance(branches, list):
        errors.append(f"{field}.branches 必须是数组")
    else:
        for index, relation in enumerate(branches):
            relation_field = f"{field}.branches.{index}"
            if not isinstance(relation, dict):
                errors.append(f"{relation_field} 必须是对象")
                continue
            _exact_keys(
                relation,
                {
                    "type",
                    "cycle_member",
                    "natal_members",
                    "natal_pillars",
                    "transformation_claimed",
                },
                relation_field,
                errors,
            )
            if relation.get("type") not in BRANCH_RELATION_TYPES:
                errors.append(f"{relation_field}.type 无效")
            if relation.get("cycle_member") != cycle_branch:
                errors.append(f"{relation_field}.cycle_member 与大运地支不一致")
            members = relation.get("natal_members")
            if (
                not isinstance(members, list)
                or not members
                or any(
                    not isinstance(member, str) or member not in EARTHLY_BRANCHES
                    for member in members
                )
                or (
                    all(isinstance(member, str) for member in members)
                    and len(members) != len(set(members))
                )
            ):
                errors.append(f"{relation_field}.natal_members 无效")
            _validate_pillars(relation.get("natal_pillars"), f"{relation_field}.natal_pillars", errors)
            if relation.get("transformation_claimed") is not False:
                errors.append(f"{relation_field}.transformation_claimed 必须为 false")


def _validate_cycle_fact(
    value: Any,
    field: str,
    day_master: str | None,
    errors: list[str],
) -> None:
    if not isinstance(value, dict):
        errors.append(f"{field} 必须是对象")
        return
    _exact_keys(
        value,
        {"index", "gan_zhi", "stem", "branch", "relations_to_natal"},
        field,
        errors,
    )
    index = value.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= 8:
        errors.append(f"{field}.index 必须是 1—8 的整数")
    gan_zhi = value.get("gan_zhi")
    if not _valid_gan_zhi(gan_zhi):
        errors.append(f"{field}.gan_zhi 必须是合法干支")
        return
    if day_master not in HEAVENLY_STEMS:
        errors.append("原局缺少可验证日主，不能校验大运事实")
        return
    stem, branch = gan_zhi
    _validate_stem_fact(value.get("stem"), f"{field}.stem", day_master, errors)
    if isinstance(value.get("stem"), dict) and value["stem"].get("value") != stem:
        errors.append(f"{field}.stem.value 与 gan_zhi 不一致")
    branch_fact = value.get("branch")
    if not isinstance(branch_fact, dict):
        errors.append(f"{field}.branch 必须是对象")
    else:
        _exact_keys(
            branch_fact,
            {"value", "element", "twelve_growth_stage", "hidden_stems"},
            f"{field}.branch",
            errors,
        )
        if branch_fact.get("value") != branch:
            errors.append(f"{field}.branch.value 与 gan_zhi 不一致")
        if branch_fact.get("element") != LunarUtil.WU_XING_ZHI.get(branch):
            errors.append(f"{field}.branch.element 与地支不一致")
        if branch_fact.get("twelve_growth_stage") != _expected_growth_stage(day_master, branch):
            errors.append(f"{field}.branch.twelve_growth_stage 与日主、地支不一致")
        hidden = branch_fact.get("hidden_stems")
        expected_hidden = LunarUtil.ZHI_HIDE_GAN.get(branch)
        if not isinstance(hidden, list) or not isinstance(expected_hidden, list) or len(hidden) != len(expected_hidden):
            errors.append(f"{field}.branch.hidden_stems 与地支藏干数量不一致")
        else:
            for hidden_index, (fact, expected_stem) in enumerate(zip(hidden, expected_hidden)):
                hidden_field = f"{field}.branch.hidden_stems.{hidden_index}"
                _validate_stem_fact(
                    fact,
                    hidden_field,
                    day_master,
                    errors,
                    role=HIDDEN_ROLES[hidden_index],
                )
                if isinstance(fact, dict) and fact.get("stem") != expected_stem:
                    errors.append(f"{hidden_field}.stem 与地支藏干不一致")
    _validate_relations(
        value.get("relations_to_natal"),
        f"{field}.relations_to_natal",
        stem,
        branch,
        errors,
    )


def _valid_focus_common(focus: dict[str, Any], errors: list[str]) -> bool:
    valid = True
    if focus.get("schema_version") != "1.0.0":
        errors.append("luck_cycle_focus.schema_version 必须是 1.0.0")
        valid = False
    date_value = focus.get("as_of_local_date")
    if not isinstance(date_value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date_value):
        errors.append("luck_cycle_focus.as_of_local_date 无效")
        valid = False
    else:
        try:
            datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError:
            errors.append("luck_cycle_focus.as_of_local_date 无效")
            valid = False
    if focus.get("selection_precision") != "local_datetime":
        errors.append("luck_cycle_focus.selection_precision 必须是 local_datetime")
        valid = False
    if focus.get("interval_policy") != "start_inclusive_end_exclusive":
        errors.append("luck_cycle_focus.interval_policy 无效")
        valid = False
    return valid


def validate_luck_cycle_context(
    context: Any,
    system: Any,
    chart: Any,
    errors: list[str],
) -> str:
    """Validate the deterministic pipeline envelope against the prepared chart."""
    if not isinstance(context, dict):
        errors.append("luck_cycle_context 必须是流水线注入的对象")
        return ""
    reject_extra(context, {"status", "reason"}, "luck_cycle_context", errors)
    status = context.get("status")
    if status not in LUCK_CYCLE_STATUSES:
        errors.append("luck_cycle_context.status 无效")
        return ""
    reason = context.get("reason")
    if status == "unavailable":
        if set(context) != {"status", "reason"}:
            errors.append("unavailable luck_cycle_context 必须只包含 status 与 reason")
        if reason not in UNAVAILABLE_REASONS:
            errors.append("luck_cycle_context.reason 不是允许的不可用原因")
    elif set(context) != {"status"}:
        errors.append(f"{status} luck_cycle_context 只能包含 status")

    focus = _focus_from_chart(chart)
    if system == "western":
        if status != "not_applicable":
            errors.append("西洋报告的 luck_cycle_context.status 必须是 not_applicable")
        return status
    if system == "bazi" and status == "not_applicable":
        errors.append("八字报告不得把大运标记为 not_applicable")
        return status
    if status in {"excluded"}:
        return status
    if not isinstance(focus, dict) or focus.get("status") != status:
        errors.append("luck_cycle_context 与盘面 luck_cycle_focus.status 不一致")
        return status

    if status == "unavailable":
        if set(focus) != {"schema_version", "status", "reason"}:
            errors.append("unavailable luck_cycle_focus 字段不符合确定性契约")
        if focus.get("schema_version") != "1.0.0":
            errors.append("luck_cycle_focus.schema_version 必须是 1.0.0")
        if focus.get("reason") != reason:
            errors.append("luck_cycle_context.reason 与盘面不可用原因不一致")
        return status

    common_keys = {
        "schema_version",
        "status",
        "as_of_local_date",
        "selection_precision",
        "interval_policy",
    }
    day_master = _natal_day_master(chart)
    if status == "available":
        if set(focus) != common_keys | {"position_band", "cycle"}:
            errors.append("available luck_cycle_focus 字段不符合确定性契约")
        _valid_focus_common(focus, errors)
        if focus.get("position_band") not in {
            "first_fifth",
            "middle_three_fifths",
            "final_fifth",
        }:
            errors.append("luck_cycle_focus.position_band 无效")
        _validate_cycle_fact(
            focus.get("cycle"), "luck_cycle_focus.cycle", day_master, errors
        )
    elif status == "conditional":
        if set(focus) != common_keys | {"branches"}:
            errors.append("conditional luck_cycle_focus 字段不符合确定性契约")
        _valid_focus_common(focus, errors)
        branches = focus.get("branches")
        if not isinstance(branches, list) or len(branches) != 2:
            errors.append("conditional luck_cycle_focus 必须恰好包含两个分支")
        else:
            if [branch.get("id") if isinstance(branch, dict) else None for branch in branches] != [
                "option_a",
                "option_b",
            ]:
                errors.append("conditional luck_cycle_focus 必须按 option_a、option_b 排列")
            for index, branch in enumerate(branches):
                if not isinstance(branch, dict):
                    errors.append(f"luck_cycle_focus.branches.{index} 必须是对象")
                    continue
                reject_extra(
                    branch,
                    {"id", "position_band", "cycle"},
                    f"luck_cycle_focus.branches.{index}",
                    errors,
                )
                if branch.get("position_band") not in {
                    "first_fifth",
                    "middle_three_fifths",
                    "final_fifth",
                }:
                    errors.append(f"luck_cycle_focus.branches.{index}.position_band 无效")
                _validate_cycle_fact(
                    branch.get("cycle"),
                    f"luck_cycle_focus.branches.{index}.cycle",
                    day_master,
                    errors,
                )
    return status


def _validate_signal_paths(
    value: Any,
    chart: dict[str, Any],
    status: str,
    errors: list[str],
) -> None:
    def derived_for(prefix: str, path: str) -> bool:
        return (
            path == prefix + "position_band"
            or path == prefix + "cycle.stem.ten_god"
            or path == prefix + "cycle.branch.twelve_growth_stage"
            or path.startswith(prefix + "cycle.branch.hidden_stems.")
            or path.startswith(prefix + "cycle.relations_to_natal.stems.")
            or path.startswith(prefix + "cycle.relations_to_natal.branches.")
        )

    if not isinstance(value, list) or not 2 <= len(value) <= 8:
        errors.append("timing.signal_paths 必须包含 2—8 条具体盘面路径")
        return
    paths: list[str] = []
    for index, item in enumerate(value):
        field = f"timing.signal_paths.{index}"
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{field} 必须是非空字符串")
            continue
        path = item.strip()
        if path in paths:
            errors.append(f"{field} 重复：{path}")
            continue
        paths.append(path)
        if not path.startswith("chart.") or path in {"chart", "chart.details"}:
            errors.append(f"{field} 不是具体盘面路径：{path}")
        elif not resolve_path(chart, path):
            errors.append(f"{field} 在盘面中不存在：{path}")

    natal_paths = [path for path in paths if path.startswith("chart.") and not path.startswith(DAYUN_FOCUS_PREFIX)]
    if not natal_paths:
        errors.append("timing.signal_paths 必须至少引用一条原局事实")
    if status == "available":
        dayun_paths = [
            path
            for path in paths
            if derived_for(DAYUN_FOCUS_PREFIX, path)
        ]
        if not dayun_paths:
            errors.append("available timing.signal_paths 必须引用当前大运派生事实")
    elif status == "conditional":
        option_paths = {
            option: [
                path
                for path in paths
                if derived_for(
                    DAYUN_FOCUS_PREFIX + f"branches.{index}.", path
                )
            ]
            for index, option in enumerate(("option_a", "option_b"))
        }
        for option, branch_paths in option_paths.items():
            if not branch_paths:
                errors.append(f"conditional timing.signal_paths 必须覆盖 {option} 分支")


def validate_paragraph(
    value: Any,
    field: str,
    errors: list[str],
    warnings: list[str],
    limits: dict[str, int],
) -> tuple[str, list[str]]:
    if not isinstance(value, dict):
        errors.append(f"{field} 必须是包含 text 与 highlights 的对象")
        return "", []
    reject_extra(value, {"text", "highlights"}, field, errors)
    text = require_text(value.get("text"), f"{field}.text", errors, warnings, 24, limits["hard"])
    highlights = value.get("highlights")
    if not isinstance(highlights, list) or len(highlights) > 1:
        errors.append(f"{field}.highlights 必须是零至一个短语的数组")
        return text, []
    checked: list[str] = []
    for index, highlight in enumerate(highlights):
        highlight_text = require_text(highlight, f"{field}.highlights.{index}", errors, warnings, 6, limits["highlight"], decisive=True)
        if not highlight_text:
            continue
        occurrences = text.count(highlight_text)
        if occurrences != 1:
            errors.append(f"{field}.highlights.{index} 必须在 text 中恰好出现一次，当前为 {occurrences} 次")
        text_length = visible_length(text)
        if text_length and visible_length(highlight_text) / text_length > 0.45:
            warnings.append(f"{field}.highlights.{index} 超过本段的 45%，建议缩短重点")
        checked.append(highlight_text)
    return text, checked


def validate_paragraph_list(
    value: Any,
    field: str,
    errors: list[str],
    warnings: list[str],
    limits: dict[str, int],
    minimum_count: int,
    maximum_count: int,
) -> list[tuple[str, list[str]]]:
    if not isinstance(value, list):
        errors.append(f"{field} 必须是短段落数组")
        return []
    if not minimum_count <= len(value) <= maximum_count:
        warnings.append(f"{field} 建议包含 {minimum_count}—{maximum_count} 个短段落，当前为 {len(value)} 个")
    paragraphs = [validate_paragraph(item, f"{field}.{index}", errors, warnings, limits) for index, item in enumerate(value)]
    if paragraphs and not any(highlights for _, highlights in paragraphs):
        warnings.append(f"{field} 没有段内重点；可保留，但视觉层次会较弱")
    return paragraphs


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    if path.exists():
        raise ValidationError(f"输出文件已存在：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def validate(payload: Any, chart: Any, hypotheses: Any, expected_topics: list[str], layout: str) -> tuple[list[str], list[str], dict[str, Any]]:
    errors: list[str] = []
    warnings: list[str] = []
    limits = LAYOUT_LIMITS[layout]
    if not isinstance(payload, dict) or not isinstance(chart, dict) or not isinstance(hypotheses, dict):
        return ["判断稿、盘面和候选假设顶层都必须是对象"], [], {}
    if hypotheses.get("validation", {}).get("status") != "pass":
        errors.append("--hypotheses 必须是通过 validate_report_hypotheses.py 的文件")
    reject_extra(
        payload,
        {
            "schema_version",
            "chart_system",
            "primary_topics",
            "luck_cycle_context",
            "overview",
            "insights",
            "timing",
            "takeaways",
        },
        "report-content",
        errors,
    )
    if payload.get("schema_version") != "4.0.0":
        errors.append("schema_version 必须是 4.0.0")
    system = payload.get("chart_system")
    if system not in {"bazi", "western"} or system != chart.get("chart_system") or system != hypotheses.get("chart_system"):
        errors.append("判断稿、盘面与候选假设的 chart_system 必须一致")
    luck_cycle_status = validate_luck_cycle_context(
        payload.get("luck_cycle_context"), system, chart, errors
    )
    if payload.get("primary_topics") != expected_topics or hypotheses.get("primary_topics") != expected_topics:
        errors.append(f"primary_topics 必须与命令行主题及顺序一致：{expected_topics}")
    selected_ids = hypotheses.get("selected_ids", [])
    candidate_map = {item.get("id"): item for item in hypotheses.get("candidates", []) if isinstance(item, dict) and item.get("id") in selected_ids}
    all_paragraphs: list[tuple[str, list[str]]] = []
    topic_chars: dict[str, int] = {topic: 0 for topic in expected_topics}
    personality_chars = 0

    overview = payload.get("overview")
    if not isinstance(overview, dict):
        errors.append("overview 必须是对象")
        overview = {}
    else:
        reject_extra(overview, {"paragraphs", "hypothesis_ids"}, "overview", errors)
    overview_paragraphs = validate_paragraph_list(overview.get("paragraphs"), "overview.paragraphs", errors, warnings, limits, 1, 2)
    all_paragraphs.extend(overview_paragraphs)
    overview_ids = overview.get("hypothesis_ids")
    if not isinstance(overview_ids, list) or not 1 <= len(overview_ids) <= 3 or len(overview_ids) != len(set(overview_ids)):
        errors.append("overview.hypothesis_ids 必须引用 1—3 个不重复入选候选")
    else:
        for candidate_id in overview_ids:
            if candidate_id not in candidate_map:
                errors.append(f"overview 引用了未入选候选：{candidate_id}")

    insights = payload.get("insights")
    if not isinstance(insights, list):
        errors.append("insights 必须是最终判断数组")
        insights = []
    else:
        expected_min = 3 if len(expected_topics) <= 2 else len(expected_topics) + 1
        expected_max = 5 if len(expected_topics) <= 2 else len(expected_topics) + 1
        if not expected_min <= len(insights) <= expected_max:
            if expected_min == expected_max:
                warnings.append(f"insights 建议包含 {expected_min} 条最终判断，当前为 {len(insights)} 条")
            else:
                warnings.append(f"insights 建议包含 {expected_min}—{expected_max} 条最终判断，当前为 {len(insights)} 条")
    actual_ids: list[str] = []
    actual_topics: list[str] = []
    for index, insight in enumerate(insights):
        field = f"insights.{index}"
        if not isinstance(insight, dict):
            errors.append(f"{field} 必须是对象")
            continue
        reject_extra(insight, {"hypothesis_id", "topic", "paragraphs"}, field, errors)
        candidate_id = insight.get("hypothesis_id")
        candidate = candidate_map.get(candidate_id)
        if not candidate:
            errors.append(f"{field}.hypothesis_id 必须引用入选候选")
            continue
        actual_ids.append(candidate_id)
        topic = insight.get("topic")
        actual_topics.append(str(topic))
        if topic != candidate.get("topic"):
            errors.append(f"{field}.topic 与候选 {candidate_id} 不一致")
        paragraphs = validate_paragraph_list(insight.get("paragraphs"), f"{field}.paragraphs", errors, warnings, limits, 1, 3)
        all_paragraphs.extend(paragraphs)
        chars = sum(visible_length(text) for text, _ in paragraphs)
        if topic == "personality":
            personality_chars += chars
        elif topic in topic_chars:
            topic_chars[topic] += chars

    if actual_ids != selected_ids:
        errors.append("insights 必须按 selected_ids 顺序逐项使用全部入选候选")
    if len(actual_ids) != len(set(actual_ids)):
        errors.append("insights 不得重复使用同一候选")
    personality_count = actual_topics.count("personality")
    if len(expected_topics) == 1:
        if personality_count not in {1, 2}:
            warnings.append("单主题报告的性格章节建议包含 1—2 条入选判断")
        if not 2 <= actual_topics.count(expected_topics[0]) <= 3:
            warnings.append(f"单主题报告的 {expected_topics[0]} 建议包含 2—3 条入选判断")
    elif len(expected_topics) == 2:
        if personality_count != 1:
            warnings.append("双主题报告的性格章节建议只保留 1 条最相关判断")
        for topic in expected_topics:
            if not 1 <= actual_topics.count(topic) <= 2:
                warnings.append(f"双主题报告的 {topic} 建议包含 1—2 条入选判断")
    else:
        if personality_count != 1:
            warnings.append("多主题报告的性格章节建议只保留 1 条最相关判断")
        for topic in expected_topics:
            if actual_topics.count(topic) != 1:
                warnings.append(f"多主题报告的 {topic} 建议包含 1 条入选判断")

    timing = payload.get("timing")
    timing_chars = 0
    if luck_cycle_status in {"available", "conditional"} and timing is None:
        errors.append(f"八字报告在 {luck_cycle_status} 大运状态下必须包含 timing")
    if luck_cycle_status in {"unavailable", "excluded", "not_applicable"} and timing is not None:
        errors.append(f"{luck_cycle_status} 大运状态下不得包含 timing")
    if timing is not None:
        if system != "bazi":
            errors.append("当前西洋报告不得包含 timing")
        if not isinstance(timing, dict):
            errors.append("timing 必须是对象")
        else:
            reject_extra(timing, {"paragraphs", "signal_paths"}, "timing", errors)
            timing_values = timing.get("paragraphs")
            if not isinstance(timing_values, list) or not 1 <= len(timing_values) <= 3:
                errors.append("timing.paragraphs 必须包含 1—3 个短段落")
            timing_paragraphs = validate_paragraph_list(
                timing_values,
                "timing.paragraphs",
                errors,
                warnings,
                limits,
                1,
                3,
            )
            all_paragraphs.extend(timing_paragraphs)
            timing_chars = sum(visible_length(text) for text, _ in timing_paragraphs)
            _validate_signal_paths(
                timing.get("signal_paths"), chart, luck_cycle_status, errors
            )
            if luck_cycle_status == "conditional":
                for index, (text, _) in enumerate(timing_paragraphs):
                    if match := CONDITIONAL_PRIVATE_LABEL.search(text):
                        errors.append(
                            f"timing.paragraphs.{index}.text 不得泄露顺逆或性别标签：{match.group(0)}"
                        )
                    if match := CONDITIONAL_SELECTION.search(text):
                        errors.append(
                            f"timing.paragraphs.{index}.text 不得替用户选择条件分支：{match.group(0)}"
                        )

    takeaways = payload.get("takeaways")
    if not isinstance(takeaways, list):
        errors.append("takeaways 必须是观察点或建议数组")
        takeaways = []
    elif not 1 <= len(takeaways) <= 3:
        warnings.append(f"takeaways 建议包含 1—3 条观察点或建议，当前为 {len(takeaways)} 条")
    takeaway_chars = 0
    user_texts: list[str] = [text for text, _ in all_paragraphs]
    for index, takeaway in enumerate(takeaways):
        text = require_text(takeaway, f"takeaways.{index}", errors, warnings, 18, limits["target"])
        takeaway_chars += visible_length(text)
        user_texts.append(text)

    paragraph_lengths = [visible_length(text) for text, _ in all_paragraphs]
    over_target = sum(length > limits["target"] for length in paragraph_lengths)
    allowed_over_target = len(paragraph_lengths) // 10
    if over_target > allowed_over_target:
        warnings.append(f"{layout} 版有 {over_target} 段超过建议上限 {limits['target']} 字；本地检查不阻断渲染")
    highlights = [(text, highlight) for text, items in all_paragraphs for highlight in items]
    if len(highlights) < 3:
        warnings.append("正文少于 3 处段内重点；本地检查不阻断渲染")
    start_highlights = sum(text.startswith(highlight) for text, highlight in highlights)
    start_ratio = start_highlights / len(highlights) if highlights else 0.0
    if highlights and start_ratio > 0.50:
        warnings.append(f"有 {start_ratio:.0%} 的重点位于段首；建议分散重点位置")

    visible_user_text = "\n".join(user_texts)
    overview_chars = sum(visible_length(text) for text, _ in overview_paragraphs)
    estimated_total = overview_chars + personality_chars + sum(topic_chars.values()) + timing_chars + takeaway_chars + 68
    minimum_total = 850 if len(expected_topics) == 1 else 1100
    if estimated_total < minimum_total:
        warnings.append(f"判断稿有效正文约 {estimated_total} 字，低于建议值 {minimum_total} 字")
    if estimated_total > 2200:
        warnings.append(f"判断稿有效正文约 {estimated_total} 字，超过建议值 2200 字")
    focus_chars = sum(topic_chars.values())
    focus_ratio = focus_chars / estimated_total if estimated_total else 0.0
    foundation_ratio = (overview_chars + personality_chars) / estimated_total if estimated_total else 0.0
    minimum_focus_ratio = 0.50 if len(expected_topics) == 1 else 0.60
    if focus_ratio < minimum_focus_ratio:
        warnings.append(f"关注主题占比为 {focus_ratio:.0%}，建议不低于 {minimum_focus_ratio:.0%}")
    if foundation_ratio > 0.40:
        warnings.append(f"总论与性格占比为 {foundation_ratio:.0%}，建议不超过 40%")
    minimum_topic = 340 if len(expected_topics) == 1 else 260
    for topic, count in topic_chars.items():
        if count < minimum_topic:
            warnings.append(f"主题 {topic} 只有 {count} 个可见字符，建议至少 {minimum_topic}")
    consultant_count = len(CONSULTANT_TERMS.findall(visible_user_text))
    if consultant_count > 6:
        warnings.append(f"判断稿出现 {consultant_count} 个咨询式抽象词，建议换成具体偏好、反应或取舍")

    metrics = {
        "layout": layout, "selected_ids": actual_ids,
        "insight_count": len(insights), "paragraph_count": len(all_paragraphs),
        "paragraphs_over_target": over_target, "highlight_count": len(highlights),
        "highlight_at_start_ratio": round(start_ratio, 4), "takeaway_count": len(takeaways),
        "estimated_characters": estimated_total, "foundation_ratio": round(foundation_ratio, 4),
        "focus_ratio": round(focus_ratio, 4), "topic_characters": topic_chars,
        "consultant_term_count": consultant_count,
    }
    return errors, warnings, metrics


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate short-paragraph report copy assembled from selected hypotheses.")
    parser.add_argument("content", type=Path)
    parser.add_argument("--chart", required=True, type=Path)
    parser.add_argument("--hypotheses", required=True, type=Path)
    parser.add_argument("--topic", choices=sorted(TOPICS), action="append", required=True)
    parser.add_argument("--layout", choices=sorted(LAYOUT_LIMITS), default="desktop")
    parser.add_argument("--strict", action="store_true", help="把文风、篇幅和排版建议也作为阻断错误；仅用于离线验证")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        topics = list(dict.fromkeys(args.topic))
        if not 1 <= len(topics) <= len(TOPICS - {"personality"}):
            raise ValidationError("--topic 必须包含至少一个且不超过全部可用主题")
        content = load_json(args.content)
        chart = load_json(args.chart)
        hypotheses = load_json(args.hypotheses)
        errors, warnings, metrics = validate(content, chart, hypotheses, topics, args.layout)
        if args.strict and warnings:
            errors.extend(warnings)
        if errors:
            print(json.dumps({"ok": False, "error": "E_REPORT_CONTENT", "details": errors, "warnings": warnings, "metrics": metrics}, ensure_ascii=False, indent=2))
            return 2
        validation = {
            "status": "pass",
            "validated_at": datetime.now(timezone.utc).isoformat(),
            "analysis_mode": chart.get("analysis_mode"),
            "layout": args.layout,
            "hypothesis_ids": hypotheses.get("selected_ids", []),
            "warnings": warnings,
        }
        focus = _focus_from_chart(chart)
        if (
            content.get("luck_cycle_context", {}).get("status")
            in {"available", "conditional"}
            and isinstance(focus, dict)
        ):
            validation["luck_cycle_reference_date"] = focus["as_of_local_date"]
        validated = {**content, "validation": validation}
        atomic_write(args.output, validated)
        print(json.dumps({"ok": True, "output": str(args.output), "warnings": warnings, "metrics": metrics}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps({"ok": False, "error": "E_REPORT_CONTENT_RUNTIME", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
