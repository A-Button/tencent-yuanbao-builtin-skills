#!/usr/bin/env python3
"""Project identity-minimized, deterministic Dayun facts for Bazi reports.

This module deliberately has no file or clock access.  The caller resolves the
report moment to the chart's local civil time and passes it as a naive
``datetime``.  Only the report pipeline should call this projector; ordinary
chart generation does not need to import it.
"""

from __future__ import annotations

import calendar
import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from vendor.lunar_python.util import LunarUtil


SCHEMA_VERSION = "1.0.0"
CALCULATION_METHOD = "lunar-python-yun-sect-1"
PILLAR_KEYS = ("year", "month", "day", "hour")
HIDDEN_ROLES = ("main", "secondary", "residual")
HEAVENLY_STEMS = "甲乙丙丁戊己庚辛壬癸"
EARTHLY_BRANCHES = "子丑寅卯辰巳午未申酉戌亥"

UNAVAILABLE_REASONS = frozenset(
    {
        "date_only",
        "time_range",
        "invalid_chart",
        "invalid_focus_moment",
        "unsupported_time_basis",
        "missing_luck_cycles",
        "incomplete_conditional_cycles",
        "invalid_luck_cycles",
        "no_current_cycle",
    }
)

STEM_COMBINATIONS = {
    frozenset(pair)
    for pair in (
        ("甲", "己"),
        ("乙", "庚"),
        ("丙", "辛"),
        ("丁", "壬"),
        ("戊", "癸"),
    )
}
BRANCH_PAIR_RELATIONS = {
    "six_harmony": {
        frozenset(pair)
        for pair in (
            ("子", "丑"),
            ("寅", "亥"),
            ("卯", "戌"),
            ("辰", "酉"),
            ("巳", "申"),
            ("午", "未"),
        )
    },
    "six_clash": {
        frozenset(pair)
        for pair in (
            ("子", "午"),
            ("丑", "未"),
            ("寅", "申"),
            ("卯", "酉"),
            ("辰", "戌"),
            ("巳", "亥"),
        )
    },
    "six_harm": {
        frozenset(pair)
        for pair in (
            ("子", "未"),
            ("丑", "午"),
            ("寅", "巳"),
            ("卯", "辰"),
            ("申", "亥"),
            ("酉", "戌"),
        )
    },
    "break": {
        frozenset(pair)
        for pair in (
            ("子", "酉"),
            ("丑", "辰"),
            ("寅", "亥"),
            ("卯", "午"),
            ("巳", "申"),
            ("未", "戌"),
        )
    },
    "punishment": {frozenset(("子", "卯"))},
}
THREE_BRANCH_RELATIONS = {
    "three_harmony": (
        frozenset(("申", "子", "辰")),
        frozenset(("亥", "卯", "未")),
        frozenset(("寅", "午", "戌")),
        frozenset(("巳", "酉", "丑")),
    ),
    "three_meeting": (
        frozenset(("亥", "子", "丑")),
        frozenset(("寅", "卯", "辰")),
        frozenset(("巳", "午", "未")),
        frozenset(("申", "酉", "戌")),
    ),
    "three_punishment": (
        frozenset(("寅", "巳", "申")),
        frozenset(("丑", "戌", "未")),
    ),
}
SELF_PUNISHMENT_BRANCHES = {"辰", "午", "酉", "亥"}

GROWTH_STAGES = (
    "长生",
    "沐浴",
    "冠带",
    "临官",
    "帝旺",
    "衰",
    "病",
    "死",
    "墓",
    "绝",
    "胎",
    "养",
)
GROWTH_OFFSETS = {
    "甲": 1,
    "丙": 10,
    "戊": 10,
    "庚": 7,
    "壬": 4,
    "乙": 6,
    "丁": 9,
    "己": 9,
    "辛": 0,
    "癸": 3,
}


class _ProjectionError(ValueError):
    def __init__(self, reason: str):
        if reason not in UNAVAILABLE_REASONS:
            raise ValueError(f"unknown unavailable reason: {reason}")
        super().__init__(reason)
        self.reason = reason


def _unavailable(reason: str) -> dict[str, Any]:
    if reason not in UNAVAILABLE_REASONS:
        raise ValueError(f"unknown unavailable reason: {reason}")
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "unavailable",
        "reason": reason,
    }


