#!/usr/bin/env python3
"""Generate an allowlist-ready Bazi fact payload with vendored lunar-python."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

from engine_common import (
    EngineError,
    atomic_write_json,
    emit_error,
    load_json,
    location_provenance_detail,
    parse_naive_datetime,
    require_exact_single_chart_time,
    resolve_local_datetime_with_metadata,
    sha256_artifact,
    timezone_db_version,
    validate_location,
    validate_time_precision,
)


SCRIPT_DIR = Path(__file__).resolve().parent
VENDOR_DIR = SCRIPT_DIR / "vendor"
sys.path.insert(0, str(VENDOR_DIR))

from lunar_python import Lunar, Solar  # noqa: E402
from lunar_python.util import LunarUtil  # noqa: E402


ENGINE_NAME = "builtin-lunar-python-bazi"
ENGINE_VERSION = "1.4.8+wrapper.3"
ENGINE_LICENSE = "MIT; vendored source and license included"
PILLAR_KEYS = ("year", "month", "day", "hour")
HIDDEN_ROLES = ("main", "secondary", "residual")
STEM_COMBINATIONS = {
    frozenset(pair) for pair in (("甲", "己"), ("乙", "庚"), ("丙", "辛"), ("丁", "壬"), ("戊", "癸"))
}
BRANCH_PAIR_RELATIONS = {
    "six_harmony": {
        frozenset(pair)
        for pair in (("子", "丑"), ("寅", "亥"), ("卯", "戌"), ("辰", "酉"), ("巳", "申"), ("午", "未"))
    },
    "six_clash": {
        frozenset(pair)
        for pair in (("子", "午"), ("丑", "未"), ("寅", "申"), ("卯", "酉"), ("辰", "戌"), ("巳", "亥"))
    },
    "six_harm": {
        frozenset(pair)
        for pair in (("子", "未"), ("丑", "午"), ("寅", "巳"), ("卯", "辰"), ("申", "亥"), ("酉", "戌"))
    },
    "break": {
        frozenset(pair)
        for pair in (("子", "酉"), ("丑", "辰"), ("寅", "亥"), ("卯", "午"), ("巳", "申"), ("未", "戌"))
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


def artifact_hash() -> str:
    return sha256_artifact(
        [
            Path(__file__).resolve(),
            SCRIPT_DIR / "engine_common.py",
            VENDOR_DIR / "lunar_python",
            VENDOR_DIR / "LICENSE.lunar-python.txt",
        ],
        SCRIPT_DIR,
    )


def _lunar_from_input(payload: dict[str, Any]) -> tuple[Any, datetime, dict[str, Any]]:
    calendar = payload.get("calendar", "gregorian")
    if calendar == "gregorian":
        naive = parse_naive_datetime(payload.get("local_datetime"))
        solar = Solar.fromYmdHms(
            naive.year,
            naive.month,
            naive.day,
            naive.hour,
            naive.minute,
            naive.second,
        )
        return solar.getLunar(), naive, {}
    if calendar != "lunar":
        raise EngineError(
            "E_INVALID_INPUT",
            "calendar 必须是 gregorian 或 lunar。",
            ["calendar"],
        )
    lunar_value = payload.get("lunar_datetime")
    # Lunar February can have 30 days: do not validate it as a Gregorian datetime.
    match = re.fullmatch(r"([0-9]{4})-([0-9]{2})-([0-9]{2})[T ]([0-9]{2}):([0-9]{2})(?::([0-9]{2}))?", lunar_value if isinstance(lunar_value, str) else "")
    if not match:
        raise EngineError("E_INVALID_INPUT", "lunar_datetime 必须是当地农历 YYYY-MM-DDTHH:MM:SS。", ["lunar_datetime"])
    year, month, day, hour, minute, second = (int(value or 0) for value in match.groups())
    if not (1 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= 30 and hour < 24 and minute < 60 and second < 60):
        raise EngineError("E_INVALID_INPUT", "农历日期或钟表时间无效。", ["lunar_datetime"])
    is_leap = payload.get("lunar_is_leap_month", False)
    if not isinstance(is_leap, bool):
        raise EngineError(
            "E_INVALID_INPUT",
            "lunar_is_leap_month 必须是布尔值。",
            ["lunar_is_leap_month"],
        )
    month = -month if is_leap else month
    try:
        lunar = Lunar.fromYmdHms(
            year,
            month,
            day,
            hour,
            minute,
            second,
        )
        solar = lunar.getSolar()
    except Exception as exc:
        raise EngineError(
            "E_CALENDAR_CONVERSION",
            f"农历日期无法转换：{exc}",
            ["lunar_datetime", "lunar_is_leap_month"],
        ) from exc
    naive = datetime.fromisoformat(solar.toYmdHms().replace(" ", "T"))
    return lunar, naive, {
        "original_lunar_datetime": lunar_value,
        "lunar_is_leap_month": is_leap,
    }


def _jie_payload(value: Any) -> dict[str, str] | None:
    if value is None:
        return None
    return {"name": value.getName(), "local_datetime": value.getSolar().toYmdHms()}


def _pillar_values(eight_char: Any) -> dict[str, dict[str, Any]]:
    stems = {
        "year": eight_char.getYearGan(),
        "month": eight_char.getMonthGan(),
        "day": eight_char.getDayGan(),
        "hour": eight_char.getTimeGan(),
    }
    branches = {
        "year": eight_char.getYearZhi(),
        "month": eight_char.getMonthZhi(),
        "day": eight_char.getDayZhi(),
        "hour": eight_char.getTimeZhi(),
    }
    hidden_raw = {
        "year": eight_char.getYearHideGan(),
        "month": eight_char.getMonthHideGan(),
        "day": eight_char.getDayHideGan(),
        "hour": eight_char.getTimeHideGan(),
    }
    hidden_ten_gods = {
        "year": eight_char.getYearShiShenZhi(),
        "month": eight_char.getMonthShiShenZhi(),
        "day": eight_char.getDayShiShenZhi(),
        "hour": eight_char.getTimeShiShenZhi(),
    }
    hidden = {
        key: [
            {
                "stem": stem,
                "element": LunarUtil.WU_XING_GAN.get(stem),
                "ten_god": hidden_ten_gods[key][index],
                "role": HIDDEN_ROLES[index],
            }
            for index, stem in enumerate(hidden_raw[key])
        ]
        for key in PILLAR_KEYS
    }
    stem_ten_gods = {
        "year": eight_char.getYearShiShenGan(),
        "month": eight_char.getMonthShiShenGan(),
        "day": eight_char.getDayShiShenGan(),
        "hour": eight_char.getTimeShiShenGan(),
    }
    growth = {
        "year": eight_char.getYearDiShi(),
        "month": eight_char.getMonthDiShi(),
        "day": eight_char.getDayDiShi(),
        "hour": eight_char.getTimeDiShi(),
    }
    return {
        "stems": stems,
        "branches": branches,
        "hidden": hidden,
        "stem_ten_gods": stem_ten_gods,
        "growth": growth,
    }


def _element_counts(
    stems: dict[str, str],
    branches: dict[str, str],
    hidden: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, int]]:
    visible = {element: 0 for element in ("木", "火", "土", "金", "水")}
    hidden_counts = {element: 0 for element in visible}
    for stem in stems.values():
        visible[LunarUtil.WU_XING_GAN[stem]] += 1
    for branch in branches.values():
        visible[LunarUtil.WU_XING_ZHI[branch]] += 1
    for items in hidden.values():
        for item in items:
            hidden_counts[item["element"]] += 1
    return {
        "visible_stems_and_branches_unweighted": visible,
        "hidden_stems_unweighted": hidden_counts,
    }


def _stem_relations(stems: dict[str, str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for first, second in combinations(PILLAR_KEYS, 2):
        pair = frozenset((stems[first], stems[second]))
        if pair in STEM_COMBINATIONS:
            result.append(
                {
                    "type": "five_stem_combination",
                    "members": [stems[first], stems[second]],
                    "pillars": [first, second],
                    "transformation_claimed": False,
                }
            )
    return result


def _branch_relations(branches: dict[str, str]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for first, second in combinations(PILLAR_KEYS, 2):
        members = (branches[first], branches[second])
        pair = frozenset(members)
        for relation_type, relation_pairs in BRANCH_PAIR_RELATIONS.items():
            if pair in relation_pairs:
                result.append(
                    {
                        "type": relation_type,
                        "members": list(members),
                        "pillars": [first, second],
                        "transformation_claimed": False,
                    }
                )
        if members[0] == members[1] and members[0] in SELF_PUNISHMENT_BRANCHES:
            result.append(
                {
                    "type": "self_punishment",
                    "members": list(members),
                    "pillars": [first, second],
                    "transformation_claimed": False,
                }
            )

    present = set(branches.values())
    for relation_type, groups in THREE_BRANCH_RELATIONS.items():
        for group in groups:
            if group.issubset(present):
                pillars = [key for key in PILLAR_KEYS if branches[key] in group]
                result.append(
                    {
                        "type": relation_type,
                        "members": sorted(group),
                        "pillars": pillars,
                        "transformation_claimed": False,
                    }
                )
    return result


def _normalize_gender(value: Any) -> tuple[int, str] | None:
    if value is None:
        return None
    mapping = {
        "male": (1, "male"),
        "男": (1, "male"),
        "female": (0, "female"),
        "女": (0, "female"),
    }
    if value not in mapping:
        raise EngineError(
            "E_INVALID_INPUT",
            "gender_for_bazi 必须是 male、female、男或女。",
            ["gender_for_bazi"],
        )
    return mapping[value]


def _luck_cycles(eight_char: Any, gender: tuple[int, str] | None) -> dict[str, Any] | None:
    if gender is None:
        return None
    gender_value, normalized = gender
    yun = eight_char.getYun(gender_value, sect=1)
    cycles = []
    for item in yun.getDaYun(9):
        if item.getIndex() == 0:
            continue
        cycles.append(
            {
                "index": item.getIndex(),
                "gan_zhi": item.getGanZhi(),
                "start_year": item.getStartYear(),
                "end_year": item.getEndYear(),
                "start_age": item.getStartAge(),
                "end_age": item.getEndAge(),
            }
        )
    return {
        "gender_rule_input": normalized,
        "calculation_method": "lunar-python-yun-sect-1",
        "direction": "forward" if yun.isForward() else "backward",
        "start_offset": {
            "years": yun.getStartYear(),
            "months": yun.getStartMonth(),
            "days": yun.getStartDay(),
            "hours": yun.getStartHour(),
        },
        "start_solar_datetime": yun.getStartSolar().toYmdHms(),
        "cycles": cycles,
    }


def generate(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("solar_time_policy", "civil") != "civil":
        raise EngineError(
            "E_UNSUPPORTED_SOLAR_TIME",
            "内置引擎当前只支持 civil 标准时；不会把经度修正冒充真太阳时。",
            ["solar_time_policy"],
        )
    day_boundary = payload.get("day_boundary_policy", "civil-midnight")
    if day_boundary not in {"civil-midnight", "late-zi-next-day"}:
        raise EngineError(
            "E_INVALID_INPUT",
            "day_boundary_policy 必须是 civil-midnight 或 late-zi-next-day。",
            ["day_boundary_policy"],
        )

    lunar, solar_naive, original_calendar = _lunar_from_input(payload)
    aware, timezone_detail, timezone_resolution = resolve_local_datetime_with_metadata(
        solar_naive,
        payload.get("timezone"),
        payload.get("fold"),
        payload.get("historical_utc_offset"),
    )
    location = validate_location(payload.get("location"))
    time_precision = require_exact_single_chart_time(
        validate_time_precision(payload.get("time_precision"))
    )

    eight_char = lunar.getEightChar()
    eight_char.setSect(1 if day_boundary == "late-zi-next-day" else 2)
    pillar_values = _pillar_values(eight_char)
    stems = pillar_values["stems"]
    branches = pillar_values["branches"]
    hidden = pillar_values["hidden"]
    gender = _normalize_gender(payload.get("gender_for_bazi"))
    pillars = {
        "year": eight_char.getYear(),
        "month": eight_char.getMonth(),
        "day": eight_char.getDay(),
        "hour": eight_char.getTime(),
    }
    details = {
        "day_master": {
            "stem": eight_char.getDayGan(),
            "element": LunarUtil.WU_XING_GAN[eight_char.getDayGan()],
            "polarity": (
                "yang"
                if LunarUtil.GAN.index(eight_char.getDayGan()) % 2 == 1
                else "yin"
            ),
        },
        "heavenly_stems": stems,
        "earthly_branches": branches,
        "hidden_stems": hidden,
        "ten_gods": {
            "heavenly_stems": pillar_values["stem_ten_gods"],
            "hidden_stems": {
                key: [item["ten_god"] for item in hidden[key]]
                for key in PILLAR_KEYS
            },
        },
        "twelve_growth_stages": pillar_values["growth"],
        "five_elements": {
            "year": eight_char.getYearWuXing(),
            "month": eight_char.getMonthWuXing(),
            "day": eight_char.getDayWuXing(),
            "hour": eight_char.getTimeWuXing(),
        },
        "element_counts": _element_counts(stems, branches, hidden),
        "stem_relations": _stem_relations(stems),
        "branch_relations": _branch_relations(branches),
        "nayin": {
            "year": eight_char.getYearNaYin(),
            "month": eight_char.getMonthNaYin(),
            "day": eight_char.getDayNaYin(),
            "hour": eight_char.getTimeNaYin(),
        },
        "luck_cycles": _luck_cycles(eight_char, gender),
        "previous_jie": _jie_payload(lunar.getPrevJie()),
        "next_jie": _jie_payload(lunar.getNextJie()),
        "day_boundary_policy": day_boundary,
        "solar_time_policy": "civil",
    }
    calendar = payload.get("calendar", "gregorian")
    normalized_input: dict[str, Any] = {
        "calendar": calendar,
        "local_datetime": solar_naive.isoformat(),
        "timezone": payload["timezone"],
        **timezone_resolution,
        "location": location,
        "time_precision": time_precision,
        "day_boundary_policy": day_boundary,
        "solar_time_policy": "civil",
        **original_calendar,
    }
    if gender is not None:
        normalized_input["gender_for_bazi"] = gender[1]
    warnings = [
        "这是传统历法排盘事实，不是经科学验证的人生预测。",
        "地点仅用于记录来源；本版本按民用当地时排盘，不做真太阳时修正。",
        "五行计数、干支关系和大运周期只是排盘事实，不自动等于强弱、喜忌、吉凶或现实事件。",
    ]
    if gender is None:
        warnings.append("未提供传统顺逆排运所需的性别选项，本次不计算大运。")
    else:
        warnings.append(
            "大运使用 lunar-python sect=1 和传统性别顺逆规则；不同流派可能采用不同起运口径。"
        )
    return {
        "schema_version": "1.0.0",
        "engine": {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "artifact_hash": artifact_hash(),
            "license": ENGINE_LICENSE,
        },
        "input": normalized_input,
        "chart_system": "bazi",
        "chart": {"pillars": pillars, "details": details},
        "boundary_checks": [
            {"name": "timezone-resolved", "status": "pass", "detail": timezone_detail},
            {
                "name": "location-resolved",
                "status": "pass",
                "detail": location_provenance_detail(location),
            },
            {
                "name": "time-precision-propagated",
                "status": "pass",
                "detail": json.dumps(time_precision, ensure_ascii=False),
            },
            {
                "name": "solar-term-boundary",
                "status": "pass",
                "detail": (
                    f"prev={details['previous_jie']}; next={details['next_jie']}; "
                    "月柱采用节令边界"
                ),
            },
            {
                "name": "day-boundary-policy",
                "status": "pass",
                "detail": day_boundary,
            },
        ],
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timezone_db_version": timezone_db_version(),
            "calendar_engine": "lunar-python 1.4.8 (vendored)",
        },
        "warnings": warnings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a bundled Bazi fact payload.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = generate(load_json(args.input))
        atomic_write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps(emit_error(exc), ensure_ascii=False, indent=2), file=sys.stderr)
        return 2 if isinstance(exc, EngineError) else 3


if __name__ == "__main__":
    raise SystemExit(main())
