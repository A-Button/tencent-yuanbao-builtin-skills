#!/usr/bin/env python3
"""operation 的机器可读契约。

放在这里而不是散在 diet_api 的分支里，是为了让「少传一个字段」在进业务逻辑之前
就被挡住，报错信息也统一——模型看到的是 missing_argument + 缺哪个字段，而不是
一个 KeyError 堆栈。
"""

from __future__ import annotations

import math
import re
from datetime import datetime

from store import MEAL_LABEL, MEAL_TYPES

TABS = ["meal", "today", "stats"]
PERIODS = ["day", "week"]
EATEN_AT_SOURCES = ["photo", "upload", "user"]

# 每一项食物的营养字段：模型估，脚本合计。缺任何一个都算没估完。
ITEM_NUTRIENT_FIELDS = ["kcal", "protein_g", "fat_g", "carb_g", "sodium_mg"]
ITEM_REQUIRED = ["name", "portion", "emoji", "origin"] + ITEM_NUTRIENT_FIELDS
ITEM_OPTIONAL = ["story", "data_source", "assumptions"]
# portion 直接渲染在 XCard 食物列表右侧那一栏，只放份量：「1个」「一份」「一碗」「半包」。
# 写长了卡片会截断或挤坏版式，克重折算和部位假设一律进 assumptions。
PORTION_MAX_LEN = 3
# 整串就是「数字 + 重量/体积单位」的，是计量不是份量，挡掉。
#
# 上限收到 3 字之后，「约250g」这类计量串多半已经先被长度挡下，这条正则只剩
# 「50g」「1kg」这种三字以内的纯计量要管：长度合规，但仍然不是份量。
#
# 「两」「斤」故意不在名单里——「二两面」在中文里就是份量的说法，不是在报重量。
PURE_MEASURE_RE = re.compile(
    r"^(?:约|大约|大概|差不多|近)?\s*\d+(?:\.\d+)?\s*(?:[-~～至到]\s*\d+(?:\.\d+)?\s*)?"
    r"(?:g|kg|mg|克|千克|公斤|毫克|ml|l|毫升|升|oz|盎司)\s*$",
    re.IGNORECASE,
)
# 标题挂餐次前缀就是菜单名：「午餐：牛肉面加卤蛋」。餐次已经印在卡片时间那一行，
# 这里再写一遍是把仅有的 40 字让给了重复信息。
#
# 判据刻意只认「前缀 + 分隔符」这一个机械信号，不去判「牛肉面加卤蛋」够不够有画面
# ——那种判断没有稳定判据，误伤一次就是把模型逼进反复重试。剩下的交给 SKILL §9.1
# 的写法示例。同 PURE_MEASURE_RE 的取舍。
_TITLE_PREFIXES = sorted(
    set(MEAL_LABEL.values()) | {"早饭", "午饭", "晚饭", "宵夜", "加餐", "早点",
                                "测算", "记录", "分析", "本餐", "这餐", "今日", "今天"},
    key=len,
    reverse=True,
)
MENU_TITLE_RE = re.compile(r"^\s*(?:" + "|".join(_TITLE_PREFIXES) + r")\s*[:：·|｜]")