def _valid_gan_zhi(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 2
        and value[0] in HEAVENLY_STEMS
        and value[1] in EARTHLY_BRANCHES
        and HEAVENLY_STEMS.index(value[0]) % 2
        == EARTHLY_BRANCHES.index(value[1]) % 2
    )


def _add_years(value: datetime, years: int) -> datetime:
    target_year = value.year + years
    target_day = min(value.day, calendar.monthrange(target_year, value.month)[1])
    return value.replace(year=target_year, day=target_day)


def _polarity(stem: str) -> str:
    return "yang" if HEAVENLY_STEMS.index(stem) % 2 == 0 else "yin"


def _growth_stage(day_master: str, branch: str) -> str:
    branch_index = EARTHLY_BRANCHES.index(branch)
    day_master_index = HEAVENLY_STEMS.index(day_master)
    step = branch_index if day_master_index % 2 == 0 else -branch_index
    return GROWTH_STAGES[(GROWTH_OFFSETS[day_master] + step) % 12]


def _stem_fact(day_master: str, stem: str) -> dict[str, str]:
    element = LunarUtil.WU_XING_GAN.get(stem)
    ten_god = LunarUtil.SHI_SHEN.get(day_master + stem)
    if element is None or ten_god is None:
        raise _ProjectionError("invalid_chart")
    return {
        "value": stem,
        "element": element,
        "polarity": _polarity(stem),
        "ten_god": ten_god,
    }


def _branch_fact(day_master: str, branch: str) -> dict[str, Any]:
    element = LunarUtil.WU_XING_ZHI.get(branch)
    hidden = LunarUtil.ZHI_HIDE_GAN.get(branch)
    if element is None or not isinstance(hidden, list) or not 1 <= len(hidden) <= 3:
        raise _ProjectionError("invalid_chart")
    hidden_stems = []
    for index, stem in enumerate(hidden):
        fact = _stem_fact(day_master, stem)
        hidden_stems.append(
            {
                "stem": fact["value"],
                "element": fact["element"],
                "polarity": fact["polarity"],
                "ten_god": fact["ten_god"],
                "role": HIDDEN_ROLES[index],
            }
        )
    return {
        "value": branch,
        "element": element,
        "twelve_growth_stage": _growth_stage(day_master, branch),
        "hidden_stems": hidden_stems,
    }


def _natal_facts(chart: Mapping[str, Any]) -> tuple[str, dict[str, str], dict[str, str]]:
    details = chart.get("details")
    if not isinstance(details, Mapping):
        raise _ProjectionError("invalid_chart")
    day_master_data = details.get("day_master")
    stems = details.get("heavenly_stems")
    branches = details.get("earthly_branches")
    day_master = day_master_data.get("stem") if isinstance(day_master_data, Mapping) else None
    if day_master not in HEAVENLY_STEMS:
        raise _ProjectionError("invalid_chart")
    if not isinstance(stems, Mapping) or not isinstance(branches, Mapping):
        raise _ProjectionError("invalid_chart")
    checked_stems: dict[str, str] = {}
    checked_branches: dict[str, str] = {}
    for pillar in PILLAR_KEYS:
        stem = stems.get(pillar)
        branch = branches.get(pillar)
        if stem not in HEAVENLY_STEMS or branch not in EARTHLY_BRANCHES:
            raise _ProjectionError("invalid_chart")
        checked_stems[pillar] = stem
        checked_branches[pillar] = branch
    return day_master, checked_stems, checked_branches


def _stem_relations(cycle_stem: str, natal_stems: Mapping[str, str]) -> list[dict[str, Any]]:
    grouped: dict[str, list[str]] = {}
    for pillar in PILLAR_KEYS:
        natal_stem = natal_stems[pillar]
        if frozenset((cycle_stem, natal_stem)) in STEM_COMBINATIONS:
            grouped.setdefault(natal_stem, []).append(pillar)
    return [
        {
            "type": "five_stem_combination",
            "cycle_member": cycle_stem,
            "natal_member": natal_stem,
            "natal_pillars": pillars,
            "transformation_claimed": False,
        }
        for natal_stem, pillars in grouped.items()
    ]


