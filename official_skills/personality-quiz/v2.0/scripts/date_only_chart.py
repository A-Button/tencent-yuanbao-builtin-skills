#!/usr/bin/env python3
"""Generate a date-only chart containing invariants and explicit ranges.

Internal sample times are calculation probes, never claimed as birth times.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable

from engine_common import (
    EngineError,
    atomic_write_json,
    emit_error,
    load_json,
    sha256_artifact,
    validate_location,
)


SCRIPT_DIR = Path(__file__).resolve().parent
ENGINE_NAME = "builtin-date-only-invariant-sampler"
ENGINE_VERSION = "1.2.0"
SAMPLE_TIMES = tuple(
    ["00:00:00"]
    + [f"{hour:02d}:30:00" for hour in range(0, 24, 2)]
    + ["23:30:00", "23:59:59"]
)
SAMPLE_POLICY = "local-date-boundaries-plus-2-hour-probes"


def artifact_hash() -> str:
    return sha256_artifact(
        [
            Path(__file__).resolve(),
            SCRIPT_DIR / "bazi_engine.py",
            SCRIPT_DIR / "western_engine.py",
            SCRIPT_DIR / "engine_common.py",
            SCRIPT_DIR / "vendor" / "lunar_python",
            SCRIPT_DIR / "vendor" / "astronomy",
        ],
        SCRIPT_DIR,
    )


def _date_text(value: Any, calendar: str = "gregorian") -> str:
    if not isinstance(value, str):
        raise EngineError("E_INVALID_INPUT", "birth_date 必须是 YYYY-MM-DD。", ["birth_date"])
    if calendar == "lunar":
        if re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
            year, month, day = map(int, value.split("-"))
            if 1 <= year <= 9999 and 1 <= month <= 12 and 1 <= day <= 30:
                return value  # The lunar engine validates actual month length.
        raise EngineError("E_INVALID_INPUT", "birth_date 必须是有效农历日期。", ["birth_date"])
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise EngineError("E_INVALID_INPUT", "birth_date 必须是有效的 YYYY-MM-DD。", ["birth_date"]) from exc
    return parsed.isoformat()


def _time_precision(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EngineError("E_INVALID_INPUT", "time_precision 必须是对象。", ["time_precision"])
    kind = value.get("kind")
    if kind not in {"approximate", "range", "unknown", "withheld", "unspecified"}:
        raise EngineError(
            "E_INVALID_INPUT",
            "日期级初盘只接受 approximate、range、unknown、withheld 或 unspecified。",
            ["time_precision.kind"],
        )
    minutes = value.get("minutes")
    if minutes is not None and (
        isinstance(minutes, bool) or not isinstance(minutes, (int, float)) or minutes < 0
    ):
        raise EngineError(
            "E_INVALID_INPUT",
            "time_precision.minutes 必须是非负数或 null。",
            ["time_precision.minutes"],
        )
    return {"kind": kind, "minutes": minutes}


def _sampling_warning(precision: dict[str, Any], stable_scope: str) -> str:
    kind = precision.get("kind")
    if kind == "approximate":
        return "当前“大概时间”仍按当地整日采样，结果没有缩小到某个具体时段。"
    if kind == "range":
        return "当前“时间范围”仍按当地整日采样，结果没有缩小到所给时段。"
    return stable_scope


def _sample_payload(payload: dict[str, Any], date_text: str, time_text: str) -> dict[str, Any]:
    calendar = payload.get("calendar", "gregorian")
    sample: dict[str, Any] = {
        "calendar": calendar,
        "timezone": payload.get("timezone"),
        "location": payload.get("location"),
        "time_precision": {"kind": "exact", "minutes": 0},
        "day_boundary_policy": payload.get("day_boundary_policy", "civil-midnight"),
        "solar_time_policy": payload.get("solar_time_policy", "civil"),
    }
    if calendar == "gregorian":
        sample["local_datetime"] = f"{date_text}T{time_text}"
    elif calendar == "lunar":
        sample["lunar_datetime"] = f"{date_text}T{time_text}"
        sample["lunar_is_leap_month"] = payload.get("lunar_is_leap_month")
    else:
        raise EngineError("E_INVALID_INPUT", "calendar 必须是 gregorian 或 lunar。", ["calendar"])
    if payload.get("historical_utc_offset") is not None:
        sample["historical_utc_offset"] = payload["historical_utc_offset"]
    return sample


def _run_sample(
    generator: Callable[[dict[str, Any]], dict[str, Any]],
    sample: dict[str, Any],
) -> list[dict[str, Any]]:
    try:
        return [generator(sample)]
    except EngineError as exc:
        if exc.code == "E_NONEXISTENT_LOCAL_TIME":
            return []
        if exc.code != "E_AMBIGUOUS_LOCAL_TIME":
            raise
    results = []
    for fold in (0, 1):
        candidate = {**sample, "fold": fold}
        results.append(generator(candidate))
    return results


def _unique(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    serialized: set[str] = set()
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if marker not in serialized:
            result.append(value)
            serialized.add(marker)
    return result


def _solar_date_for_western(payload: dict[str, Any], date_text: str) -> str:
    if payload.get("calendar", "gregorian") == "gregorian":
        return date_text
    import bazi_engine

    probe = _sample_payload(payload, date_text, "12:00:00")
    _, solar_naive, _ = bazi_engine._lunar_from_input(probe)
    return solar_naive.date().isoformat()


def _common_input(
    payload: dict[str, Any],
    birth_date: str,
    precision: dict[str, Any],
    location: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "calendar": payload.get("calendar", "gregorian"),
        "birth_date": birth_date,
        "timezone": payload.get("timezone"),
        "location": location,
        "time_precision": precision,
        "chart_precision": "date-only",
    }
    if payload.get("calendar") == "lunar":
        result["lunar_is_leap_month"] = payload.get("lunar_is_leap_month")
    return result


def generate_bazi(payload: dict[str, Any]) -> dict[str, Any]:
    import bazi_engine

    birth_date = _date_text(payload.get("birth_date"), payload.get("calendar", "gregorian"))
    precision = _time_precision(payload.get("time_precision"))
    location = validate_location(payload.get("location"))
    cached_hash = bazi_engine.artifact_hash()
    original_hash = bazi_engine.artifact_hash
    bazi_engine.artifact_hash = lambda: cached_hash
    samples: list[dict[str, Any]] = []
    skipped = 0
    try:
        for time_text in SAMPLE_TIMES:
            current = _run_sample(
                bazi_engine.generate,
                _sample_payload(payload, birth_date, time_text),
            )
            if not current:
                skipped += 1
            samples.extend(current)
    finally:
        bazi_engine.artifact_hash = original_hash
    if not samples:
        raise EngineError("E_DATE_ONLY_NO_VALID_SAMPLES", "该日期没有可用的当地时间样本。", ["birth_date", "timezone"])

    pillar_keys = ("year", "month", "day", "hour")
    possible_pillars = {
        key: _unique([sample["chart"]["pillars"][key] for sample in samples])
        for key in pillar_keys
    }
    stable_pillars = {
        key: values[0]
        for key, values in possible_pillars.items()
        if len(values) == 1 and key != "hour"
    }
    day_masters = _unique([sample["chart"]["details"]["day_master"] for sample in samples])
    stable_day_master = day_masters[0] if len(day_masters) == 1 else None
    solar_dates = _unique([sample["input"]["local_datetime"][:10] for sample in samples])
    possible = {
        "pillars": {
            key: values
            for key, values in possible_pillars.items()
            if key == "hour" or len(values) > 1
        }
    }
    return {
        "schema_version": "1.0.0",
        "engine": {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "artifact_hash": artifact_hash(),
            "underlying": f"{bazi_engine.ENGINE_NAME} {bazi_engine.ENGINE_VERSION}",
        },
        "input": {
            **_common_input(payload, birth_date, precision, location),
            "resolved_solar_dates": solar_dates,
        },
        "chart_system": "bazi",
        "chart": {
            "coverage": "date-only-invariants",
            "precision": "date-only",
            "stable": {"pillars": stable_pillars, "day_master": stable_day_master},
            "possible": possible,
            "details": {
                "sample_count": len(samples),
                "sample_policy": SAMPLE_POLICY,
                "skipped_nonexistent_local_times": skipped,
                "day_boundary_policy": payload.get("day_boundary_policy", "civil-midnight"),
                "luck_cycles": None,
            },
            "unavailable": [
                "确定时柱",
                "含时柱的十神、藏干、五行计数与干支关系",
                "大运起点与阶段周期",
            ],
        },
        "boundary_checks": [
            {"name": "date-only-sampling", "status": "pass", "detail": f"valid_samples={len(samples)}; skipped={skipped}"},
            {"name": "internal-times-not-birth-time", "status": "pass", "detail": "sample probes are not exposed as birth time"},
        ],
        "provenance": {"generated_at": datetime.now(timezone.utc).isoformat()},
        "warnings": [
            _sampling_warning(
                precision,
                "未使用推测出生时间；本初盘只展示整日采样中稳定不变的事实和明确范围。",
            ),
            "时柱、大运起点及所有依赖时柱的综合字段已省略。",
            "这是传统历法排盘事实，不是经科学验证的人生预测。",
        ],
    }


def generate_western(payload: dict[str, Any]) -> dict[str, Any]:
    import western_engine

    birth_date = _date_text(payload.get("birth_date"), payload.get("calendar", "gregorian"))
    precision = _time_precision(payload.get("time_precision"))
    location = validate_location(payload.get("location"))
    solar_date = _solar_date_for_western(payload, birth_date)
    cached_hash = western_engine.artifact_hash()
    original_hash = western_engine.artifact_hash
    western_engine.artifact_hash = lambda: cached_hash
    samples: list[dict[str, Any]] = []
    skipped = 0
    try:
        for time_text in SAMPLE_TIMES:
            sample_payload = {
                **_sample_payload({**payload, "calendar": "gregorian"}, solar_date, time_text),
                "calendar": "gregorian",
            }
            current = _run_sample(western_engine.generate, sample_payload)
            if not current:
                skipped += 1
            samples.extend(current)
    finally:
        western_engine.artifact_hash = original_hash
    if not samples:
        raise EngineError("E_DATE_ONLY_NO_VALID_SAMPLES", "该日期没有可用的当地时间样本。", ["birth_date", "timezone"])

    planets: dict[str, dict[str, Any]] = {}
    for name in western_engine.BODIES:
        planet_id = name[0]
        possible_signs = _unique([sample["chart"]["planets"][planet_id]["sign"] for sample in samples])
        planets[planet_id] = {
            "status": "stable" if len(possible_signs) == 1 else "variable",
            "sign": possible_signs[0] if len(possible_signs) == 1 else None,
            "possible_signs": possible_signs,
        }
    return {
        "schema_version": "1.0.0",
        "engine": {
            "name": ENGINE_NAME,
            "version": ENGINE_VERSION,
            "artifact_hash": artifact_hash(),
            "underlying": f"{western_engine.ENGINE_NAME} {western_engine.ENGINE_VERSION}",
        },
        "input": {
            **_common_input(payload, birth_date, precision, location),
            "resolved_solar_date": solar_date,
        },
        "chart_system": "western",
        "chart": {
            "coverage": "date-only-sign-invariants-no-houses",
            "precision": "date-only",
            "zodiac": "tropical",
            "stable": {
                "planet_signs": {
                    key: value["sign"] for key, value in planets.items() if value["status"] == "stable"
                }
            },
            "possible": {
                "planet_signs": {
                    key: value["possible_signs"] for key, value in planets.items() if value["status"] == "variable"
                }
            },
            "planets": planets,
            "aspects": None,
            "houses": None,
            "ascendant": None,
            "details": {
                "sample_count": len(samples),
                "sample_policy": SAMPLE_POLICY,
                "skipped_nonexistent_local_times": skipped,
            },
            "unavailable": ["精确行星度数", "时间敏感相位", "上升点", "宫位"],
        },
        "boundary_checks": [
            {"name": "date-only-sampling", "status": "pass", "detail": f"valid_samples={len(samples)}; skipped={skipped}"},
            {"name": "internal-times-not-birth-time", "status": "pass", "detail": "sample probes are not exposed as birth time"},
        ],
        "provenance": {"generated_at": datetime.now(timezone.utc).isoformat()},
        "warnings": [
            _sampling_warning(
                precision,
                "未使用推测出生时间；本初盘只展示整日稳定的行星星座和明确范围。",
            ),
            "精确度数、时间敏感相位、上升点和宫位已省略。",
            "占星解释属于传统文化框架，不是经科学验证的预测。",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate date-only invariant chart facts.")
    parser.add_argument("input", type=Path)
    parser.add_argument("--system", choices=("bazi", "western"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = load_json(args.input)
        result = generate_bazi(payload) if args.system == "bazi" else generate_western(payload)
        atomic_write_json(args.output, result)
        print(json.dumps({"ok": True, "output": str(args.output)}, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(json.dumps(emit_error(exc), ensure_ascii=False, indent=2))
        return 2 if isinstance(exc, EngineError) else 3


if __name__ == "__main__":
    raise SystemExit(main())
