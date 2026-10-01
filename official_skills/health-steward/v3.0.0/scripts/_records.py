#!/usr/bin/env python3
"""训练 / 体重 / 档案的真源：一条记录一个 JSON 对象。

查询不直接扫这些文件。每次打开时把对象灌进一份内存 SQLite，工具仍用原来的
SQL 读法。对象在挂载卷上，按「一天一个键」落盘：

    records/readiness/2026-09-23.json
    records/sessions/2026-09-23.json      # 整场训练，动作放在同一个对象里
    records/measurements/2026-09-23.json
    records/profile.json

两个沙箱同时改同一天，会落到同一个对象，后写的赢。这是故意的：一天一条不能靠
某个沙箱本地索引里的 UNIQUE 来保证。同一场里勾完成是读出、改一项、再整份写回。

旧的 ``workout.sqlite`` 只在首次打开、且对象目录还是空的时候导入一次。导入后
打标记，原文件留着不删。
"""

from __future__ import annotations

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