def _branch_relations(
    cycle_branch: str, natal_branches: Mapping[str, str]
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for relation_type, relation_pairs in BRANCH_PAIR_RELATIONS.items():
        grouped: dict[str, list[str]] = {}
        for pillar in PILLAR_KEYS:
            natal_branch = natal_branches[pillar]
            if frozenset((cycle_branch, natal_branch)) in relation_pairs:
                grouped.setdefault(natal_branch, []).append(pillar)
        for natal_branch, pillars in grouped.items():
            result.append(
                {
                    "type": relation_type,
                    "cycle_member": cycle_branch,
                    "natal_members": [natal_branch],
                    "natal_pillars": pillars,
                    "transformation_claimed": False,
                }
            )

    if cycle_branch in SELF_PUNISHMENT_BRANCHES:
        pillars = [
            pillar
            for pillar in PILLAR_KEYS
            if natal_branches[pillar] == cycle_branch
        ]
        if pillars:
            result.append(
                {
                    "type": "self_punishment",
                    "cycle_member": cycle_branch,
                    "natal_members": [cycle_branch],
                    "natal_pillars": pillars,
                    "transformation_claimed": False,
                }
            )

    present = set(natal_branches.values()) | {cycle_branch}
    for relation_type, groups in THREE_BRANCH_RELATIONS.items():
        for group in groups:
            if cycle_branch not in group or not group.issubset(present):
                continue
            pillars = [
                pillar
                for pillar in PILLAR_KEYS
                if natal_branches[pillar] in group
            ]
            natal_members = sorted(
                {natal_branches[pillar] for pillar in pillars},
                key=EARTHLY_BRANCHES.index,
            )
            result.append(
                {
                    "type": relation_type,
                    "cycle_member": cycle_branch,
                    "natal_members": natal_members,
                    "natal_pillars": pillars,
                    "transformation_claimed": False,
                }
            )
    return result


def _parse_first_start(luck_cycles: Mapping[str, Any]) -> datetime:
    value = luck_cycles.get("start_solar_datetime")
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value
    ):
        raise _ProjectionError("invalid_luck_cycles")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError as exc:
        raise _ProjectionError("invalid_luck_cycles") from exc
    if parsed.tzinfo is not None:
        raise _ProjectionError("invalid_luck_cycles")
    return parsed


def _select_cycle(
    luck_cycles: Mapping[str, Any], focus_moment: datetime
) -> tuple[dict[str, Any], datetime, datetime]:
    if luck_cycles.get("calculation_method") != CALCULATION_METHOD:
        raise _ProjectionError("invalid_luck_cycles")
    if luck_cycles.get("direction") not in {"forward", "backward"}:
        raise _ProjectionError("invalid_luck_cycles")
    first_start = _parse_first_start(luck_cycles)
    cycles = luck_cycles.get("cycles")
    if not isinstance(cycles, list) or len(cycles) != 8:
        raise _ProjectionError("invalid_luck_cycles")

    selected: tuple[dict[str, Any], datetime, datetime] | None = None
    seen_indices: set[int] = set()
    for item in cycles:
        if not isinstance(item, Mapping):
            raise _ProjectionError("invalid_luck_cycles")
        index = item.get("index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 1 <= index <= 8
            or index in seen_indices
            or not _valid_gan_zhi(item.get("gan_zhi"))
        ):
            raise _ProjectionError("invalid_luck_cycles")
        seen_indices.add(index)
        start = _add_years(first_start, 10 * (index - 1))
        end = _add_years(first_start, 10 * index)
        start_year = item.get("start_year")
        end_year = item.get("end_year")
        if (
            isinstance(start_year, bool)
            or isinstance(end_year, bool)
            or not isinstance(start_year, int)
            or not isinstance(end_year, int)
            or start_year != start.year
            or end_year != end.year - 1
        ):
            raise _ProjectionError("invalid_luck_cycles")
        if start <= focus_moment < end:
            if selected is not None:
                raise _ProjectionError("invalid_luck_cycles")
            selected = (dict(item), start, end)
    if seen_indices != set(range(1, 9)):
        raise _ProjectionError("invalid_luck_cycles")
    if selected is None:
        raise _ProjectionError("no_current_cycle")
    return selected


