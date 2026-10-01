#!/usr/bin/env python3
"""训练 / 体重 / 档案的真源：一条记录一个 JSON 对象。

查询不直接扫这些文件。一次调用只用到的那几天灌进内存 SQLite，工具仍用原来的
SQL 读法。对象在挂载卷上，按「一天一个键」落盘：

    records/readiness/2026-09-23.json
    records/sessions/2026-09-23.json      # 整场训练，动作放在同一个对象里
    records/measurements/2026-09-23.json
    records/profile.json

两个沙箱同时改同一天，会落到同一个对象，后写的赢。这是故意的：一天一条不能靠
某个沙箱本地索引里的 UNIQUE 来保证。同一场里勾完成是读出、改一项、再整份写回。

旧的 ``workout.sqlite`` 不整库导入。某一天的 JSON 不在时，才读旧库里的那一天；
档案 JSON 不在时，才读那一行 ``body_profile``。读到不回写，原文件留着。
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

import json
import os
import sqlite3
from pathlib import Path

_MARKER = ".workout-migrated"
_DAY_KINDS = ("readiness", "sessions", "measurements")


def root_for(legacy_path: Path) -> Path:
    """对象目录跟旧库放在同一层，不跟库文件抢同一个路径。"""
    return legacy_path.parent / "records"


def object_path(root: Path, kind: str, key: str) -> Path:
    if kind == "profile":
        return root / "profile.json"
    return root / kind / f"{key}.json"


def write_object(root: Path, kind: str, key: str, payload: dict) -> None:
    path = object_path(root, kind, key)
    _atomic_write(path, json.dumps(payload, ensure_ascii=False))


def read_object(path: Path) -> dict | None:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


def iter_objects(root: Path, kind: str) -> list[dict]:
    if kind == "profile":
        payload = read_object(root / "profile.json")
        return [payload] if payload else []
    directory = root / kind
    if not directory.is_dir():
        return []
    rows = []
    for path in sorted(directory.glob("*.json")):
        if path.name.startswith("."):
            continue
        payload = read_object(path)
        if payload is not None:
            rows.append(payload)
    return rows


def has_objects(root: Path) -> bool:
    if (root / "profile.json").is_file():
        return True
    return any((root / kind).glob("*.json") for kind in _DAY_KINDS if (root / kind).is_dir())


def migrate_workout(legacy: Path, root: Path) -> None:
    """把旧的整库 SQLite 拆成对象。已有对象或已经迁过就不动。"""
    marker = root / _MARKER
    if marker.is_file() or has_objects(root):
        if not marker.is_file() and has_objects(root):
            _touch(marker)
        return
    if not legacy.is_file() or legacy.stat().st_size == 0:
        return
    try:
        connection = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
    except sqlite3.Error:
        return
    connection.row_factory = sqlite3.Row
    try:
        sessions = _rows(connection, "sessions")
        exercises = _rows(connection, "session_exercises")
        by_session: dict[str, list[dict]] = {}
        for row in exercises:
            by_session.setdefault(str(row.get("session_id")), []).append(row)
        for session in sessions:
            day = str(session.get("date") or "")
            if not day:
                continue
            write_object(root, "sessions", day, {**session, "exercises": by_session.get(str(session.get("id")), [])})
        for kind, table in (("readiness", "readiness"), ("measurements", "measurements")):
            for row in _rows(connection, table):
                day = str(row.get("date") or "")
                if day:
                    write_object(root, kind, day, row)
        profiles = _rows(connection, "body_profile")
        if profiles:
            write_object(root, "profile", "default", profiles[0])
    except sqlite3.Error:
        return
    finally:
        connection.close()
    _touch(marker)


def _rows(connection: sqlite3.Connection, table: str) -> list[dict]:
    try:
        found = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
    except sqlite3.Error:
        return []
    if found is None:
        return []
    return [dict(row) for row in connection.execute(f"SELECT * FROM {table}").fetchall()]


def _atomic_write(dst: Path, text: str) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    staging = dst.parent / f".{dst.name}.{os.getpid()}.tmp"
    try:
        staging.write_text(text, encoding="utf-8")
        os.replace(staging, dst)
    except OSError:
        staging.unlink(missing_ok=True)
        raise


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("ok\n", encoding="utf-8")


def list_dates(root: Path | None, kind: str) -> list[str]:
    if root is None:
        return []
    directory = root / kind
    if not directory.is_dir():
        return []
    return sorted(
        path.stem for path in directory.glob("*.json")
        if path.is_file() and not path.name.startswith(".")
    )


def _legacy_connect(legacy: Path | None) -> sqlite3.Connection | None:
    """只读打开旧库。文件不在就不创建。"""
    if legacy is None or not legacy.is_file() or legacy.stat().st_size == 0:
        return None
    try:
        connection = sqlite3.connect(f"file:{legacy}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    connection.row_factory = sqlite3.Row
    return connection


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    try:
        found = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
    except sqlite3.Error:
        return False
    return found is not None


_LEGACY_TABLE = {
    "readiness": "readiness",
    "measurements": "measurements",
    "sessions": "sessions",
}


def read_legacy_day(legacy: Path | None, kind: str, day: str) -> dict | None:
    """旧库里的这一天。不把别的日子读出来，也不写 JSON。"""
    table = _LEGACY_TABLE.get(kind)
    connection = _legacy_connect(legacy)
    if connection is None or table is None:
        if connection is not None:
            connection.close()
        return None
    try:
        if not _table_exists(connection, table):
            return None
        row = connection.execute(f"SELECT * FROM {table} WHERE date = ?", (day,)).fetchone()
        if row is None:
            return None
        obj = dict(row)
        if kind == "sessions" and _table_exists(connection, "session_exercises"):
            exercises = connection.execute(
                "SELECT * FROM session_exercises WHERE session_id = ? ORDER BY position, created_at",
                (obj.get("id"),),
            ).fetchall()
            obj["exercises"] = [dict(item) for item in exercises]
        return obj
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def legacy_dates(legacy: Path | None, table: str) -> list[str]:
    if table not in _LEGACY_TABLE.values():
        return []
    connection = _legacy_connect(legacy)
    if connection is None:
        return []
    try:
        if not _table_exists(connection, table):
            return []
        return [
            str(row[0]) for row in connection.execute(f"SELECT date FROM {table}").fetchall()
            if row[0]
        ]
    except sqlite3.Error:
        return []
    finally:
        connection.close()


def read_legacy_profile(legacy: Path | None) -> dict | None:
    connection = _legacy_connect(legacy)
    if connection is None:
        return None
    try:
        if not _table_exists(connection, "body_profile"):
            return None
        row = connection.execute("SELECT * FROM body_profile LIMIT 1").fetchone()
        return dict(row) if row is not None else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def read_legacy_session(legacy: Path | None, session_id: str) -> dict | None:
    if not session_id:
        return None
    connection = _legacy_connect(legacy)
    if connection is None:
        return None
    try:
        if not _table_exists(connection, "sessions"):
            return None
        row = connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        obj = dict(row)
        if _table_exists(connection, "session_exercises"):
            exercises = connection.execute(
                "SELECT * FROM session_exercises WHERE session_id = ? ORDER BY position, created_at",
                (session_id,),
            ).fetchall()
            obj["exercises"] = [dict(item) for item in exercises]
        return obj
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def read_legacy_exercise(legacy: Path | None, exercise_id: str) -> dict | None:
    if not exercise_id:
        return None
    connection = _legacy_connect(legacy)
    if connection is None:
        return None
    try:
        if not _table_exists(connection, "session_exercises"):
            return None
        row = connection.execute(
            "SELECT * FROM session_exercises WHERE id = ?", (exercise_id,)
        ).fetchone()
        return dict(row) if row is not None else None
    except sqlite3.Error:
        return None
    finally:
        connection.close()


def merged_dates(root: Path | None, legacy: Path | None, kind: str, table: str) -> set[str]:
    dates = set(list_dates(root, kind))
    dates.update(legacy_dates(legacy, table))
    return dates


def count_exercises(root: Path | None, legacy: Path | None, session_dates: set[str]) -> int:
    """JSON 里的训练按对象数动作；只存在于旧库的那些日子再去旧库计数。"""
    total = 0
    json_dates: set[str] = set()
    if root is not None:
        directory = root / "sessions"
        if directory.is_dir():
            for path in directory.glob("*.json"):
                if not path.is_file() or path.name.startswith("."):
                    continue
                json_dates.add(path.stem)
                obj = read_object(path)
                total += len((obj or {}).get("exercises") or [])
    outside = [day for day in session_dates if day not in json_dates]
    total += _legacy_exercise_count(legacy, outside)
    return total


def _legacy_exercise_count(legacy: Path | None, dates: list[str]) -> int:
    if not dates:
        return 0
    connection = _legacy_connect(legacy)
    if connection is None:
        return 0
    try:
        if not _table_exists(connection, "sessions") or not _table_exists(connection, "session_exercises"):
            return 0
        placeholders = ", ".join("?" for _ in dates)
        row = connection.execute(
            "SELECT COUNT(*) FROM session_exercises AS exercise"
            " JOIN sessions AS session ON session.id = exercise.session_id"
            f" WHERE session.date IN ({placeholders})",
            tuple(dates),
        ).fetchone()
        return int(row[0]) if row is not None else 0
    except sqlite3.Error:
        return 0
    finally:
        connection.close()
