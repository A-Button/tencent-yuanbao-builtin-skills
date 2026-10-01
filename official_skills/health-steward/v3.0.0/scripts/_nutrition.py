#!/usr/bin/env python3
"""营养推荐区间：五项区间判定、持久化与统一工具收尾。"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import date, datetime
from pathlib import Path

from _errors import ActionError

NUTRIENT_KEYS = ("kcal", "carb_g", "protein_g", "fat_g", "fiber_g")
NUTRIENT_LABELS = {
    "kcal": ("总热量", "kcal"),
    "carb_g": ("碳水", "g"),
    "protein_g": ("蛋白质", "g"),
    "fat_g": ("脂肪", "g"),
    "fiber_g": ("膳食纤维", "g"),
}
DEFAULT_NUTRITION_TARGET = {
    "kcal": {"min": 1600, "max": 2000},
    "carb_g": {"min": 180, "max": 250},
    "protein_g": {"min": 60, "max": 90},
    "fat_g": {"min": 40, "max": 70},
    "fiber_g": {"min": 25, "max": 35},
}
VERDICT_BY_IN_RANGE = {
    5: "整体均衡",
    4: "整体较均衡",
    3: "基本达标",
    2: "略有偏离",
    1: "偏离较多",
    0: "偏离明显",
}
IN_RANGE, LOW, HIGH = "in_range", "low", "high"
NOTABLE_DEVIATION = 0.3
ADVICE_BY_NUTRIENT = {
    ("kcal", LOW): "可以再加一份主食或坚果",
    ("kcal", HIGH): "明天可减少一次加餐",
    ("carb_g", LOW): "明天可增加半碗杂粮饭",
    ("carb_g", HIGH): "明天可把一餐主食减半",
    ("protein_g", LOW): "明天可增加一份鸡蛋或豆制品",
    ("protein_g", HIGH): "明天可减少一份红肉",
    ("fat_g", LOW): "可以补一小把坚果或一勺橄榄油",
    ("fat_g", HIGH): "明天可少用一勺油",
    ("fiber_g", LOW): "明天可增加一份深色蔬菜",
    ("fiber_g", HIGH): "明天可少吃一份粗粮",
}
ALL_IN_RANGE_ADVICE = "五项都落在推荐区间内，保持现在的搭配就好。"

DEFAULT_DATA_DIR = "/data/user"
LOCAL_DATA_DIR = "~/.one-agent/data"
STORE_FILENAME = "nutrition.json"
_LOCK_DIR = os.environ.get("HEALTH_ASSISTANT_LOCK_DIR", "/tmp")
_LOCK_TIMEOUT = float(os.environ.get("HEALTH_ASSISTANT_LOCK_TIMEOUT", "30"))
_RETRYABLE_CODES = {"STORE_BUSY", "STORE_WRITE_FAILED"}


def _tidy_amount(value):
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)


def evaluate_nutrition(intake: dict, target: dict, day: str) -> dict:
    items = []
    for key in NUTRIENT_KEYS:
        label, unit = NUTRIENT_LABELS[key]
        bounds = target.get(key) or DEFAULT_NUTRITION_TARGET[key]
        low = float(bounds.get("min", 0))
        high = float(bounds.get("max", 0))
        raw = intake.get(key)
        if raw is None:
            items.append(
                {
                    "key": key,
                    "label": label,
                    "unit": unit,
                    "value": None,
                    "min": _tidy_amount(low),
                    "max": _tidy_amount(high),
                    "state": "unknown",
                    "deviation": 0.0,
                    "value_label": "未知",
                    "range_label": f"推荐 {_tidy_amount(low)}-{_tidy_amount(high)}{unit}",
                    "fill_percent": 0,
                }
            )
            continue
        value = float(raw)
        if value < low:
            state, deviation = LOW, (low - value) / low if low else 0.0
        elif value > high:
            state, deviation = HIGH, (value - high) / high if high else 0.0
        else:
            state, deviation = IN_RANGE, 0.0
        items.append(
            {
                "key": key,
                "label": label,
                "unit": unit,
                "value": _tidy_amount(value),
                "min": _tidy_amount(low),
                "max": _tidy_amount(high),
                "state": state,
                "deviation": round(deviation, 4),
                "value_label": f"{_tidy_amount(value)}{unit}",
                "range_label": f"推荐 {_tidy_amount(low)}-{_tidy_amount(high)}{unit}",
                "fill_percent": min(round(value / high * 100), 100) if high else 0,
            }
        )
    unknown = [item for item in items if item["state"] == "unknown"]
    in_range_count = sum(1 for item in items if item["state"] == IN_RANGE)
    if not unknown:
        verdict = VERDICT_BY_IN_RANGE[in_range_count]
    elif in_range_count == len(items) - len(unknown):
        verdict = "已知项都在区间内"
    else:
        verdict = VERDICT_BY_IN_RANGE[min(in_range_count, 5)]
    return {
        "date": day,
        "in_range_count": in_range_count,
        "verdict": verdict,
        "advice": _build_advice(items),
        "items": items,
    }


def _build_advice(items: list) -> str:
    off_range = [item for item in items if item["state"] not in (IN_RANGE, "unknown")]
    if not off_range:
        if any(item["state"] == "unknown" for item in items):
            return "已记录的项都在推荐区间内。膳食纤维没有记，先不当成达标或超标。"
        return ALL_IN_RANGE_ADVICE
    worst = max(off_range, key=lambda item: item["deviation"])
    degree = "明显" if worst["deviation"] >= NOTABLE_DEVIATION else "略"
    direction = "少" if worst["state"] == LOW else "多"
    hint = ADVICE_BY_NUTRIENT[(worst["key"], worst["state"])]
    return f"{worst['label']}{degree}{direction}，{hint}。"


def resolve_date(raw) -> str:
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        return datetime.now().astimezone().date().isoformat()
    if not isinstance(raw, str) or len(raw.strip()) != 10:
        raise ActionError("INVALID_ARGUMENT", "date 需要 YYYY-MM-DD 形式的日期。")
    try:
        return date.fromisoformat(raw.strip()).isoformat()
    except ValueError as exc:
        raise ActionError("INVALID_ARGUMENT", "date 需要 YYYY-MM-DD 形式的日期。") from exc


def require_number(args: dict, name: str) -> float:
    value = args.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ActionError("INVALID_ARGUMENT", f"{name} 必须是数值。")
    if value < 0:
        raise ActionError("INVALID_ARGUMENT", f"{name} 不能是负数。")
    return float(value)


def _resolve_store_path(environ: dict | None = None) -> Path:
    env = os.environ if environ is None else environ
    explicit = (env.get("HEALTH_ASSISTANT_STORE") or "").strip()
    if explicit:
        return Path(explicit)
    override = (
        env.get("HEALTH_ASSISTANT_DATA_DIR") or env.get("ONEAGENT_APP_DATA_DIR") or ""
    ).strip()
    if override:
        root = Path(override)
    elif Path(DEFAULT_DATA_DIR).is_dir():
        root = Path(DEFAULT_DATA_DIR)
    else:
        root = Path(LOCAL_DATA_DIR).expanduser()
    return root / "health-assistant" / STORE_FILENAME


def _lock_path(path: Path) -> Path:
    digest = hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    return Path(_LOCK_DIR) / f"health-assistant-{digest}.lock"


@contextlib.contextmanager
def _store_lock(path: Path):
    lock = _lock_path(path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    with open(lock, "a+", encoding="utf-8") as handle:
        deadline = time.monotonic() + _LOCK_TIMEOUT
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise ActionError("STORE_BUSY", "数据正被其它操作占用，请稍后重试。") from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ActionError("STORE_CORRUPTED", "营养设置已损坏。") from exc
    if not isinstance(data, dict):
        raise ActionError("STORE_CORRUPTED", "营养设置不是对象。")
    return data


def _save(path: Path, document: dict) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + f".tmp-{uuid.uuid4().hex}")
        with open(temporary, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        raise ActionError("STORE_WRITE_FAILED", "营养设置写入失败。") from exc


def _target_file(legacy: Path) -> Path:
    return legacy.parent / "records" / "nutrition_target.json"


def _migrate_nutrition(legacy: Path, dest: Path) -> None:
    """旧的整份 nutrition.json 收成一个对象。对象已经在，或旧文件不是 JSON，就不动。"""
    if dest.is_file() or not legacy.is_file() or legacy.suffix != ".json":
        return
    document = _load(legacy)
    if "nutrition_target" not in document:
        return
    _save(dest, {"nutrition_target": document["nutrition_target"]})


class Store:
    def __init__(self, path: Path):
        self._path = _target_file(path)
        _migrate_nutrition(path, self._path)
        sibling = path.with_name("nutrition.json")
        if sibling != path:
            _migrate_nutrition(sibling, self._path)
        self._doc = _load(self._path) if self._path.is_file() else {}

    def nutrition_target(self) -> dict:
        stored = self._doc.get("nutrition_target")
        stored = stored if isinstance(stored, dict) else {}
        return {
            key: (
                {"min": stored[key]["min"], "max": stored[key]["max"]}
                if isinstance(stored.get(key), dict)
                and "min" in stored[key]
                and "max" in stored[key]
                else dict(DEFAULT_NUTRITION_TARGET[key])
            )
            for key in NUTRIENT_KEYS
        }

    def set_nutrition_target(self, target: dict) -> dict:
        self._doc["nutrition_target"] = target
        _save(self._path, self._doc)
        return target


def execute(handler, raw_args: str, store_path=None) -> dict:
    try:
        args = json.loads(raw_args)
        if not isinstance(args, dict):
            raise ActionError("INVALID_ARGUMENT", "请求参数必须为对象。")
        path = Path(store_path) if store_path else _resolve_store_path()
        with _store_lock(path):
            store = Store(path)
            result = {
                "nutrition_target": store.nutrition_target(),
                "nutrition": None,
            }
            result.update(handler(args, store) or {})
            return result
    except (json.JSONDecodeError, ActionError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        message = getattr(exc, "message", "请求参数不是合法 JSON。")
        return error_envelope(code, message)


def run(handler, store_path=None, raw_args: str | None = None) -> int:
    if raw_args is None:
        raw_args = sys.argv[1] if len(sys.argv) > 1 else "{}"
    print(
        json.dumps(
            execute(handler, raw_args, store_path),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0


def error_envelope(code: str, message: str) -> dict:
    return {
        "phase": "error",
        "code": code,
        "message": message,
        "retryable": code in _RETRYABLE_CODES,
    }
