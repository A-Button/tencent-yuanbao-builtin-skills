#!/usr/bin/env python3
"""Resolve common Chinese city names to IANA timezones without network access.

The resolver keeps only the bundled immutable dataset in memory. Raw queries are
never written to disk or retained in a process-wide query cache.
"""

from __future__ import annotations

import argparse
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
DATA_PATH = SCRIPT_DIR / "data" / "city_timezones.zh-CN.json"
COORDINATE_PATH = SCRIPT_DIR / "data" / "city_coordinates.zh-CN.json"
COUNTRY_PARTS = frozenset(
    {
        "中国",
        "中國",
        "中华人民共和国",
        "中華人民共和國",
        "china",
        "prc",
        "cn",
    }
)
XINJIANG_CLOCK_CHOICES = (
    {
        "id": "beijing-time",
        "label": "北京时间",
        "timezone": "Asia/Shanghai",
    },
    {
        "id": "xinjiang-time",
        "label": "新疆时间",
        "timezone": "Asia/Urumqi",
    },
)


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def _query_keys(query: str) -> tuple[str, ...]:
    pieces = [
        piece.strip()
        for piece in re.split(r"[\s,，、/|;；]+", query)
        if piece.strip()
    ]
    candidates = [query, *pieces]
    result: list[str] = []
    for candidate in candidates:
        normalized = _normalize(candidate)
        if normalized and normalized not in COUNTRY_PARTS and normalized not in result:
            result.append(normalized)
    return tuple(result)


@lru_cache(maxsize=1)
def _dataset() -> dict[str, Any]:
    payload = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "1.0.0" or not isinstance(
        payload.get("records"), list
    ):
        raise RuntimeError("内置城市时区表格式无效。")
    return payload


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, tuple[dict[str, Any], str]]:
    index: dict[str, tuple[dict[str, Any], str]] = {}
    for record in _dataset()["records"]:
        aliases = record.get("aliases")
        if not isinstance(aliases, list):
            raise RuntimeError("内置城市时区表缺少 aliases。")
        for alias in aliases:
            if not isinstance(alias, str) or not alias.strip():
                raise RuntimeError("内置城市时区表包含无效 alias。")
            normalized = _normalize(alias)
            if normalized in index and index[normalized][0] != record:
                raise RuntimeError(f"内置城市时区表存在重复 alias：{alias}")
            index[normalized] = (record, alias)
    return index


def _location(record: dict[str, Any]) -> dict[str, str]:
    dataset = _dataset()
    return {
        "label": record["label"],
        "source": dataset["source"],
        "precision": record["precision"],
    }


def _provenance(matched_alias: str) -> dict[str, str]:
    dataset = _dataset()
    return {
        "method": "builtin-static-alias-match",
        "dataset": DATA_PATH.name,
        "dataset_version": dataset["dataset_version"],
        "matched_alias": matched_alias,
    }


@lru_cache(maxsize=1)
def _coordinate_dataset() -> dict[str, Any]:
    data = json.loads(COORDINATE_PATH.read_text(encoding="utf-8"))
    if data.get("schema_version") != "1.0.0" or not isinstance(data.get("records"), dict):
        raise RuntimeError("内置城市坐标表格式无效。")
    return data


def with_western_coordinates(location: dict[str, Any]) -> dict[str, Any]:
    """Enrich only an exact, canonical city from our own timezone fast path.

    Host-provided coordinates and labels are never overridden. Region-only
    records are deliberately absent: a timezone does not identify a horizon.
    """
    if location.get("source") != "builtin-city-timezone-table" or any(
        location.get(field) is not None for field in ("latitude", "longitude")
    ):
        return dict(location)
    record = _coordinate_dataset()["records"].get(location.get("label"))
    if record is None:
        return dict(location)
    return {
        **location,
        "latitude": record["latitude"],
        "longitude": record["longitude"],
        "source": "builtin-city-timezone-table; " + record.get("source", f"GeoNames:{record['geonameid']} (geonamescache 2.0.0)"),
    }


def resolve_city(query: Any) -> dict[str, Any]:
    """Return a resolved timezone, a user choice, or a closed not-found result."""
    if not isinstance(query, str) or not query.strip():
        return {
            "ok": False,
            "status": "invalid-query",
            "ambiguity_code": "timezone_unresolved",
            "error": {
                "code": "E_INVALID_CITY_QUERY",
                "message": "出生城市必须是非空文本。",
                "fields": ["birth_city_raw"],
            },
        }

    match: tuple[dict[str, Any], str] | None = None
    for key in _query_keys(query):
        match = _alias_index().get(key)
        if match is not None:
            break
    if match is None:
        return {
            "ok": False,
            "status": "not-found",
            "ambiguity_code": "timezone_unresolved",
            "error": {
                "code": "E_CITY_NOT_FOUND",
                "message": "内置城市表未命中；需要宿主位置服务补充解析。",
                "fields": ["birth_city_raw"],
            },
        }

    record, matched_alias = match
    base = {
        "location": _location(record),
        "provenance": _provenance(matched_alias),
    }
    if record.get("ambiguity_code") == "xinjiang_clock_required":
        return {
            "ok": False,
            "status": "needs-user-choice",
            "timezone": None,
            "ambiguity_code": "xinjiang_clock_required",
            "message": "新疆出生记录可能使用北京时间或新疆时间，必须先确认记录口径。",
            "choices": [dict(choice) for choice in XINJIANG_CLOCK_CHOICES],
            **base,
        }

    return {
        "ok": True,
        "status": "resolved",
        "timezone": record["timezone"],
        "ambiguity_code": None,
        **base,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a common Chinese city to an IANA timezone offline."
    )
    parser.add_argument("city")
    args = parser.parse_args()
    result = resolve_city(args.city)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
