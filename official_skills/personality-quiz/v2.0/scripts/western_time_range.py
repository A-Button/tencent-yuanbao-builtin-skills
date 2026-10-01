#!/usr/bin/env python3
"""Verify tropical sign invariants only inside supplied civil-clock intervals.

Adaptive subdivision covers the integer-second grid, pruning a segment only
when a generous angular-speed envelope cannot reach a sign boundary. It does
not infer stability from matching endpoints (retrograde excursions can return
to the starting sign). Probes never become claimed birth times or degrees.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Callable, Any

import western_engine as western
from birth_time_range import read_ranges, resolve_range_timezone
from date_only_chart import _date_text
from engine_common import EngineError, atomic_write_json, emit_error, load_json, validate_location, sha256_artifact

SCRIPT_DIR = Path(__file__).resolve().parent
SAMPLE_POLICY = "adaptive-angular-envelope; whole-second-grid; half-open-civil-ranges"
# Deliberately loose envelopes over the wrapper's 1800–2200 product domain.
# 864 degrees/day exceeds lunar and planetary geocentric angular rates by a
# wide margin; 1 degree/second exceeds geometric rising rates at |lat| <= 65.
# These are pruning guards, NOT inferred velocities from the two endpoints.
PLANET_SPEED_BOUND = 0.01
ASCENDANT_SPEED_BOUND = 1.0


def sign_candidates(longitude_at: Callable[[int], float], ranges: list[tuple[int, int]], speed_bound: float) -> tuple[list[str], int]:
    if not math.isfinite(speed_bound) or speed_bound <= 0:
        raise ValueError("speed_bound must be positive and finite")
    samples: dict[int, float] = {}

    def sample(second: int) -> float:
        if second not in samples:
            value = longitude_at(second)
            if not math.isfinite(value):
                raise EngineError("E_INVALID_INPUT", "星历返回了无效角度。")
            samples[second] = value % 360
        return samples[second]

    def visit(start: int, last: int) -> None:
        middle = (start + last) // 2
        longitude = sample(middle)
        distance = min(longitude % 30, 30 - longitude % 30)
        if distance > speed_bound * max(middle - start, last - middle) + 1e-9:
            return
        if start < middle:
            visit(start, middle - 1)
        if middle < last:
            visit(middle + 1, last)

    for start, end in ranges:
        sample(start)
        sample(end - 1)
        visit(start, end - 1)
    candidates = list(dict.fromkeys(western.SIGNS_ZH[int(samples[second] // 30)] for second in sorted(samples)))
    return candidates, len(samples)


def artifact_hash() -> str:
    return sha256_artifact([
        Path(__file__).resolve(), SCRIPT_DIR / "birth_time_range.py",
        SCRIPT_DIR / "western_engine.py", SCRIPT_DIR / "date_only_chart.py",
        SCRIPT_DIR / "engine_common.py", SCRIPT_DIR / "vendor" / "astronomy",
        SCRIPT_DIR / "vendor" / "LICENSE.astronomy-engine.txt",
    ], SCRIPT_DIR)


def generate(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("calendar", "gregorian") != "gregorian":
        raise EngineError("E_INVALID_INPUT", "西洋范围盘只接受 gregorian 对象输入。", ["calendar"])
    birth_date = _date_text(payload.get("birth_date"))
    midnight = datetime.fromisoformat(birth_date)
    ranges, clock_ranges, label = read_ranges(payload)
    last_moment = midnight + timedelta(seconds=ranges[-1][1] - 1)
    if not 1800 <= midnight.year <= last_moment.year <= 2200:
        raise EngineError("E_EPHEMERIS_RANGE", "西洋范围盘支持 1800—2200 年。", ["birth_date", "time_ranges"])
    location = validate_location(payload.get("location"))
    offset, metadata = resolve_range_timezone(midnight, ranges, payload)
    utc_midnight = midnight - offset

    @lru_cache(maxsize=None)
    def astro_time(second: int) -> western.astro.Time:
        moment = utc_midnight + timedelta(seconds=second)
        return western.astro.Time.Make(moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)

    stable: dict[str, Any] = {"planet_signs": {}}
    possible: dict[str, Any] = {"planet_signs": {}}
    counts = {}
    planets = {}
    for key, body in western.BODIES:
        def longitude_at(second: int) -> float:
            return western.astro.Ecliptic(western.astro.GeoVector(body, astro_time(second), True)).elon
        signs, counts[key] = sign_candidates(longitude_at, ranges, PLANET_SPEED_BOUND)
        if len(signs) == 1:
            stable["planet_signs"][key] = signs[0]
        else:
            possible["planet_signs"][key] = signs
        planets[key] = {"status": "stable" if len(signs) == 1 else "variable", "sign": signs[0] if len(signs) == 1 else None, "possible_signs": signs}

    _, ascendant_status = western.calculate_ascendant(astro_time(ranges[0][0]), location)
    ascendant = None
    if ascendant_status == "available":
        def ascending_longitude(second: int) -> float:
            return western.calculate_ascendant(astro_time(second), location, round_coordinates=False)[0]["longitude_deg"]
        signs, counts["ascendant"] = sign_candidates(ascending_longitude, ranges, ASCENDANT_SPEED_BOUND)
        if len(signs) == 1:
            stable["ascendant"] = ascendant = {"sign": signs[0]}
        else:
            possible["ascendant"] = signs
            ascendant_status = "variable"
    normalized = {
        "calendar": "gregorian", "birth_date": birth_date,
        "timezone": payload.get("timezone"), **metadata, "location": location,
        "chart_precision": "time-range", "time_precision": {"kind": payload["time_precision"]["kind"], "minutes": None},
        "time_ranges": clock_ranges, "time_range_label": label,
    }
    if payload["time_precision"]["kind"] == "shichen":
        normalized["birth_time_branch"] = payload["birth_time_branch"]
    return {
        "schema_version": "1.0.0", "chart_system": "western",
        "engine": {"name": "builtin-western-time-range", "version": "1.0.0", "artifact_hash": artifact_hash(), "license": western.ENGINE_LICENSE},
        "input": normalized,
        "chart": {
            "precision": "time-range", "coverage": "time-range-sign-invariants", "zodiac": "tropical",
            "stable": stable, "possible": possible, "planets": planets,
            "ascendant": ascendant, "ascendant_status": ascendant_status,
            "aspects": None, "houses": None,
            "details": {"sample_count": sum(counts.values()), "sample_policy": SAMPLE_POLICY, "resolution_seconds": 1, "component_sample_counts": counts},
        },
        "boundary_checks": [
            {"name": "time-range-verified", "status": "pass", "detail": "只核验所给半开时段，秒级自适应检查星座交界；不以端点相同推断稳定。"},
            {"name": "timezone-resolved", "status": "pass", "detail": "所给区间逐秒 UTC 往返校验，钟制一致；没有选择 fold 或扩大到全天。"},
            {"name": "internal-times-not-birth-time", "status": "pass", "detail": "不输出探测时刻、代表角度、相位或宫位。"},
        ],
        "provenance": {"generated_at": datetime.now(timezone.utc).isoformat(), "timezone_db_version": metadata["timezone_db_version"], "ephemeris_version": "Astronomy Engine 2.1.19"},
        "warnings": ["仅解读所给时段内稳定的星座；真正跨界的项目保留候选，不挑选其一。", "星座测试是一种文化解读"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Western signs inside an explicit birth-time range.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = generate(load_json(args.input))
        atomic_write_json(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(json.dumps(emit_error(exc), ensure_ascii=False), file=sys.stderr)
        return 2 if isinstance(exc, EngineError) else 3


if __name__ == "__main__":
    raise SystemExit(main())
