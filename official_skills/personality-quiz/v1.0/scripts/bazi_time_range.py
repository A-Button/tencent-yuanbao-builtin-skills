#!/usr/bin/env python3
"""Compute Bazi invariants for an explicit interval or named shichen.

generate() accepts birth_date (YYYY-MM-DD), calendar, IANA timezone, location,
time_precision={"kind": "shichen", "minutes": None} and birth_time_branch,
or kind=range with explicit time_ranges. Both use the same vendored engine.
Lunar dates also accept lunar_is_leap_month; historical offsets follow
engine_common. Only ranges whose resolved offset is +08:00 are supported.

All ranges are half-open. Named Zi's [00:00, 01:00) and [23:00, 24:00) belong
to the SAME civil date; explicit intervals may cross midnight into next day.
Midnight day rollover uses the existing
engine's sect=2, including its different early/late Zi hour stems.

chart.stable contains invariant pillars and day_master; chart.possible.pillars
contains only variable pillars, in chronological candidate order. A complete
chart.pillars and deterministic details are included only when all four pillars
are invariant. Probe datetimes never leave this module as birth facts, and
details.luck_cycles is always None, even when gender_for_bazi was supplied.
Errors use EngineError; the CLI serializes them with engine_common.emit_error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import bazi_engine
from birth_time_range import read_ranges, resolve_range_timezone
from date_only_chart import _date_text, _unique
from engine_common import (
    EngineError,
    atomic_write_json,
    emit_error,
    load_json,
    location_provenance_detail,
    resolve_local_datetime_with_metadata,
    sha256_artifact,
    validate_location,
)


SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_NAME = "builtin-bazi-shichen-range"
ENGINE_VERSION = "1.1.0"
BRANCHES = "子丑寅卯辰巳午未申酉戌亥"
SAMPLE_POLICY = "range-endpoints-and-solar-term-boundaries"
DETERMINISTIC_DETAIL_KEYS = (
    "day_master", "heavenly_stems", "earthly_branches", "hidden_stems",
    "ten_gods", "twelve_growth_stages", "five_elements", "element_counts",
    "stem_relations", "branch_relations", "nayin",
)


def artifact_hash() -> str:
    return sha256_artifact(
        [
            Path(__file__).resolve(),
            SCRIPT_DIR / "bazi_engine.py",
            SCRIPT_DIR / "birth_time_range.py",
            SCRIPT_DIR / "date_only_chart.py",
            SCRIPT_DIR / "engine_common.py",
            SCRIPT_DIR / "vendor" / "lunar_python",
            SCRIPT_DIR / "vendor" / "LICENSE.lunar-python.txt",
        ],
        SCRIPT_DIR,
    )


def _birth_date(payload: dict[str, Any]) -> tuple[str, date]:
    value = payload.get("birth_date")
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise EngineError("E_INVALID_INPUT", "birth_date 必须是 YYYY-MM-DD。", ["birth_date"])
    calendar = payload.get("calendar", "gregorian")
    if calendar == "gregorian":
        normalized = _date_text(value)
        return normalized, date.fromisoformat(normalized)
    if calendar != "lunar":
        raise EngineError("E_INVALID_INPUT", "calendar 必须是 gregorian 或 lunar。", ["calendar"])
    is_leap = payload.get("lunar_is_leap_month", False)
    if not isinstance(is_leap, bool):
        raise EngineError("E_INVALID_INPUT", "lunar_is_leap_month 必须是布尔值。", ["lunar_is_leap_month"])
    year, month, day = map(int, value.split("-"))
    if not 1 <= year <= 9999 or not 1 <= month <= 12 or not 1 <= day <= 30:
        raise EngineError("E_INVALID_INPUT", "birth_date 不是有效的农历日期。", ["birth_date"])
    try:
        # Validate lunar days with the lunar calendar, not Gregorian February.
        lunar = bazi_engine.Lunar.fromYmd(year, -month if is_leap else month, day)
        return value, date.fromisoformat(lunar.getSolar().toYmd())
    except Exception as exc:
        raise EngineError(
            "E_CALENDAR_CONVERSION", f"农历日期无法转换：{exc}",
            ["birth_date", "lunar_is_leap_month"],
        ) from exc


def _ranges(branch: str) -> list[tuple[int, int]]:
    """Seconds since civil midnight; 86400 is an exclusive bound, not a date."""
    index = BRANCHES.index(branch)
    if index == 0:
        return [(0, 3600), (23 * 3600, 24 * 3600)]
    return [((2 * index - 1) * 3600, (2 * index + 1) * 3600)]


def _lunar_at(moment: datetime) -> Any:
    return bazi_engine.Solar.fromYmdHms(
        moment.year, moment.month, moment.day,
        moment.hour, moment.minute, moment.second,
    ).getLunar()


def _solar_term_seconds(lunar: Any, solar_date: date) -> list[int]:
    """All 24 terms are cheap to inspect; aliases are deduplicated by second."""
    return sorted({
        term.getHour() * 3600 + term.getMinute() * 60 + term.getSecond()
        for term in lunar.getJieQiTable().values()
        if term.toYmd() == solar_date.isoformat()
    })


def _segments(ranges: list[tuple[int, int]], terms: list[int]) -> list[tuple[int, int]]:
    segments = []
    # Arbitrary windows can cross shichen and civil-midnight boundaries.
    boundaries = sorted(set(terms) | {
        day * 86400 + hour * 3600
        for day in range(2) for hour in (0, *range(1, 24, 2))
    })
    for start, end in ranges:
        cuts = [start, *(term for term in boundaries if start < term < end), end]
        segments.extend(zip(cuts, cuts[1:]))
    return segments


def _resolve_timezone(moment: datetime, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        # A range must never select one side of a clock rollback via fold.
        aware, _, metadata = resolve_local_datetime_with_metadata(
            moment, payload.get("timezone"),
            historical_utc_offset=payload.get("historical_utc_offset"),
        )
    except EngineError as exc:
        if exc.code in {"E_NONEXISTENT_LOCAL_TIME", "E_AMBIGUOUS_LOCAL_TIME"}:
            raise EngineError(
                "E_TIME_RANGE_UNSUPPORTED_TIMEZONE",
                "出生时段包含时钟跳变或回拨歧义，当前范围引擎停止计算。",
                ["birth_date", "birth_time_branch" if payload.get("time_precision", {}).get("kind") == "shichen" else "time_ranges", "timezone"],
            ) from exc
        # The caller supplied a date/range, never a local_datetime.
        raise EngineError(
            exc.code, str(exc),
            ["birth_date" if field == "local_datetime" else field for field in exc.fields],
        ) from exc
    if aware.utcoffset() != timedelta(hours=8):
        raise EngineError(
            "E_TIME_RANGE_UNSUPPORTED_TIMEZONE",
            "当前八字范围计算仅支持整个范围实际 UTC 偏移为 +08:00；本输入停止计算。",
            ["birth_date", "birth_time_branch" if payload.get("time_precision", {}).get("kind") == "shichen" else "time_ranges", "timezone", "historical_utc_offset"],
        )
    return {key: value for key, value in metadata.items() if key != "fold"}


def _probe(lunar: Any) -> dict[str, Any]:
    eight_char = lunar.getEightChar()
    eight_char.setSect(2)
    stem = eight_char.getDayGan()
    return {
        "pillars": {
            "year": eight_char.getYear(), "month": eight_char.getMonth(),
            "day": eight_char.getDay(), "hour": eight_char.getTime(),
        },
        "day_master": {
            "stem": stem,
            "element": bazi_engine.LunarUtil.WU_XING_GAN[stem],
            "polarity": "yang" if bazi_engine.LunarUtil.GAN.index(stem) % 2 == 1 else "yin",
        },
    }


def _stable_details(
    moment: datetime, payload: dict[str, Any], location: dict[str, Any],
) -> dict[str, Any]:
    # A private exact call reuses existing deterministic detail generation once.
    # No gender is forwarded, so precise luck-cycle computation is never enabled.
    probe_input = {
        "calendar": "gregorian", "local_datetime": moment.isoformat(),
        "timezone": payload.get("timezone"), "location": location,
        "time_precision": {"kind": "exact", "minutes": 0},
        "day_boundary_policy": "civil-midnight", "solar_time_policy": "civil",
    }
    if payload.get("historical_utc_offset") is not None:
        probe_input["historical_utc_offset"] = payload["historical_utc_offset"]
    details = bazi_engine.generate(probe_input)["chart"]["details"]
    # Do not copy input, previous/next jie, or any exact-time-dependent field.
    return {key: details[key] for key in DETERMINISTIC_DETAIL_KEYS}


def generate(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise EngineError("E_INVALID_INPUT", "输入根节点必须是 JSON 对象。")
    ranges, clock_ranges, label = read_ranges(payload)
    precision = payload["time_precision"]
    branch = payload.get("birth_time_branch")
    if payload.get("day_boundary_policy", "civil-midnight") != "civil-midnight":
        raise EngineError("E_INVALID_INPUT", "时辰范围固定使用 civil-midnight 午夜换日。", ["day_boundary_policy"])
    if payload.get("solar_time_policy", "civil") != "civil":
        raise EngineError("E_UNSUPPORTED_SOLAR_TIME", "时辰范围只支持 civil 民用标准时。", ["solar_time_policy"])
    birth_date, solar_date = _birth_date(payload)
    location = validate_location(payload.get("location"))
    gender_value = payload.get("gender_for_bazi")
    if gender_value is not None and not isinstance(gender_value, str):
        raise EngineError("E_INVALID_INPUT", "gender_for_bazi 必须是有效字符串。", ["gender_for_bazi"])
    gender = bazi_engine._normalize_gender(gender_value)
    midnight = datetime(solar_date.year, solar_date.month, solar_date.day)
    first_moment = midnight + timedelta(seconds=ranges[0][0])
    timezone_metadata = _resolve_timezone(first_moment, payload)
    resolve_range_timezone(midnight, ranges, payload)
    first_lunar = _lunar_at(first_moment)
    terms = _solar_term_seconds(first_lunar, solar_date)
    if ranges[-1][1] > 86400:
        next_date = solar_date + timedelta(days=1)
        terms += [86400 + second for second in _solar_term_seconds(_lunar_at(midnight + timedelta(days=1)), next_date)]
    segments = _segments(ranges, terms)
    # Every piece has constant year/month/day/hour according to the vendored
    # engine: terms split year/month, midnight splits days, shichen splits hours.
    # Check each piece's inclusive first/last second, including both term sides.
    seconds = sorted({second for start, end in segments for second in (start, end - 1)})
    samples = []
    for second in seconds:
        moment = midnight + timedelta(seconds=second)
        if moment == first_moment:
            lunar = first_lunar
        else:
            _resolve_timezone(moment, payload)
            lunar = _lunar_at(moment)
        samples.append(_probe(lunar))

    possible_pillars = {
        key: _unique([sample["pillars"][key] for sample in samples])
        for key in bazi_engine.PILLAR_KEYS
    }
    stable_pillars = {key: values[0] for key, values in possible_pillars.items() if len(values) == 1}
    day_masters = _unique([sample["day_master"] for sample in samples])
    fully_stable = len(stable_pillars) == len(bazi_engine.PILLAR_KEYS)
    details: dict[str, Any] = {
        "sample_count": len(samples), "sample_policy": SAMPLE_POLICY,
        "segment_count": len(segments),
        "solar_term_boundary_count": sum(any(start <= term < end for start, end in ranges) for term in terms),
        "day_boundary_policy": "civil-midnight", "solar_time_policy": "civil",
        "luck_cycles": None,
    }
    if fully_stable:
        details.update(_stable_details(first_moment, payload, location))
    chart: dict[str, Any] = {
        "coverage": "time-range-invariants", "precision": "time-range",
        "stable": {"pillars": stable_pillars, "day_master": day_masters[0] if len(day_masters) == 1 else None},
        "possible": {"pillars": {key: values for key, values in possible_pillars.items() if len(values) > 1}},
        "details": details,
        "unavailable": ["大运起点与阶段周期"],
    }
    if fully_stable:
        chart["pillars"] = dict(stable_pillars)
    else:
        chart["unavailable"].append("依赖未稳定四柱的十神、藏干、五行计数与干支关系")
    normalized_input: dict[str, Any] = {
        "calendar": payload.get("calendar", "gregorian"), "birth_date": birth_date,
        "resolved_solar_dates": [(solar_date + timedelta(days=day)).isoformat() for day in range(1 + (ranges[-1][1] - 1) // 86400)],
        "timezone": payload.get("timezone"), **timezone_metadata,
        "location": location, "chart_precision": "time-range",
        "time_precision": {"kind": precision["kind"], "minutes": None},
        "time_range_label": label,
        "time_ranges": clock_ranges,
        "day_boundary_policy": "civil-midnight", "solar_time_policy": "civil",
    }
    if precision["kind"] == "shichen":
        normalized_input["birth_time_branch"] = branch
    if payload.get("calendar") == "lunar":
        normalized_input["lunar_is_leap_month"] = payload.get("lunar_is_leap_month", False)
    if gender is not None:
        normalized_input["gender_for_bazi"] = gender[1]
    return {
        "schema_version": "1.0.0",
        "engine": {
            "name": ENGINE_NAME, "version": ENGINE_VERSION,
            "artifact_hash": artifact_hash(), "license": bazi_engine.ENGINE_LICENSE,
            "underlying": f"{bazi_engine.ENGINE_NAME} {bazi_engine.ENGINE_VERSION}",
        },
        "input": normalized_input, "chart_system": "bazi", "chart": chart,
        "boundary_checks": [
            {"name": "time-range-segmentation", "status": "pass", "detail": f"segments={len(segments)}; endpoint_samples={len(samples)}; solar_terms={details['solar_term_boundary_count']}"},
            {"name": "timezone-resolved", "status": "pass", "detail": "全部区间边界实际 UTC 偏移为 +08:00，已完成 UTC 往返校验。"},
            {"name": "location-resolved", "status": "pass", "detail": location_provenance_detail(location)},
            {"name": "day-boundary-policy", "status": "pass", "detail": "civil-midnight; 子时两段均属于所给民用日期"},
            {"name": "internal-times-not-birth-time", "status": "pass", "detail": "区间边界仅用于验证，没有输出探测时刻或精确起运。"},
        ],
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "timezone_db_version": timezone_metadata["timezone_db_version"],
            "calendar_engine": "lunar-python 1.4.8 (vendored)",
        },
        "warnings": [
            "仅在所给出生时段内验证稳定字段及候选，没有补造出生分钟。",
            "出生分钟未知，不计算精确起运或大运阶段周期。",
            "地点仅记录来源；按民用当地时排盘，不做真太阳时修正。",
            "这是传统历法排盘事实，不是经科学验证的人生预测。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Bazi facts for a named shichen range.")
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