def _position_band(focus_moment: datetime, start: datetime, end: datetime) -> str:
    progress = (focus_moment - start).total_seconds() / (end - start).total_seconds()
    if progress < 0.20:
        return "first_fifth"
    if progress < 0.80:
        return "middle_three_fifths"
    return "final_fifth"


def _enhanced_cycle(
    selected: tuple[dict[str, Any], datetime, datetime],
    focus_moment: datetime,
    day_master: str,
    natal_stems: Mapping[str, str],
    natal_branches: Mapping[str, str],
) -> dict[str, Any]:
    item, start, end = selected
    gan_zhi = item["gan_zhi"]
    cycle_stem, cycle_branch = gan_zhi
    return {
        "position_band": _position_band(focus_moment, start, end),
        "cycle": {
            "index": item["index"],
            "gan_zhi": gan_zhi,
            "stem": _stem_fact(day_master, cycle_stem),
            "branch": _branch_fact(day_master, cycle_branch),
            "relations_to_natal": {
                "stems": _stem_relations(cycle_stem, natal_stems),
                "branches": _branch_relations(cycle_branch, natal_branches),
            },
        },
    }


def project_dayun_facts(
    chart: Mapping[str, Any],
    focus_moment: datetime,
    *,
    conditional_luck_cycles: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return a safe current-Dayun projection for a report.

    ``focus_moment`` must be a naive local civil datetime resolved by the
    caller.  If the chart already has ``details.luck_cycles``, that selected
    calculation is authoritative.  Otherwise callers may supply exactly two
    raw alternatives under ``forward`` and ``backward``; the output deliberately
    renames them ``option_a`` and ``option_b`` so it carries no direction basis.

    The function never raises for chart-data or projection failures.  Such
    failures return ``status=unavailable`` with an allowlisted reason code.
    """

    if not isinstance(chart, Mapping):
        return _unavailable("invalid_chart")
    if chart.get("precision") == "date-only":
        return _unavailable("date_only")
    if chart.get("precision") == "time-range":
        return _unavailable("time_range")
    if (
        not isinstance(focus_moment, datetime)
        or focus_moment.tzinfo is not None
    ):
        return _unavailable("invalid_focus_moment")

    try:
        day_master, natal_stems, natal_branches = _natal_facts(chart)
        details = chart.get("details")
        assert isinstance(details, Mapping)
        embedded = details.get("luck_cycles")
        common = {
            "schema_version": SCHEMA_VERSION,
            "as_of_local_date": focus_moment.date().isoformat(),
            "selection_precision": "local_datetime",
            "interval_policy": "start_inclusive_end_exclusive",
        }
        if embedded is not None:
            if not isinstance(embedded, Mapping):
                raise _ProjectionError("invalid_luck_cycles")
            selected = _select_cycle(embedded, focus_moment)
            return {
                **common,
                "status": "available",
                **_enhanced_cycle(
                    selected,
                    focus_moment,
                    day_master,
                    natal_stems,
                    natal_branches,
                ),
            }

        if conditional_luck_cycles is None:
            return _unavailable("missing_luck_cycles")
        if (
            not isinstance(conditional_luck_cycles, Mapping)
            or set(conditional_luck_cycles) != {"forward", "backward"}
            or not all(
                isinstance(conditional_luck_cycles[key], Mapping)
                for key in ("forward", "backward")
            )
        ):
            return _unavailable("incomplete_conditional_cycles")

        branches = []
        for option_id, source_key in (
            ("option_a", "forward"),
            ("option_b", "backward"),
        ):
            raw = conditional_luck_cycles[source_key]
            if raw.get("direction") != source_key:
                raise _ProjectionError("invalid_luck_cycles")
            selected = _select_cycle(raw, focus_moment)
            branches.append(
                {
                    "id": option_id,
                    **_enhanced_cycle(
                        selected,
                        focus_moment,
                        day_master,
                        natal_stems,
                        natal_branches,
                    ),
                }
            )
        return {**common, "status": "conditional", "branches": branches}
    except _ProjectionError as exc:
        return _unavailable(exc.reason)
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return _unavailable("invalid_chart")


__all__ = ["UNAVAILABLE_REASONS", "project_dayun_facts"]
