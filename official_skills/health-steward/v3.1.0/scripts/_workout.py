#!/usr/bin/env python3
"""运动训练的共享层（SQLite 版），供 scripts/ 下十个 tool 脚本共用。

它自己不是 tool，不出现在 app.yaml 里。里面是四类东西：

* 存储：``Store`` 五张表的行级读写、``_connect`` 建表、``_store_lock`` 并发控制
* 判定：``advice_for`` —— 身体状态给出的训练建议，规则写死在这里，不交给模型
* 资料：``assets/exercise_library.json`` 的读取与索引（随包静态数据，不是用户数据）
* 收尾：``execute`` 解析入参、拿锁、调 handler、补全量快照；``run`` 把它打成一行 JSON

真源在 ``records/`` 下，一条记录一个 JSON 对象（一天一条的用日期当文件名，
档案是 ``profile.json``）。每次调用把这些对象灌进内存 SQLite 再查——SQLite 只做
查询面，不放在挂载卷上。旧的 ``workout.sqlite`` 首次打开时拆成对象，原文件保留。

数据根仍是 ``/data/user/health-assistant/``。沙箱里选它而不是 ``~/``，是因为 Agent
沙箱与 App 沙箱各有各的 home，但挂的是同一份 ``/data/user``。本地没有这个挂载时
退到 ``~/.one-agent/data/``。同一沙箱里的并发用 ``/tmp`` 上的 flock；两个沙箱同时
写同一天会落到同一个对象，后写的赢。

换领域模型时，``CREATE TABLE`` 与各张表的 ``*_COLUMNS`` 要一起改：``new_record()``
产出的字段必须和表的列对得上，否则 ``insert`` 会在 SQL 层报错。
"""

from __future__ import annotations

import calendar
import contextlib
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import sys
import time
import traceback
import uuid
from datetime import date as date_cls
from datetime import datetime, timezone
from pathlib import Path

import _records
from _errors import ActionError

DEFAULT_DATA_DIR = "/data/user"
LOCAL_DATA_DIR = "~/.one-agent/data"
STORE_FILENAME = "workout.sqlite"
APP_ID = "health-assistant"
_LOCK_DIR = os.environ.get("HEALTH_ASSISTANT_LOCK_DIR", "/tmp")
_LOCK_TIMEOUT = float(os.environ.get("HEALTH_ASSISTANT_LOCK_TIMEOUT", "30"))

# 列顺序即出参里字段的顺序，UI 直接按它渲染。
READINESS_COLUMNS = (
    "id", "date", "fatigue", "soreness", "advice", "created_at", "updated_at",
)
SESSION_COLUMNS = (
    "id", "date", "plan_name", "cycle_index", "cycle_size", "status", "created_at", "updated_at",
)
EXERCISE_COLUMNS = (
    "id", "session_id", "exercise_key", "name", "sets", "reps", "load_text", "done", "position",
    "created_at", "updated_at",
)
MEASUREMENT_COLUMNS = (
    "id", "date", "waist_cm", "hip_cm", "thigh_cm", "weight_kg", "created_at", "updated_at",
)
BODY_PROFILE_COLUMNS = (
    "id", "sex", "height_cm", "age", "activity_level", "created_at", "updated_at",
)
BODY_PROFILE_ID = "default"

# 身体状态的取值域。这三张表既是 app.yaml 里 enum 的真源，也是 handler 兜底时的判据。
SORENESS_PARTS = (
    "neck", "shoulder", "chest", "back", "waist", "hip", "thigh_front", "thigh_back", "calf",
)
SORENESS_LEVELS = ("mild", "moderate", "severe")
# 「中度及以上」——advice 判定第二档只认这两级。
HEAVY_SORENESS = frozenset(("moderate", "severe"))
ADVICES = ("normal", "reduced", "rest")

# 身体档案取值域（没有体重——体重是一天一条的测量）。
SEXES = ("male", "female")
ACTIVITY_LEVELS = ("sedentary", "light", "moderate")

# 围度 / 体重：part 名 → measurements 表的列名。体重是一天一条，不进身体档案。
MEASUREMENT_PARTS = {
    "waist": "waist_cm", "hip": "hip_cm", "thigh": "thigh_cm", "weight": "weight_kg",
}
MEASUREMENT_UNITS = {"waist": "cm", "hip": "cm", "thigh": "cm", "weight": "kg"}
DEFAULT_TREND_PART = "waist"
DEFAULT_TREND_WEEKS = 5
MIN_TREND_WEEKS = 2
MAX_TREND_WEEKS = 52

_LIBRARY_PATH = Path(__file__).resolve().parents[1] / "assets" / "exercise_library.json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def today_iso() -> str:
    """本地日历日。持久化用不带时区的 ``YYYY-MM-DD``，因为「哪一天训练的」是日历概念。"""
    return datetime.now().astimezone().strftime("%Y-%m-%d")


def _resolve_store_path(environ: dict[str, str] | None = None) -> Path:
    """显式文件 > 环境变量指定的数据根 > 持久卷 /data/user > 本地 ~/.one-agent/data。

    环境变量仅供测试与特殊部署，正常运行两条真实分支就够：沙箱里 ``/data/user``
    是按用户挂载的持久卷，本地跑没有这个挂载，退到用户目录。判断的是挂载点本身
    存在与否，而不是 ``<app-id>`` 子目录——子目录首次写入时才建。
    """
    env = os.environ if environ is None else environ
    explicit = (env.get("HEALTH_ASSISTANT_STORE") or "").strip()
    if explicit:
        return Path(explicit)
    override = (
        env.get("HEALTH_ASSISTANT_DATA_DIR") or env.get("ONEAGENT_APP_DATA_DIR") or ""
    ).strip()
    root = Path(override) if override else _data_root()
    return root / APP_ID / STORE_FILENAME


def _data_root() -> Path:
    # 挂载点不在就退到本地：此时创建 /data/user 只会写进容器本地盘，数据不持久，
    # 还不如落在用户目录里。
    persistent = Path(DEFAULT_DATA_DIR)
    if persistent.is_dir():
        return persistent
    return Path(LOCAL_DATA_DIR).expanduser()


def _lock_path(store_path: Path) -> Path:
    """锁文件跟着库文件走，但放在本地盘：COS fuse 上 flock 不可靠。"""
    digest = hashlib.sha256(str(store_path).encode("utf-8")).hexdigest()[:16]
    return Path(_LOCK_DIR) / f"{APP_ID}-{digest}.lock"


