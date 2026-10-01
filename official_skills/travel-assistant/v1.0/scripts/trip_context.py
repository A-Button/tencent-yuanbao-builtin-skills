#!/usr/bin/env python3
"""读取 travel_plan 沙箱行程，归一化成陪伴视图。

读不到文件、信封损坏或没有 trip 时返回 found=false，不抛异常。
"""

from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path
from typing import Any

DEFAULT_STORE_PATH = Path.home() / ".travel_plan" / "trip.json"


def store_path() -> Path:
    override = (os.environ.get("MY_TRAVEL_STORE") or "").strip()
    return Path(override) if override else DEFAULT_STORE_PATH


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else ""


def _location(value: object) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    try:
        lat, lng = float(value["lat"]), float(value["lng"])
    except (KeyError, TypeError, ValueError):
        return None
    if isinstance(value.get("lat"), bool) or isinstance(value.get("lng"), bool):
        return None
    if not (math.isfinite(lat) and math.isfinite(lng)):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None
    return {"lat": round(lat, 6), "lng": round(lng, 6)}


def _empty(reason: str, *, path: str = "") -> dict[str, Any]:
    result = {"found": False, "reason": reason, "days": []}
    if path:
        result["storePath"] = path
    return result


def _day_sort_key(day_id: str) -> tuple[int, str]:
    match = re.search(r"(\d+)$", day_id)
    return (int(match.group(1)), day_id) if match else (10**9, day_id)


def _normalize_stop(stop: dict[str, Any]) -> dict[str, Any] | None:
    name = _text(stop.get("name"))
    if not name:
        return None
    item: dict[str, Any] = {
        "stopId": _text(stop.get("id") or stop.get("stopId")),
        "name": name,
        "summary": _text(stop.get("summary")),
    }
    location = _location(stop.get("location"))
    if location:
        item["location"] = location
        item["coord"] = f"{location['lat']},{location['lng']}"
    address = _text(stop.get("address"))
    if address:
        item["address"] = address
    return item


def _normalize_trip(trip: dict[str, Any]) -> dict[str, Any]:
    destination = _text(trip.get("destination") or trip.get("city"))
    raw_days = trip.get("days") if isinstance(trip.get("days"), dict) else {}
    days: list[dict[str, Any]] = []
    for day_id in sorted(raw_days, key=_day_sort_key):
        day = raw_days[day_id]
        if not isinstance(day, dict):
            continue
        stops = []
        for stop in day.get("stops") or []:
            if isinstance(stop, dict):
                item = _normalize_stop(stop)
                if item:
                    stops.append(item)
        days.append({
            "dayId": day_id,
            "label": _text(day.get("label")) or day_id,
            "title": _text(day.get("title")),
            "city": _text(day.get("city")) or destination,
            "stops": stops,
        })
    return {
        "found": True,
        "reason": "ok",
        "tripId": _text(trip.get("tripId")),
        "title": _text(trip.get("title")),
        "destination": destination,
        "days": days,
    }


def load_trip_context(path: Path | None = None) -> dict[str, Any]:
    target = path or store_path()
    resolved = str(target)
    if not target.exists():
        return _empty("STORE_MISSING", path=resolved)
    try:
        raw = target.read_text(encoding="utf-8")
        if not raw.strip():
            return _empty("STORE_EMPTY", path=resolved)
        data = json.loads(raw)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _empty("STORE_UNREADABLE", path=resolved)
    if not isinstance(data, dict):
        return _empty("STORE_UNREADABLE", path=resolved)
    trip = data.get("trip") if "trip" in data else data
    if not isinstance(trip, dict) or not trip:
        return _empty("NO_TRIP", path=resolved)
    result = _normalize_trip(trip)
    result["storePath"] = resolved
    return result


def main() -> int:
    print(json.dumps(load_trip_context(), ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