NARRATIVE_FIELDS = {"key_signals", "metabolism", "care", "followup"}
PATCH_FIELDS = {
    "eaten_at", "eaten_at_source", "meal_type", "title", "scene_oneliner",
    "items", "narrative", "nutrients", "photo_url", "is_favorited",
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

CONTRACT: dict[str, dict] = {
    "record_meal": {
        "summary": "落库一餐（同槽可多卡，不合并）并把三个 tab 推上屏",
        "required": ["items", "title", "sceneOneliner", "aiPrice"],
        "optional": [
            "narrative", "photoUrl", "eatenAt", "eatenAtSource",
            "mealType", "beverageOnly", "nutrients", "userId",
        ],
        "defaultTab": "meal",
    },
    "estimate_meal": {
        "summary": "只识别 + 算营养，不落库，卡片照出",
        # title / sceneOneliner 跟 record_meal 一样必填：测算也出卡，缺了只能由脚本兜底，
        # 而脚本能编出来的只有「测算：番茄炒蛋」这种菜单名——正是 SKILL §9.1 的反例。
        # 宁可让模型补一句，也不要我们自己往卡片上写废话。
        "required": ["items", "aiPrice", "narrative", "title", "sceneOneliner"],
        "optional": ["photoUrl"],
        "defaultTab": "meal",
    },
    "get_meal": {
        "summary": "按 meal_id 取单条，卡片停在本餐 tab",
        "required": ["mealId"],
        "optional": [],
        "defaultTab": "meal",
    },
    "get_day": {
        "summary": "取某一天的今日食书",
        "required": [],
        "optional": ["date"],
        "defaultTab": "today",
    },
    "get_stats": {
        "summary": "取日/周统计洞察",
        "required": [],
        "optional": ["period", "date"],
        "defaultTab": "stats",
    },
    "update_meal": {
        "summary": "字段级修改；items 变了会重算 totals",
        "required": ["mealId", "patch"],
        "optional": [],
        "defaultTab": "meal",
    },
    "delete_meal": {
        "summary": "软删一条，卡片切回今日食书",
        "required": ["mealId"],
        "optional": [],
        "defaultTab": "today",
    },
}


class ContractError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _require_string(value, path: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        suffix = "字符串" if allow_empty else "非空字符串"
        raise ContractError("invalid_argument", f"{path} 必须是{suffix}")


def _require_number(value, path: str) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError("invalid_argument", f"{path} 必须是数字")
    if not math.isfinite(float(value)) or value < 0:
        raise ContractError("invalid_argument", f"{path} 必须是大于等于 0 的有限数字")


def _check_strings(values, path: str) -> None:
    if not isinstance(values, list):
        raise ContractError("invalid_argument", f"{path} 必须是数组")
    for idx, value in enumerate(values):
        _require_string(value, f"{path}[{idx}]")


def _check_title(value, path: str = "title") -> None:
    _require_string(value, path)
    title = value.strip()
    if MENU_TITLE_RE.match(title):
        raise ContractError(
            "invalid_argument",
            f"{path} 是「{title}」，开头挂了餐次/操作前缀，这是菜单名不是标题。"
            "餐次已经印在卡片时间那一行，重复写一遍等于把仅有的 40 字让给废话。"
            "从这顿里挑一个具体的画面重写——一缕热气、一层油光、只买了一颗、汤见了底："
            "「一碗热气里的牛骨香」「夜灯下的油炸时光」「只收一颗的海苔小贝」",
        )


def _check_narrative(value, path: str = "narrative", *, require_care: bool = False) -> None:
    if not isinstance(value, dict):
        raise ContractError("invalid_argument", f"{path} 必须是对象")
    unknown = sorted(set(value) - NARRATIVE_FIELDS)
    if unknown:
        raise ContractError("invalid_argument", f"{path} 有未知字段：{', '.join(unknown)}")
    if "key_signals" in value:
        _check_strings(value["key_signals"], f"{path}.key_signals")
    for field in ("metabolism", "care", "followup"):
        if field in value:
            _require_string(value[field], f"{path}.{field}", allow_empty=True)
    if require_care:
        care = value.get("care")
        if not isinstance(care, str) or not care.strip():
            raise ContractError(
                "missing_argument",
                f"{path}.care 必填：卡片底部「本餐营养学分析」绑的就是这一段，空了卡片会空一块",
            )


def _check_iso_datetime(value, path: str) -> None:
    _require_string(value, path)
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ContractError("invalid_argument", f"{path} 必须是 ISO 8601 时间") from None


def _check_items(items) -> None:
    if not isinstance(items, list) or not items:
        raise ContractError("invalid_argument", "items 必须是非空数组")
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            raise ContractError("invalid_argument", f"items[{idx}] 必须是对象")
        unknown = sorted(set(item) - set(ITEM_REQUIRED) - set(ITEM_OPTIONAL))
        if unknown:
            raise ContractError("invalid_argument", f"items[{idx}] 有未知字段：{', '.join(unknown)}")
        missing = [f for f in ITEM_REQUIRED if item.get(f) in (None, "")]
        if missing:
            raise ContractError(
                "missing_argument",
                f"items[{idx}]（{item.get('name') or '未命名'}）缺字段：{', '.join(missing)}",
            )
        for field in ("name", "portion", "emoji", "origin"):
            _require_string(item[field], f"items[{idx}].{field}")
        portion = item["portion"].strip()
        # 先判「是不是计量」再判长度。两种都拒，但「这是计量不是份量」直接说清了该怎么改，
        # 而「超了几个字」只说了不合规。上限收到 3 字后绝大多数计量串两条都犯，
        # 顺序反过来就只剩长度那句，模型容易把「约250g」删成「250g」再撞一次。
        if PURE_MEASURE_RE.match(portion):
            raise ContractError(
                "invalid_argument",
                f"items[{idx}]（{item['name']}）的 portion 是「{portion}」，这是计量不是份量。"
                "换成用户一眼看懂的份量单位——「1个」「一份」「一碗」「半份」「两块」，"
                f"克重写进 assumptions（比如 assumptions 里写「{portion}」）",
            )
        if len(portion) > PORTION_MAX_LEN:
            raise ContractError(
                "invalid_argument",
                f"items[{idx}]（{item['name']}）的 portion 是「{portion}」，有 {len(portion)} 字，"
                f"上限 {PORTION_MAX_LEN}。卡片那一栏只放得下「1个」「一份」「一碗」这种两三个字的，"
                "括号补充、克重折算和部位假设一律写进 assumptions",
            )
        for field in ITEM_NUTRIENT_FIELDS:
            _require_number(item[field], f"items[{idx}].{field}")
        for field in ITEM_OPTIONAL:
            if field in item:
                _require_string(item[field], f"items[{idx}].{field}", allow_empty=True)


def _check_patch(patch: dict) -> None:
    unknown = sorted(set(patch) - PATCH_FIELDS)
    if unknown:
        raise ContractError("invalid_argument", f"patch 有不可修改字段：{', '.join(unknown)}")
    if "title" in patch:
        _check_title(patch["title"], "patch.title")
    if "scene_oneliner" in patch:
        _require_string(patch["scene_oneliner"], "patch.scene_oneliner")
    if "items" in patch:
        _check_items(patch["items"])
    if "narrative" in patch:
        _check_narrative(patch["narrative"], "patch.narrative")
    if "nutrients" in patch:
        _check_strings(patch["nutrients"], "patch.nutrients")
    if "photo_url" in patch and patch["photo_url"] is not None:
        _require_string(patch["photo_url"], "patch.photo_url")
    if "is_favorited" in patch and not isinstance(patch["is_favorited"], bool):
        raise ContractError("invalid_argument", "patch.is_favorited 必须是布尔值")
    if "eaten_at" in patch:
        _check_iso_datetime(patch["eaten_at"], "patch.eaten_at")
    if "eaten_at_source" in patch and patch["eaten_at_source"] not in EATEN_AT_SOURCES:
        raise ContractError("invalid_argument", f"patch.eaten_at_source 只能是 {', '.join(EATEN_AT_SOURCES)}")
    if "meal_type" in patch and patch["meal_type"] not in MEAL_TYPES:
        raise ContractError("invalid_argument", f"patch.meal_type 只能是 {', '.join(MEAL_TYPES)}")


def validate(operation: str, args: dict) -> dict:
    """校验并回填默认值，返回规范化后的参数。不合法直接抛 ContractError。"""
    spec = CONTRACT.get(operation)
    if spec is None:
        raise ContractError(
            "unknown_operation",
            f"不支持的 operation：{operation}。可用：{', '.join(sorted(CONTRACT))}",
        )

    allowed = {"operation", "tab", *spec["required"], *spec["optional"]}
    unknown = sorted(set(args) - allowed)
    if unknown:
        raise ContractError("invalid_argument", f"{operation} 有未知参数：{', '.join(unknown)}")

    missing = [f for f in spec["required"] if args.get(f) in (None, "", [])]
    if missing:
        raise ContractError("missing_argument", f"{operation} 缺参数：{', '.join(missing)}")

    if operation == "record_meal":
        _check_items(args["items"])
        _check_title(args["title"])
        _require_string(args["sceneOneliner"], "sceneOneliner")
        meal_type = args.get("mealType")
        if meal_type and meal_type not in MEAL_TYPES:
            raise ContractError("invalid_argument", f"mealType 只能是 {', '.join(MEAL_TYPES)}")
        source = args.get("eatenAtSource")
        if source and source not in EATEN_AT_SOURCES:
            raise ContractError("invalid_argument", f"eatenAtSource 只能是 {', '.join(EATEN_AT_SOURCES)}")
        if "eatenAt" in args:
            _check_iso_datetime(args["eatenAt"], "eatenAt")
        if "beverageOnly" in args and not isinstance(args["beverageOnly"], bool):
            raise ContractError("invalid_argument", "beverageOnly 必须是布尔值")
        if "aiPrice" in args:
            _require_number(args["aiPrice"], "aiPrice")
        if "nutrients" in args:
            _check_strings(args["nutrients"], "nutrients")
        if "narrative" in args:
            _check_narrative(args["narrative"])
        for field in ("photoUrl", "userId"):
            if field in args:
                _require_string(args[field], field)

    if operation == "estimate_meal":
        _check_items(args["items"])
        if "aiPrice" in args:
            _require_number(args["aiPrice"], "aiPrice")
        # care 上屏「本餐营养学分析」；测算不落库，但仍要出卡，care 不能空。
        _check_narrative(args["narrative"], require_care=True)
        _check_title(args["title"])
        _require_string(args["sceneOneliner"], "sceneOneliner")
        if "photoUrl" in args:
            _require_string(args["photoUrl"], "photoUrl")

    if operation == "update_meal":
        patch = args.get("patch")
        if not isinstance(patch, dict) or not patch:
            raise ContractError("invalid_argument", "patch 必须是非空对象")
        _check_patch(patch)

    if operation == "get_stats":
        period = args.get("period") or "week"
        if period not in PERIODS:
            raise ContractError("invalid_argument", f"period 只能是 {', '.join(PERIODS)}")
        args = {**args, "period": period}

    if "mealId" in args:
        _require_string(args["mealId"], "mealId")
    if "date" in args:
        date = args["date"]
        _require_string(date, "date")
        if not DATE_RE.fullmatch(date):
            raise ContractError("invalid_argument", "date 必须是 YYYY-MM-DD")
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise ContractError("invalid_argument", "date 必须是有效日期") from None
    if "tab" in args and args["tab"] not in TABS:
        raise ContractError("invalid_argument", f"tab 只能是 {', '.join(TABS)}")

    return args