@contextlib.contextmanager
def _store_lock(store_path: Path):
    lock_file = _lock_path(store_path)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + _LOCK_TIMEOUT
    with open(lock_file, "a+", encoding="utf-8") as handle:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise ActionError("STORE_BUSY", "数据正被其它操作占用，请稍后重试。")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


# 一天一条的两张表（readiness / measurements）靠 date 上的唯一索引兜住，
# 重复提交走「读出来改字段再写回」，不会堆出两行。
_READINESS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS readiness (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL UNIQUE,
        fatigue INTEGER NOT NULL,
        soreness TEXT NOT NULL DEFAULT '[]',
        advice TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """

_SCHEMA = (
    _READINESS_SCHEMA,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL UNIQUE,
        plan_name TEXT NOT NULL,
        cycle_index INTEGER NOT NULL,
        cycle_size INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS session_exercises (
        id TEXT PRIMARY KEY,
        session_id TEXT NOT NULL,
        exercise_key TEXT NOT NULL,
        name TEXT NOT NULL,
        sets INTEGER NOT NULL,
        reps INTEGER NOT NULL,
        load_text TEXT NOT NULL DEFAULT '',
        done INTEGER NOT NULL DEFAULT 0,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS measurements (
        id TEXT PRIMARY KEY,
        date TEXT NOT NULL UNIQUE,
        waist_cm REAL,
        hip_cm REAL,
        thigh_cm REAL,
        weight_kg REAL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS body_profile (
        id TEXT PRIMARY KEY,
        sex TEXT NOT NULL,
        height_cm REAL NOT NULL,
        age INTEGER NOT NULL,
        activity_level TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_exercises_session ON session_exercises (session_id, position)",
)


def _ensure_measurement_columns(connection: sqlite3.Connection) -> None:
    """已有库补 weight_kg。新建表的 CREATE 已带这一列，PRAGMA 里有就跳过。"""
    existing = {
        row[1] for row in connection.execute("PRAGMA table_info(measurements)").fetchall()
    }
    if "weight_kg" not in existing:
        connection.execute("ALTER TABLE measurements ADD COLUMN weight_kg REAL")


def _remove_legacy_sleep_quality(connection: sqlite3.Connection) -> None:
    """旧版本 readiness 多一列睡眠评分；重建表时保留其它训练状态数据。"""
    existing = {
        row[1] for row in connection.execute("PRAGMA table_info(readiness)").fetchall()
    }
    legacy_column = "sleep_quality"
    if legacy_column not in existing:
        return
    connection.execute("ALTER TABLE readiness RENAME TO readiness_legacy")
    connection.execute(_READINESS_SCHEMA)
    columns = ", ".join(READINESS_COLUMNS)
    connection.execute(
        f"INSERT INTO readiness ({columns}) SELECT {columns} FROM readiness_legacy"
    )
    connection.execute("DROP TABLE readiness_legacy")


@contextlib.contextmanager
def _connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        connection = sqlite3.connect(path, timeout=_LOCK_TIMEOUT)
    except sqlite3.Error as exc:
        raise ActionError("STORE_UNAVAILABLE", f"打不开数据库：{exc}") from exc
    connection.row_factory = sqlite3.Row
    try:
        # 建表放在每次连接：首次调用就能用，不需要额外的迁移步骤。
        for statement in _SCHEMA:
            connection.execute(statement)
        _remove_legacy_sleep_quality(connection)
        _ensure_measurement_columns(connection)
        connection.commit()
        yield connection
    except sqlite3.DatabaseError as exc:
        connection.rollback()
        raise ActionError("STORE_CORRUPTED", f"数据库损坏或不可读：{exc}") from exc
    finally:
        connection.close()


class Store:
    """一次调用期间的数据视图，增删改都是行级 SQL，立即 commit。

    五张表各自一组读写方法，没有通用 CRUD：表之间的键和一天一条的约束不一样，
    抽成一套反而要在调用处重新分辨。
    """

    def __init__(self, connection: sqlite3.Connection, records_root: Path | None = None):
        self._connection = connection
        self._records = records_root

    def _one(self, table: str, columns: tuple, where: str, params: tuple) -> dict | None:
        cursor = self._connection.execute(
            f"SELECT {', '.join(columns)} FROM {table} WHERE {where}", params
        )
        row = cursor.fetchone()
        return dict(row) if row is not None else None

    def _insert(self, table: str, columns: tuple, record: dict) -> None:
        self._connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)})"
            f" VALUES ({', '.join('?' for _ in columns)})",
            tuple(record.get(column) for column in columns),
        )
        self._connection.commit()
        self._persist(table, record)

    def _update(self, table: str, columns: tuple, record: dict) -> None:
        assignments = ", ".join(f"{column} = ?" for column in columns if column != "id")
        self._connection.execute(
            f"UPDATE {table} SET {assignments} WHERE id = ?",
            tuple(record.get(column) for column in columns if column != "id") + (record["id"],),
        )
        self._connection.commit()
        self._persist(table, record)

    def _persist(self, table: str, record: dict) -> None:
        """SQL 改完立刻把对应的那一个对象写回挂载卷。内存库只活这一次调用。"""
        root = self._records
        if root is None:
            return
        if table == "readiness":
            _records.write_object(root, "readiness", record["date"], self.readiness_on(record["date"]) or record)
        elif table == "measurements":
            _records.write_object(root, "measurements", record["date"], self.measurement_on(record["date"]) or record)
        elif table == "body_profile":
            _records.write_object(root, "profile", "default", self.body_profile() or record)
        elif table in ("sessions", "session_exercises"):
            session_id = record["id"] if table == "sessions" else record["session_id"]
            session = self.session(session_id)
            if session is None:
                return
            _records.write_object(
                root, "sessions", session["date"],
                {**session, "exercises": self.exercises_of(session_id)},
            )

    # --- readiness：一天一条 -------------------------------------------------

    def readiness_on(self, day: str) -> dict | None:
        return self._one("readiness", READINESS_COLUMNS, "date = ?", (day,))

    def save_readiness(self, record: dict) -> None:
        if self.readiness_on(record["date"]) is None:
            self._insert("readiness", READINESS_COLUMNS, record)
        else:
            self._update("readiness", READINESS_COLUMNS, record)

    # --- sessions 与它的动作行 -----------------------------------------------

    def session_on(self, day: str) -> dict | None:
        return self._one("sessions", SESSION_COLUMNS, "date = ?", (day,))

    def session(self, session_id: str) -> dict | None:
        return self._one("sessions", SESSION_COLUMNS, "id = ?", (session_id,))

    def require_session(self, session_id: str) -> dict:
        record = self.session(session_id)
        if record is None:
            raise ActionError("NOT_FOUND", f"未找到训练：{session_id}")
        return record

    def insert_session(self, record: dict) -> None:
        self._insert("sessions", SESSION_COLUMNS, record)

    def replace_session(self, record: dict) -> None:
        self._update("sessions", SESSION_COLUMNS, record)

    def sessions_between(self, start: str, end: str) -> list[dict]:
        """左闭右开的日期区间，跨月/跨年都靠它，不做字符串前缀匹配。"""
        cursor = self._connection.execute(
            f"SELECT {', '.join(SESSION_COLUMNS)} FROM sessions"
            " WHERE date >= ? AND date < ? ORDER BY date",
            (start, end),
        )
        return [dict(row) for row in cursor.fetchall()]

    def exercises_of(self, session_id: str) -> list[dict]:
        cursor = self._connection.execute(
            f"SELECT {', '.join(EXERCISE_COLUMNS)} FROM session_exercises"
            " WHERE session_id = ? ORDER BY position, created_at",
            (session_id,),
        )
        return [dict(row) for row in cursor.fetchall()]

    def exercise(self, exercise_id: str) -> dict | None:
        return self._one("session_exercises", EXERCISE_COLUMNS, "id = ?", (exercise_id,))

    def require_exercise(self, exercise_id: str) -> dict:
        record = self.exercise(exercise_id)
        if record is None:
            raise ActionError("NOT_FOUND", f"未找到动作：{exercise_id}")
        return record

    def insert_exercise(self, record: dict) -> None:
        self._insert("session_exercises", EXERCISE_COLUMNS, record)

    def replace_exercise(self, record: dict) -> None:
        self._update("session_exercises", EXERCISE_COLUMNS, record)

    # --- measurements：一天一条 ----------------------------------------------

    def measurement_on(self, day: str) -> dict | None:
        return self._one("measurements", MEASUREMENT_COLUMNS, "date = ?", (day,))

    def save_measurement(self, record: dict) -> None:
        if self.measurement_on(record["date"]) is None:
            self._insert("measurements", MEASUREMENT_COLUMNS, record)
        else:
            self._update("measurements", MEASUREMENT_COLUMNS, record)

    def measurement_points(self, part: str, limit: int) -> list[dict]:
        """某一项围度最近 ``limit`` 个有值的记录，返回时按日期升序。

        取最近 N 条而不是整表，是为了记录攒到几百周以后趋势图仍然只带回要画的点。
        """
        column = MEASUREMENT_PARTS[part]
        cursor = self._connection.execute(
            f"SELECT date, {column} AS value FROM measurements"
            f" WHERE {column} IS NOT NULL ORDER BY date DESC LIMIT ?",
            (limit,),
        )
        rows = [dict(row) for row in cursor.fetchall()]
        rows.reverse()
        return rows

    def latest_measurements(self) -> dict:
        """各项各自最近一次有值的记录。各项可以记在不同日期，所以要分别取。"""
        latest = {}
        for part in MEASUREMENT_PARTS:
            points = self.measurement_points(part, 1)
            latest[part] = points[0] if points else None
        return latest

    def latest_weight_on_or_before(self, day: str) -> float | None:
        """``day`` 当天或更早最近一条体重。基础代谢用它，不读未来日期的数。"""
        cursor = self._connection.execute(
            "SELECT weight_kg FROM measurements"
            " WHERE date <= ? AND weight_kg IS NOT NULL"
            " ORDER BY date DESC LIMIT 1",
            (day,),
        )
        row = cursor.fetchone()
        return None if row is None else float(row["weight_kg"])

    def weight_rows_between(self, start: str, end: str) -> list[dict]:
        """闭区间 ``[start, end]`` 内有体重的日子（一天一行）。"""
        cursor = self._connection.execute(
            "SELECT date, weight_kg FROM measurements"
            " WHERE weight_kg IS NOT NULL AND date >= ? AND date <= ?"
            " ORDER BY date",
            (start, end),
        )
        return [
            {"date": row["date"], "weight_kg": float(row["weight_kg"])}
            for row in cursor.fetchall()
        ]

    # --- body_profile：单行慢变量（无体重） ----------------------------------

    def body_profile(self) -> dict | None:
        return self._one("body_profile", BODY_PROFILE_COLUMNS, "id = ?", (BODY_PROFILE_ID,))

    def save_body_profile(self, record: dict) -> None:
        record = {**record, "id": BODY_PROFILE_ID}
        if self.body_profile() is None:
            self._insert("body_profile", BODY_PROFILE_COLUMNS, record)
        else:
            self._update("body_profile", BODY_PROFILE_COLUMNS, record)

    def counts(self) -> dict:
        totals = {}
        for table in ("readiness", "sessions", "session_exercises", "measurements"):
            cursor = self._connection.execute(f"SELECT COUNT(*) AS n FROM {table}")
            totals[table] = int(cursor.fetchone()["n"])
        return totals


def new_record(**fields: object) -> dict:
    """补上 id 与时间戳。id 由服务端生成，模型与 UI 都只能复用返回值里的那个。"""
    now = _now_iso()
    return {"id": uuid.uuid4().hex, "created_at": now, "updated_at": now, **fields}


def touch(record: dict) -> dict:
    record["updated_at"] = _now_iso()
    return record


# --- 入参兜底 --------------------------------------------------------------
# 字段是否存在、类型、枚举、数值范围都写在 app.yaml 的 inputSchema 里，由 CLI 拦。
# 这里只补两类 CLI 表达不了的：一是「去掉空白后不能为空」（CLI 不实现 pattern），
# 二是日期这种要真正解析才知道合不合法的格式。另外 handler 也会被单测直接调用，
# 那条路径没有 CLI，所以取值前仍要确认类型对得上，否则会崩在 TypeError 上、
# 连错误信封都打不出来。


def require_text(args: dict, name: str) -> str:
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ActionError("INVALID_ARGUMENT", f"缺少参数：{name}")
    return value.strip()


def require_int(args: dict, name: str, low: int, high: int) -> int:
    value = args.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ActionError("INVALID_ARGUMENT", f"{name} 必须是 {low}–{high} 的整数。")
    if not low <= value <= high:
        raise ActionError("INVALID_ARGUMENT", f"{name} 超出范围 {low}–{high}：{value}")
    return value


def optional_number(args: dict, name: str, low: float, high: float) -> float | None:
    value = args.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ActionError("INVALID_ARGUMENT", f"{name} 必须是数字。")
    if not low <= float(value) <= high:
        raise ActionError("INVALID_ARGUMENT", f"{name} 超出范围 {low}–{high}：{value}")
    return round(float(value), 1)


def optional_date(args: dict, name: str = "date") -> str:
    """不传就是今天。传了必须是能真正解析出来的 ``YYYY-MM-DD``。"""
    raw = args.get(name)
    if raw is None:
        return today_iso()
    if not isinstance(raw, str):
        raise ActionError("INVALID_ARGUMENT", f"{name} 必须是 YYYY-MM-DD 格式的日期。")
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").strftime("%Y-%m-%d")
    except ValueError:
        raise ActionError("INVALID_ARGUMENT", f"{name} 不是合法日期：{raw}") from None


def require_month(args: dict, name: str = "month") -> str:
    raw = args.get(name)
    if not isinstance(raw, str):
        raise ActionError("INVALID_ARGUMENT", f"{name} 必须是 YYYY-MM 格式的月份。")
    try:
        return datetime.strptime(raw.strip(), "%Y-%m").strftime("%Y-%m")
    except ValueError:
        raise ActionError("INVALID_ARGUMENT", f"{name} 不是合法月份：{raw}") from None


def month_bounds(month: str) -> tuple[str, str]:
    """返回左闭右开区间 ``[当月 1 日, 次月 1 日)``。12 月要进位到次年，所以不用字符串拼。"""
    year, index = int(month[:4]), int(month[5:7])
    start = date_cls(year, index, 1)
    end = date_cls(year + 1, 1, 1) if index == 12 else date_cls(year, index + 1, 1)
    return start.isoformat(), end.isoformat()


def normalize_soreness(raw: object) -> list[dict]:
    """把入参里的酸痛清单整理成 ``[{"part","level"}]``，同一部位后来的覆盖先前的。

    ``level`` 不填按最轻的 ``mild`` 记——不填不该被当成严重，否则会把 advice 推到
    减量档去。
    """
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ActionError("INVALID_ARGUMENT", "soreness 必须是数组。")
    merged: dict[str, str] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise ActionError("INVALID_ARGUMENT", "soreness 的每一项必须是对象。")
        part = item.get("part")
        if part not in SORENESS_PARTS:
            raise ActionError(
                "INVALID_ARGUMENT", f"soreness.part 只能取 {'/'.join(SORENESS_PARTS)}：{part}"
            )
        level = item.get("level") or "mild"
        if level not in SORENESS_LEVELS:
            raise ActionError(
                "INVALID_ARGUMENT", f"soreness.level 只能取 {'/'.join(SORENESS_LEVELS)}：{level}"
            )
        merged[part] = level
    return [{"part": part, "level": merged[part]} for part in SORENESS_PARTS if part in merged]


def advice_for(fatigue: int, soreness: list[dict]) -> str:
    """身体状态 → 训练建议。这条判定是本包存在的意义之一，不能交给模型自己想。

    三档按顺序短路，互斥且完备：

    1. 疲劳 >= 4                           → ``rest``（今日休息）
    2. 疲劳 == 3 **或** 有中度及以上酸痛  → ``reduced``（减量训练）
    3. 其余                                → ``normal``（正常训练）

    第 1 条优先于第 2 条：高疲劳加上重度酸痛仍然是休息，不会被降级成减量。
    轻微酸痛不影响判定，它只是记录。规则改动必须同步 SKILL.md 与 tests/test_api.py。
    """
    if fatigue >= 4:
        return "rest"
    if fatigue == 3 or any(item["level"] in HEAVY_SORENESS for item in soreness):
        return "reduced"
    return "normal"


# --- 随包动作资料 ----------------------------------------------------------

_library_cache: list[dict] | None = None


def exercise_library() -> list[dict]:
    """读 assets/exercise_library.json。静态资料，进程内读一次就够。"""
    global _library_cache
    if _library_cache is None:
        try:
            parsed = json.loads(_LIBRARY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ActionError("LIBRARY_UNAVAILABLE", f"动作资料读不出来：{exc}") from exc
        entries = parsed.get("exercises") if isinstance(parsed, dict) else parsed
        if not isinstance(entries, list) or not entries:
            raise ActionError("LIBRARY_UNAVAILABLE", "动作资料为空。")
        _library_cache = entries
    return _library_cache


def library_entry(key: str) -> dict | None:
    return next((item for item in exercise_library() if item.get("key") == key), None)


def require_library_entry(key: str) -> dict:
    entry = library_entry(key)
    if entry is None:
        known = "、".join(item["key"] for item in exercise_library())
        raise ActionError("NOT_FOUND", f"动作资料里没有 {key}，可选：{known}")
    return entry


def rep_unit_of(key: str) -> str:
    """次数的单位是动作自带的属性（登山跑按秒、硬拉按次），所以查资料而不是存库。"""
    entry = library_entry(key)
    return (entry or {}).get("rep_unit") or "次"


# --- 排动作、找动作 ----------------------------------------------------------
# plan_session / add_exercise 建动作行，complete_exercise / update_exercise_setting /
# get_exercise_detail 找动作行，都走这里，免得五个脚本各抄一份口径。

MAX_SETS = 20
MAX_REPS = 300
MAX_PER_SESSION = 20


def check_exercise_keys(raw: list) -> None:
    """一次把不认识的动作 key 全报出来，不是撞一个报一个。"""
    unknown = []
    for item in raw:
        if not isinstance(item, dict):
            raise ActionError("INVALID_ARGUMENT", "exercises 的每一项必须是对象。")
        key = require_text(item, "exercise_key")
        if library_entry(key) is None and key not in unknown:
            unknown.append(key)
    if unknown:
        known = "、".join(item["key"] for item in exercise_library())
        raise ActionError("NOT_FOUND", f"动作资料里没有 {'、'.join(unknown)}，可选：{known}")


def exercise_row(item: dict, session_id: str, position: int) -> dict:
    """一条动作：没给的字段用随包资料里的默认值补齐，不让模型为了排训练背参数。"""
    entry = require_library_entry(require_text(item, "exercise_key"))
    filled = {
        "name": item.get("name") or entry["name"],
        "sets": item.get("sets", entry["default_sets"]),
        "reps": item.get("reps", entry["default_reps"]),
    }
    return new_record(
        session_id=session_id,
        exercise_key=entry["key"],
        name=require_text(filled, "name"),
        sets=require_int(filled, "sets", 1, MAX_SETS),
        reps=require_int(filled, "reps", 1, MAX_REPS),
        load_text=str(item.get("load_text", entry["default_load_text"]) or "").strip(),
        done=0,
        position=position,
    )


def append_exercises(store: Store, session: dict, raw: list) -> list[dict]:
    """往已有的一场末尾追加动作，已有的几条一个字段都不动。

    先把整批行都建好再写：第二条参数不对时，第一条不会已经落了库。
    整场已经收场（status=done）又加了新动作，就重新打开，月历上才不会显示已完成。
    """
    check_exercise_keys(raw)
    existing = store.exercises_of(session["id"])
    if len(existing) + len(raw) > MAX_PER_SESSION:
        raise ActionError(
            "TOO_MANY_EXERCISES",
            f"一场最多 {MAX_PER_SESSION} 个动作，今天已有 {len(existing)} 个，"
            f"这次要加 {len(raw)} 个。",
        )
    start = max((int(item["position"]) for item in existing), default=-1) + 1
    rows = [exercise_row(item, session["id"], start + offset) for offset, item in enumerate(raw)]
    for row in rows:
        store.insert_exercise(row)
    if session.get("status") == "done":
        session["status"] = "pending"
        store.replace_session(touch(session))
    return rows


def session_for(store: Store, args: dict) -> dict:
    """给了 session_id 就用它；没给就取 date（缺省今天）那一场。"""
    session_id = args.get("session_id")
    if isinstance(session_id, str) and session_id.strip():
        return store.require_session(session_id.strip())
    day = optional_date(args)
    session = store.session_on(day)
    if session is None:
        raise ActionError("SESSION_NOT_FOUND", f"{day} 还没有安排训练，先用 workout_plan 排一场。")
    return session


_ORDINAL_RE = re.compile(r"^第\s*(\d+)\s*个(?:动作)?$")
_NAME_NOISE_RE = re.compile(r"[\s「」『』“”\"'()（）【】\[\]·•、，,。.]+")


def _norm_name(value: object) -> str:
    return _NAME_NOISE_RE.sub("", str(value or "")).lower()


def match_by_name(rows: list[dict], name: str) -> tuple[dict | None, str | None]:
    """按名字找一行：先全名，再唯一的包含关系。找不到或对上多个都返回原因，不猜。

    同名的有好几条（同一个动作加过两次）时，优先还没做完的那条。
    """
    target = _norm_name(name)
    if not target:
        return None, "动作名是空的"
    exact = [row for row in rows if _norm_name(row.get("name")) == target]
    if exact:
        return next((row for row in exact if not row.get("done")), exact[0]), None
    fuzzy = [
        row for row in rows
        if target in _norm_name(row.get("name")) or _norm_name(row.get("name")) in target
    ]
    if len(fuzzy) == 1:
        return fuzzy[0], None
    if not fuzzy:
        return None, f"没有叫「{name}」的动作"
    options = "、".join(str(row.get("name")) for row in fuzzy)
    return None, f"「{name}」能对上好几个：{options}，用 positions 指明是第几个"


def ordinal_of(value: object) -> int | None:
    """「第2个动作」「第 2 个」→ 2。卡片「查要领」递进来的就是这种说法。"""
    match = _ORDINAL_RE.match(str(value or "").strip())
    return int(match.group(1)) if match else None


def _listing(rows: list[dict]) -> str:
    return "；".join(f"{index}. {row['name']}" for index, row in enumerate(rows, start=1)) or "（空）"


def pick_exercises(store: Store, session: dict, args: dict, *, single: bool = False) -> list[dict]:
    """按 exercise_id、names / name、positions / position 找到要操作的动作行。

    position 从 1 数，是排期原顺序里的第几个——卡面露的就是前三个，所以跟卡上
    「第 N 个」对得上。找不到的名字、越界的序号一次全报出来，并附上今天的清单，
    不做部分写入。
    """
    rows = store.exercises_of(session["id"])
    picked: list[dict] = []
    problems: list[str] = []

    exercise_id = args.get("exercise_id")
    if isinstance(exercise_id, str) and exercise_id.strip():
        exercise = store.require_exercise(exercise_id.strip())
        if exercise["session_id"] != session["id"]:
            raise ActionError(
                "SESSION_MISMATCH", f"动作 {exercise['id']} 不属于训练 {session['id']}。"
            )
        picked.append(exercise)

    names = args.get("names")
    if names is None and args.get("name") is not None:
        names = [args["name"]]
    positions = args.get("positions")
    if positions is None and args.get("position") is not None:
        positions = [args["position"]]
    if names is not None and not isinstance(names, list):
        raise ActionError("INVALID_ARGUMENT", "names 必须是字符串数组。")
    if positions is not None and not isinstance(positions, list):
        raise ActionError("INVALID_ARGUMENT", "positions 必须是整数数组。")

    for name in names or []:
        ordinal = ordinal_of(name)
        if ordinal is not None:
            positions = [*(positions or []), ordinal]
            continue
        row, problem = match_by_name(rows, str(name))
        if problem:
            problems.append(problem)
        else:
            picked.append(row)
    for position in positions or []:
        if isinstance(position, bool) or not isinstance(position, int):
            problems.append(f"positions 里的 {position!r} 不是整数")
        elif not 1 <= position <= len(rows):
            problems.append(f"没有第 {position} 个动作（今天共 {len(rows)} 个）")
        else:
            picked.append(rows[position - 1])

    if problems:
        raise ActionError(
            "INVALID_ARGUMENT", "；".join(problems) + f"。今天的动作：{_listing(rows)}"
        )
    unique: list[dict] = []
    for row in picked:
        if all(row["id"] != seen["id"] for seen in unique):
            unique.append(row)
    if not unique:
        raise ActionError(
            "INVALID_ARGUMENT",
            f"要指明是哪个动作：names（动作名）或 positions（第几个，从 1 数）。今天的动作：{_listing(rows)}",
        )
    if single and len(unique) > 1:
        raise ActionError("INVALID_ARGUMENT", "这个工具一次只改一个动作。")
    return unique


# --- 全量快照 --------------------------------------------------------------
# 每个 tool 都回带同一份快照，UI 拿到结果就能直接上屏，不用再拉一次，也不会出现
# 「改完还显示旧值」。范围是有界的：今天一条、当月一屏、围度最近 N 个点。


def body_profile_payload(store: Store) -> dict | None:
    """档案里只取算基础代谢要的四项；没建档返回 None（不是空 dict）。

    ``_energy.expenditure`` 靠「是不是 None」来决定标不标 ``body_profile`` 缺数，
    空 dict 会被当成建过档但字段为空，于是缺数不报、基础代谢算不出来还没人说。
    """
    profile = store.body_profile()
    if profile is None:
        return None
    return {
        "sex": profile["sex"],
        "height_cm": profile["height_cm"],
        "age": profile["age"],
        "activity_level": profile["activity_level"],
    }


def session_energy_inputs(store: Store, day: str) -> tuple[list[dict], float | None]:
    """当天已完成动作（带 met/sets/reps/rep_unit）+ 勾选时间跨度（分钟）。

    消耗和日报两条路都要这份输入，放在领域模块里各取一次，不让 tool 脚本互相 import。
    没有完成动作时返回空列表——训练消耗记 0，不是缺数。
    """
    session = store.session_on(day)
    if session is None:
        return [], None
    done = [row for row in store.exercises_of(session["id"]) if row.get("done")]
    if not done:
        return [], None

    exercises = []
    for row in done:
        key = row["exercise_key"]
        entry = library_entry(key) or {}
        exercises.append(
            {
                "exercise_key": key,
                "met": entry.get("met"),
                "sets": row["sets"],
                "reps": row["reps"],
                "rep_unit": rep_unit_of(key),
            }
        )
    return exercises, _span_minutes(done)


def _span_minutes(done: list[dict]) -> float | None:
    """已完成动作 ``updated_at`` 最早与最晚之差（分钟）。解析失败则当作无跨度。"""
    moments = []
    for row in done:
        raw = row.get("updated_at")
        if not isinstance(raw, str) or not raw:
            continue
        try:
            moments.append(datetime.fromisoformat(raw))
        except ValueError:
            continue
    if len(moments) < 2:
        # 只有一个时间戳时跨度为 0，不可信，交给估算时长。
        return None if not moments else 0.0
    return (max(moments) - min(moments)).total_seconds() / 60.0


def _decorate_exercise(record: dict) -> dict:
    unit = rep_unit_of(record["exercise_key"])
    item = dict(record)
    item["done"] = bool(record["done"])
    item["rep_unit"] = unit
    meta = f"{record['sets']}组 × {record['reps']}{unit}"
    if record["load_text"]:
        meta = f"{meta} · {record['load_text']}"
    item["meta"] = meta
    return item


def _decorate_session(store: Store, session: dict | None) -> dict | None:
    if session is None:
        return None
    exercises = [_decorate_exercise(row) for row in store.exercises_of(session["id"])]
    done = sum(1 for item in exercises if item["done"])
    detail = dict(session)
    detail["exercises"] = exercises
    detail["done_count"] = done
    detail["total_count"] = len(exercises)
    detail["cycle_text"] = f"第 {session['cycle_index']}/{session['cycle_size']} 次"
    return detail


def _decorate_readiness(record: dict | None) -> dict | None:
    if record is None:
        return None
    detail = dict(record)
    # soreness 在库里是 JSON 文本，出参给的是解析好的数组：UI 和模型都不该再解一次。
    try:
        parsed = json.loads(record["soreness"] or "[]")
    except json.JSONDecodeError:
        parsed = []
    detail["soreness"] = parsed if isinstance(parsed, list) else []
    return detail


def _build_calendar(store: Store, month: str, anchor: str) -> dict:
    start, end = month_bounds(month)
    days = []
    for session in store.sessions_between(start, end):
        exercises = [_decorate_exercise(row) for row in store.exercises_of(session["id"])]
        days.append(
            {
                "date": session["date"],
                "day": int(session["date"][8:10]),
                "plan_name": session["plan_name"],
                "cycle_text": f"第 {session['cycle_index']}/{session['cycle_size']} 次",
                "status": session["status"],
                "done_count": sum(1 for item in exercises if item["done"]),
                "total_count": len(exercises),
                "exercises": [
                    {"id": item["id"], "name": item["name"], "done": item["done"]}
                    for item in exercises
                ],
            }
        )
    year, index = int(month[:4]), int(month[5:7])
    # 设计稿的表头是「日一二三四五六」，而 weekday() 以周一为 0，所以转成周日为 0。
    first_weekday = (date_cls(year, index, 1).weekday() + 1) % 7
    return {
        "month": month,
        "days_in_month": calendar.monthrange(year, index)[1],
        "first_weekday": first_weekday,
        "days": days,
        "selected": next((item for item in days if item["date"] == anchor), None),
    }


def _build_measurement(store: Store, part: str, weeks: int) -> dict:
    points = [
        {"date": row["date"], "label": _short_date(row["date"]), "value": row["value"]}
        for row in store.measurement_points(part, weeks)
    ]
    current = points[-1]["value"] if points else None
    delta = round(points[-1]["value"] - points[-2]["value"], 1) if len(points) >= 2 else None
    return {
        "latest": store.latest_measurements(),
        "trend": {
            "part": part,
            "unit": MEASUREMENT_UNITS.get(part, "cm"),
            "weeks": weeks,
            "points": points,
            "current": current,
            "delta": delta,
        },
    }


def _short_date(day: str) -> str:
    return f"{int(day[5:7])}/{int(day[8:10])}"


CARD_BADGE = "每日健身"
"""卡片顶部那行蓝字。跟饮食卡的「每日膳食」成对，是这张卡在会话里的身份。"""


EXERCISE_ICONS = {
    "goblet_squat": "🏋️",
    "bulgarian_split_squat": "🦵",
    "romanian_deadlift": "🏗️",
    "hip_thrust": "🌉",
    "glute_bridge": "🌁",
    "walking_lunge": "🚶",
    "push_up": "💪",
    "dumbbell_bench_press": "🛏️",
    "bent_over_row": "🚣",
    "lat_pulldown": "🪝",
    "bent_over_fly": "🦅",
    "overhead_press": "🙆",
    "lateral_raise": "🦋",
    "bicep_curl": "🥊",
    "triceps_extension": "🦾",
    "plank": "🧘",
    "side_plank": "🤸",
    "dead_bug": "🐛",
    "slider_mountain_climber": "🧗",
    "ab_wheel_kneeling_rollout": "☸️",
}
"""动作库这 20 个各配一个 emoji，且互不重样。

一张卡同时露三行。漏一个 key，那个动作掉进 🏃 兜底；两个 key 配同一个 emoji，
同一天排到一起就是两行一样的图标。两种都不报错、只是看着像没渲染出来，所以
``test_every_library_exercise_has_its_own_icon`` 同时守这两条。
"""


CARD_EXERCISE_LIMIT = 3
"""卡面一次最多露几个动作。

宿主的对话内联预览区只有三行多的高度，再往下连同底部按钮一起被裁掉。按排期
原顺序截断：已完成的行还在，右侧从勾选变成 ✓，不要折成「已完成 N 个」摘要。
"""


def _cue_prompt(name: str) -> str:
    """选中该动作后点「查要领」送进主对话的那句话。

    A2UI 的业务 action 不会直接调 tool，`sendQuery` 把这句话当成用户消息交给
    agent，再由 agent 去调 get_exercise_detail。措辞要能被 SKILL.md 的路由规则
    认出来，动作名加书名号是为了让 agent 不用猜名字到哪儿结束。
    """
    return f"看「{name}」的动作要领"


def _card_row(item: dict, *, present: bool = True) -> dict:
    done = bool(item.get("done")) and present
    return {
        "icon": EXERCISE_ICONS.get(item["exercise_key"], "🏃"),
        "name": item["name"],
        "meta": item["meta"],
        "status": "✓" if done else "○",
        "present": present,
        "done": done,
        "not_done": present and not done,
    }


def _empty_card_row() -> dict:
    return {
        "icon": "",
        "name": "",
        "meta": "",
        "status": "○",
        "present": False,
        "done": False,
        "not_done": False,
    }


def _pad_card_rows(shown: list[dict]) -> list[dict]:
    """卡面永远是三行槽位。空槽 present=false，Visibility 不画，路径却还在。"""
    rows = [_card_row(item) for item in shown[:CARD_EXERCISE_LIMIT]]
    while len(rows) < CARD_EXERCISE_LIMIT:
        rows.append(_empty_card_row())
    return rows


def _build_card(today: dict) -> dict:
    """卡片那几行文案在这里拼好，摊平到出参根上。

    A2UI 卡片只能按 JSON Pointer 取值、没法做条件渲染或字符串拼接，绑不到的路径
    是静默不画。把「第 2/3 次」「已完成 2/3」这类文案在服务端拼好，卡片就退化成
    一组纯取值，不会因为某天没有训练而画出半张空卡。

    Visibility 用的 ``card_has_*`` 布尔两边都给确定值：缺键在 A2UI 里是静默不画。
    """
    session = today["session"]
    if session is None:
        return {
            "card_badge": CARD_BADGE,
            "card_time": "08:00",
            "card_source": "来自「健康管家」 · 数据来自周计划",
            "card_title": "今日训练",
            "card_cycle": "今天还没有训练计划",
            "card_plan": f"{today['date']} · 让管家先排一次训练",
            # 文案里不要再提「工作台」：H5 撤了，卡上能给的下一步只有回对话说一声。
            "card_progress": "暂无动作清单 · 说一声就帮你排一次",
            "card_exercises": _pad_card_rows([]),
            "card_more": "",
            "card_more_prompt": "",
            "card_has_more": False,
            "card_has_session": False,
        }
    exercises = session["exercises"]
    shown = exercises[:CARD_EXERCISE_LIMIT]
    hidden = max(0, len(exercises) - len(shown))
    return {
        "card_badge": CARD_BADGE,
        "card_time": "08:00",
        "card_source": f"来自「{session['plan_name']}」 · 数据来自周计划",
        "card_title": "今日训练",
        "card_cycle": session["cycle_text"],
        "card_plan": f"今日训练 · {session['plan_name']}",
        "card_progress": (
            f"{session['cycle_text']} · 动作清单"
            f"（已完成 {session['done_count']}/{session['total_count']}）"
        ),
        "card_exercises": _pad_card_rows(shown),
        "card_more": f"还有 {hidden} 个动作 · 看完整清单 ›" if hidden else "",
        "card_more_prompt": "把今天完整的训练清单说一遍" if hidden else "",
        "card_has_more": hidden > 0,
        "card_has_session": True,
    }


def build_snapshot(store: Store, result: dict) -> dict:
    """按 handler 留下的锚点算出全量快照。

    handler 通过返回值里的三个键表达「以哪里为准」：``date``（今天是哪天）、
    ``month``（月历看哪个月）、``trend``（趋势看哪一项、看几个点）。前两个本身也是
    有意义的出参，留在结果里；``trend`` 只是查询条件，算完就换成
    ``measurement.trend`` 里的答案，不留两份。
    """
    anchor = result.get("date") or today_iso()
    month = result.get("month") or anchor[:7]
    query = result.pop("trend", None) or {}
    part = query.get("part") or DEFAULT_TREND_PART
    weeks = int(query.get("weeks") or DEFAULT_TREND_WEEKS)

    today = {
        "date": anchor,
        "readiness": _decorate_readiness(store.readiness_on(anchor)),
        "session": _decorate_session(store, store.session_on(anchor)),
    }
    snapshot = {
        "date": anchor,
        "month": month,
        "today": today,
        "calendar": _build_calendar(store, month, anchor),
        "measurement": _build_measurement(store, part, weeks),
        "exercise_library": exercise_library(),
        "counts": store.counts(),
    }
    snapshot.update(_build_card(today))
    return snapshot


# --- 给模型的回执 ------------------------------------------------------------
# 快照是给卡的：card_* 摊平在根上，外加整份动作库（约 7KB）、月历、围度点、计数。
# 模型要的只是这次做了什么，加上判断下一步要的那一小块。卡片那份一个字节不动。

_CARD_ONLY_KEYS = frozenset(("exercise_library", "counts", "calendar", "measurement", "month", "today"))
_TODAY_TOOLS = frozenset((
    "get_today", "log_readiness", "plan_session", "add_exercise",
    "complete_exercise", "update_exercise_setting", "complete_session",
))
_MEASUREMENT_TOOLS = frozenset(("get_measurement_trend", "log_measurement"))


def _compact_today(today: dict) -> dict:
    readiness = today.get("readiness")
    session = today.get("session")
    return {
        "date": today.get("date"),
        "readiness": None if not readiness else {
            "fatigue": readiness.get("fatigue"),
            "soreness": readiness.get("soreness") or [],
            "advice": readiness.get("advice"),
        },
        "session": None if not session else {
            "plan_name": session.get("plan_name"),
            "cycle_text": session.get("cycle_text"),
            "status": session.get("status"),
            "done_count": session.get("done_count"),
            "total_count": session.get("total_count"),
            "exercises": [
                {
                    "position": index,
                    "name": item.get("name"),
                    "exercise_key": item.get("exercise_key"),
                    "meta": item.get("meta"),
                    "done": bool(item.get("done")),
                }
                for index, item in enumerate(session.get("exercises") or [], start=1)
            ],
        },
    }


def _compact_calendar(calendar_view: dict) -> dict:
    return {
        "month": calendar_view.get("month"),
        "days": [
            {
                "date": day.get("date"),
                "plan_name": day.get("plan_name"),
                "status": day.get("status"),
                "done_count": day.get("done_count"),
                "total_count": day.get("total_count"),
                "exercises": [
                    {"name": item.get("name"), "done": bool(item.get("done"))}
                    for item in day.get("exercises") or []
                ],
            }
            for day in calendar_view.get("days") or []
        ],
    }


def _compact_measurement(measurement: dict) -> dict:
    trend = measurement.get("trend") or {}
    return {
        "latest": {
            part: None if not point else {"date": point.get("date"), "value": point.get("value")}
            for part, point in (measurement.get("latest") or {}).items()
        },
        "trend": {
            "part": trend.get("part"),
            "unit": trend.get("unit"),
            "weeks": trend.get("weeks"),
            "current": trend.get("current"),
            "delta": trend.get("delta"),
            "points": [
                {"date": point.get("date"), "value": point.get("value")}
                for point in trend.get("points") or []
            ],
        },
    }


def model_view(tool: str, structured: dict) -> dict:
    """把给卡的整份快照收成给模型的回执。错误信封原样返回。

    ``tool`` 是 handler 的函数名（即旧工具名），跟 ``_store.TOOL_DOMAIN`` 同一套键。
    """
    if structured.get("phase") == "error":
        return structured
    view = {
        key: value for key, value in structured.items()
        if key not in _CARD_ONLY_KEYS and not key.startswith("card_")
    }
    if tool in _TODAY_TOOLS:
        view["today"] = _compact_today(structured.get("today") or {})
    if tool == "get_month":
        view["month"] = structured.get("month")
        view["calendar"] = _compact_calendar(structured.get("calendar") or {})
    if tool in _MEASUREMENT_TOOLS:
        view["measurement"] = _compact_measurement(structured.get("measurement") or {})
    return view


def _hydrate(connection: sqlite3.Connection, root: Path) -> None:
    """把对象灌进这次调用的内存库。内存库是查询面，关掉就没了。"""

    def put(table: str, columns: tuple, record: dict) -> None:
        connection.execute(
            f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})",
            tuple(record.get(column) for column in columns),
        )

    for record in _records.iter_objects(root, "readiness"):
        put("readiness", READINESS_COLUMNS, record)
    for record in _records.iter_objects(root, "measurements"):
        put("measurements", MEASUREMENT_COLUMNS, record)
    for record in _records.iter_objects(root, "profile"):
        put("body_profile", BODY_PROFILE_COLUMNS, record)
    for record in _records.iter_objects(root, "sessions"):
        exercises = record.get("exercises") or []
        put("sessions", SESSION_COLUMNS, record)
        for exercise in exercises:
            if isinstance(exercise, dict):
                put("session_exercises", EXERCISE_COLUMNS, exercise)
    connection.commit()


@contextlib.contextmanager
def open_store(path: Path):
    """锁仍在本地盘上，挡住同一个沙箱里的并发；跨沙箱靠对象文件的原子替换，后写的赢。"""
    root = _records.root_for(path)
    _records.migrate_workout(path, root)
    with _store_lock(path):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            for statement in _SCHEMA:
                connection.execute(statement)
            _hydrate(connection, root)
            yield Store(connection, root)
        finally:
            connection.close()


def execute(handler, raw_args: str, store_path: str | os.PathLike | None = None) -> dict:
    """解析入参 → 拿锁 → 交给 handler → 补快照，返回该打给上游的那个对象。

    handler 形如 ``handler(args, store) -> dict``，只返回自己那部分结果，快照由这里
    统一补上。无论成败都返回一个可序列化的 dict，连未预期的异常也落成同一个错误
    信封——两个入口都指望这一点来保证 stdout 第一行永远是合法 JSON。

    包的两个入口共用它，区别只在怎么打：``run`` 打成恰好一行给 ``app`` CLI，
    ``_run.py`` 打成「业务 JSON + sentinel」两行给 Host 网关。
    """
    try:
        args = json.loads(raw_args)
        if not isinstance(args, dict):
            raise ActionError("INVALID_ARGUMENT", "请求参数必须为对象。")
        path = Path(store_path) if store_path else _resolve_store_path()
        # 真源是 records/ 下的对象。内存 SQLite 只是这一次调用的查询面。
        with open_store(path) as store:
            result = handler(args, store)
            result.update(build_snapshot(store, result))
            return result
    except (json.JSONDecodeError, ActionError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        message = getattr(exc, "message", "请求参数不是合法 JSON。")
        return error_envelope(code, message)
    except Exception:  # noqa: BLE001 - 兜住一切，保证 stdout 仍是合法 JSON
        # 异常文本可能带上原始入参，不往外透传；栈留在 stderr，上游不会把它当结果解析。
        traceback.print_exc()
        return error_envelope("INTERNAL_ERROR", "处理请求时发生内部错误。")


def run(handler, store_path: str | os.PathLike | None = None, raw_args: str | None = None) -> int:
    """``app`` CLI 那条路的收尾：把 ``execute`` 的结果打成**恰好一行** JSON。

    CLI 原样透传 stdout，多一行少一行都会让上游解析失败。``raw_args`` 不传就从
    ``sys.argv[1]`` 取——留这个形参是为了让别的入口能直接喂入参，不必改写 argv。
    """
    if raw_args is None:
        raw_args = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(json.dumps(execute(handler, raw_args, store_path), ensure_ascii=False,
                     separators=(",", ":")))
    return 0


# 入口在 handler 起跑之前就拦下的调用（未知 tool、visibility 不匹配、handler 文件不在）。
# 重试同一次调用不会有不同结果，所以跟 STORE_CORRUPTED 一样归到不可重试。
GATE_CODES = frozenset(("UNKNOWN_TOOL", "FORBIDDEN", "SCRIPT_MISSING"))


def error_envelope(code: str, message: str) -> dict:
    """统一错误信封。业务拒绝、入口拦截、内部异常都走这里，形状是对外契约。"""
    return {
        "phase": "error",
        "code": code,
        "message": message,
        "retryable": code not in ({"STORE_CORRUPTED", "INTERNAL_ERROR"} | GATE_CODES),
    }
