#!/usr/bin/env python3
"""operation 的机器可读契约。

放在这里而不是散在 diet_api 的分支里，是为了让「少传一个字段」在进业务逻辑之前
就被挡住，报错信息也统一。

**一次报全。** 以前撞到第一个问题就抛，模型改一个、再撞下一个，一餐能来回三四轮。
现在把整份入参查完，所有问题一起放进 ``ContractError.errors``，每条都写清怎么改。
"""

from __future__ import annotations

import math
import re
from datetime import datetime

from store import MEAL_LABEL, MEAL_TYPES, SKIP_SLOTS

TABS = ["meal", "today", "stats"]
PERIODS = ["day", "week"]
EATEN_AT_SOURCES = ["photo", "upload", "user"]

# 每一项食物的营养字段：模型估，脚本合计。缺任何一个都算没估完。
ITEM_NUTRIENT_FIELDS = ["kcal", "protein_g", "fat_g", "carb_g", "sodium_mg"]
ITEM_REQUIRED = ["name", "portion"] + ITEM_NUTRIENT_FIELDS
# emoji / origin / story / data_source / assumptions 现在的饮食卡一个都不画，只在正文里用得上，
# 所以不再逼模型往参数里写；传了照存。
ITEM_OPTIONAL = ["emoji", "origin", "story", "data_source", "assumptions"]
# portion 拼进卡面那行「白米饭 × 一碗」，只放份量：「1个」「一份」「一碗」「半包」。
# 写长了那一行会折成两行，克重折算和部位假设写进正文。
PORTION_MAX_LEN = 3
# 整串就是「数字 + 重量/体积单位」的，是计量不是份量，挡掉。
#
# 「两」「斤」故意不在名单里——「二两面」在中文里就是份量的说法，不是在报重量。
PURE_MEASURE_RE = re.compile(
    r"^(?:约|大约|大概|差不多|近)?\s*\d+(?:\.\d+)?\s*(?:[-~～至到]\s*\d+(?:\.\d+)?\s*)?"
    r"(?:g|kg|mg|克|千克|公斤|毫克|ml|l|毫升|升|oz|盎司)\s*$",
    re.IGNORECASE,
)
# 标题挂餐次前缀（「午餐：牛肉面」）时直接去掉前缀。标题不上卡，只在「看今天吃了什么」
# 的回执里帮你认出是哪一条，为一个前缀让模型重试一轮不值。
_TITLE_PREFIXES = sorted(
    set(MEAL_LABEL.values()) | {"早饭", "午饭", "晚饭", "宵夜", "加餐", "早点",
                                "测算", "记录", "分析", "本餐", "这餐", "今日", "今天"},
    key=len,
    reverse=True,
)
MENU_TITLE_RE = re.compile(r"^\s*(?:" + "|".join(_TITLE_PREFIXES) + r")\s*[:：·|｜]\s*")

NARRATIVE_FIELDS = {"key_signals", "metabolism", "care", "followup"}
PATCH_FIELDS = {
    "eaten_at", "eaten_at_source", "meal_type", "title", "scene_oneliner",
    "items", "narrative", "nutrients", "photo_url", "is_favorited",
}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

# tab / userId 是 H5 时代的参数：详情页撤了、档案靠持久卷隔离，manifest 里已不再声明。
# 老调用传了照收，不报未知参数。
_LEGACY_OPTIONAL = ["tab", "userId"]

CONTRACT: dict[str, dict] = {
    "record_meal": {
        "summary": "落库一餐（同槽可多卡，不合并）并出饮食卡",
        "required": ["items"],
        "optional": [
            "photoUrl", "eatenAt", "eatenAtSource", "mealType", "beverageOnly",
            "title", "sceneOneliner", "aiPrice", "narrative", "nutrients",
        ],
        "defaultTab": "meal",
    },
    "estimate_meal": {
        "summary": "只识别 + 算营养，不落库，卡片照出",
        "required": ["items"],
        "optional": ["photoUrl", "title", "sceneOneliner", "aiPrice", "narrative"],
        "defaultTab": "meal",
    },
    "get_meal": {
        "summary": "按 meal_id 取单条",
        "required": ["mealId"],
        "optional": [],
        "defaultTab": "meal",
    },
    "get_day": {
        "summary": "取某一天吃了什么",
        "required": [],
        "optional": ["date"],
        "defaultTab": "today",
    },
    "skip_meal": {
        "summary": "把早/午/晚某一餐标成跳过，不进热量合计，卡片刷新成已跳过",
        "required": ["mealType"],
        "optional": ["date"],
        "defaultTab": "today",
    },
    "get_stats": {
        "summary": "取日/周统计",
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
        "summary": "软删一条",
        "required": ["mealId"],
        "optional": [],
        "defaultTab": "today",
    },
}


class ContractError(ValueError):
    """入参不合法或业务拒绝。``errors`` 是逐条的问题清单，一次给全。"""

    def __init__(self, code: str, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.code = code
        self.errors = list(errors or [])


def _require_string(value, path: str, problems: list[str], *, allow_empty: bool = False) -> bool:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        suffix = "字符串" if allow_empty else "非空字符串"
        problems.append(f"{path} 必须是{suffix}")
        return False
    return True


def _require_number(value, path: str, problems: list[str]) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        problems.append(f"{path} 必须是数字")
    elif not math.isfinite(float(value)) or value < 0:
        problems.append(f"{path} 必须是大于等于 0 的有限数字")


def _check_strings(values, path: str, problems: list[str]) -> None:
    if not isinstance(values, list):
        problems.append(f"{path} 必须是字符串数组")
        return
    for idx, value in enumerate(values):
        _require_string(value, f"{path}[{idx}]", problems)


def normalize_title(value: str) -> str:
    """去掉「午餐：」「测算·」这类前缀。去完是空的就返回空串，交给落库时按食物名补。"""
    return MENU_TITLE_RE.sub("", value).strip()


def _check_narrative(value, path: str, problems: list[str]) -> None:
    if not isinstance(value, dict):
        problems.append(f"{path} 必须是对象")
        return
    unknown = sorted(set(value) - NARRATIVE_FIELDS)
    if unknown:
        problems.append(
            f"{path} 有未知字段：{', '.join(unknown)}（可用：{', '.join(sorted(NARRATIVE_FIELDS))}）"
        )
    if "key_signals" in value:
        _check_strings(value["key_signals"], f"{path}.key_signals", problems)
    for field in ("metabolism", "care", "followup"):
        if field in value:
            _require_string(value[field], f"{path}.{field}", problems, allow_empty=True)


def _check_iso_datetime(value, path: str, problems: list[str]) -> None:
    if not _require_string(value, path, problems):
        return
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        problems.append(f"{path} 必须是 ISO 8601 时间，如 2026-09-03T12:30:00+08:00，只知道日期就写 2026-09-03")


def _check_portion(portion: str, label: str, problems: list[str]) -> None:
    # 先判「是不是计量」再判长度。两种都拒，但「这是计量不是份量」直接说清了该怎么改，
    # 而「超了几个字」只说了不合规。顺序反过来，模型容易把「约250g」删成「250g」再撞一次。
    text = portion.strip()
    if PURE_MEASURE_RE.match(text):
        problems.append(
            f"{label} 的 portion 是「{text}」，这是计量不是份量。换成「1个」「一份」「一碗」「半份」"
            "「两块」这种份量词，克重写进正文"
        )
    elif len(text) > PORTION_MAX_LEN:
        problems.append(
            f"{label} 的 portion 是「{text}」，有 {len(text)} 字，上限 {PORTION_MAX_LEN}。"
            "只写「1个」「一份」「一碗」这种份量词，括号补充和克重写进正文"
        )


def _check_items(items, problems: list[str], path: str = "items") -> None:
    if not isinstance(items, list) or not items:
        problems.append(f"{path} 必须是非空数组，一样食物一项")
        return
    allowed = set(ITEM_REQUIRED) | set(ITEM_OPTIONAL)
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            problems.append(f"{path}[{idx}] 必须是对象")
            continue
        label = f"{path}[{idx}]（{item.get('name') or '未命名'}）"
        unknown = sorted(set(item) - allowed)
        if unknown:
            problems.append(f"{label} 有未知字段：{', '.join(unknown)}（可用：{', '.join(ITEM_REQUIRED + ITEM_OPTIONAL)}）")
        missing = [field for field in ITEM_REQUIRED if item.get(field) in (None, "")]
        if missing:
            problems.append(f"{label} 缺字段：{', '.join(missing)}")
        if item.get("name") not in (None, ""):
            _require_string(item["name"], f"{label}.name", problems)
        portion = item.get("portion")
        if portion not in (None, "") and _require_string(portion, f"{label}.portion", problems):
            _check_portion(portion, label, problems)
        for field in ITEM_NUTRIENT_FIELDS:
            if item.get(field) is not None:
                _require_number(item[field], f"{label}.{field}", problems)
        for field in ITEM_OPTIONAL:
            if field in item:
                _require_string(item[field], f"{label}.{field}", problems, allow_empty=True)


def _check_meal_texts(args: dict, problems: list[str]) -> dict:
    """title / sceneOneliner / aiPrice / narrative：都是可选的，传了就查形状。"""
    if "title" in args:
        if _require_string(args["title"], "title", problems, allow_empty=True):
            title = normalize_title(args["title"])
            args = {**args, "title": title} if title else {k: v for k, v in args.items() if k != "title"}
    if "sceneOneliner" in args:
        _require_string(args["sceneOneliner"], "sceneOneliner", problems, allow_empty=True)
    if args.get("aiPrice") is not None:
        _require_number(args["aiPrice"], "aiPrice", problems)
    if "narrative" in args:
        _check_narrative(args["narrative"], "narrative", problems)
    if "photoUrl" in args:
        _require_string(args["photoUrl"], "photoUrl", problems)
    return args


def _check_patch(patch: dict, problems: list[str]) -> dict:
    unknown = sorted(set(patch) - PATCH_FIELDS)
    if unknown:
        problems.append(f"patch 有不可修改字段：{', '.join(unknown)}（可改：{', '.join(sorted(PATCH_FIELDS))}）")
    if "title" in patch and _require_string(patch["title"], "patch.title", problems):
        title = normalize_title(patch["title"])
        if title:
            patch = {**patch, "title": title}
        else:
            problems.append("patch.title 去掉餐次前缀后是空的，写一个能认出这一餐的短标题")
    if "scene_oneliner" in patch:
        _require_string(patch["scene_oneliner"], "patch.scene_oneliner", problems, allow_empty=True)
    if "items" in patch:
        _check_items(patch["items"], problems, "patch.items")
    if "narrative" in patch:
        _check_narrative(patch["narrative"], "patch.narrative", problems)
    if "nutrients" in patch:
        _check_strings(patch["nutrients"], "patch.nutrients", problems)
    if "photo_url" in patch and patch["photo_url"] is not None:
        _require_string(patch["photo_url"], "patch.photo_url", problems)
    if "is_favorited" in patch and not isinstance(patch["is_favorited"], bool):
        problems.append("patch.is_favorited 必须是布尔值")
    if "eaten_at" in patch:
        _check_iso_datetime(patch["eaten_at"], "patch.eaten_at", problems)
    if "eaten_at_source" in patch and patch["eaten_at_source"] not in EATEN_AT_SOURCES:
        problems.append(f"patch.eaten_at_source 只能是 {', '.join(EATEN_AT_SOURCES)}")
    if "meal_type" in patch and patch["meal_type"] not in MEAL_TYPES:
        problems.append(f"patch.meal_type 只能是 {', '.join(MEAL_TYPES)}")
    return patch


def _raise_if(problems: list[str]) -> None:
    if not problems:
        return
    message = problems[0] if len(problems) == 1 else f"有 {len(problems)} 处参数要改，逐条见 errors"
    raise ContractError("INVALID_ARGUMENT", message, problems)


def validate(operation: str, args: dict) -> dict:
    """校验并回填默认值，返回规范化后的参数。不合法时抛 ContractError，问题一次给全。"""
    spec = CONTRACT.get(operation)
    if spec is None:
        raise ContractError(
            "UNKNOWN_TOOL",
            f"不支持的 operation：{operation}。可用：{', '.join(sorted(CONTRACT))}",
        )

    problems: list[str] = []
    allowed = {"operation", *spec["required"], *spec["optional"], *_LEGACY_OPTIONAL}
    unknown = sorted(set(args) - allowed)
    if unknown:
        usable = [name for name in (*spec["required"], *spec["optional"])]
        problems.append(f"有未知参数：{', '.join(unknown)}（可用：{', '.join(usable)}）")
    missing = [field for field in spec["required"] if args.get(field) in (None, "", [])]
    if missing:
        problems.append(f"缺参数：{', '.join(missing)}")

    if operation in ("record_meal", "estimate_meal"):
        if "items" not in missing:
            _check_items(args["items"], problems)
        args = _check_meal_texts(args, problems)

    if operation == "record_meal":
        meal_type = args.get("mealType")
        if meal_type and meal_type not in MEAL_TYPES:
            problems.append(f"mealType 只能是 {', '.join(MEAL_TYPES)}")
        source = args.get("eatenAtSource")
        if source and source not in EATEN_AT_SOURCES:
            problems.append(f"eatenAtSource 只能是 {', '.join(EATEN_AT_SOURCES)}")
        if "eatenAt" in args:
            _check_iso_datetime(args["eatenAt"], "eatenAt", problems)
        if "beverageOnly" in args and not isinstance(args["beverageOnly"], bool):
            problems.append("beverageOnly 必须是布尔值")
        if "nutrients" in args:
            _check_strings(args["nutrients"], "nutrients", problems)
        if "userId" in args:
            _require_string(args["userId"], "userId", problems)

    if operation == "skip_meal" and "mealType" not in missing:
        if args["mealType"] not in SKIP_SLOTS:
            problems.append(f"mealType 只能是 {', '.join(SKIP_SLOTS)}（饮品、下午茶、夜宵不标跳过）")

    if operation == "update_meal" and "patch" not in missing:
        patch = args.get("patch")
        if not isinstance(patch, dict) or not patch:
            problems.append("patch 必须是非空对象")
        else:
            args = {**args, "patch": _check_patch(patch, problems)}

    if operation == "get_stats":
        period = args.get("period") or "week"
        if period not in PERIODS:
            problems.append(f"period 只能是 {', '.join(PERIODS)}")
        args = {**args, "period": period}

    if "mealId" in args and "mealId" not in missing:
        _require_string(args["mealId"], "mealId", problems)
    if "date" in args:
        date = args["date"]
        if _require_string(date, "date", problems):
            if not DATE_RE.fullmatch(date):
                problems.append("date 必须是 YYYY-MM-DD")
            else:
                try:
                    datetime.strptime(date, "%Y-%m-%d")
                except ValueError:
                    problems.append("date 必须是有效日期")
    if "tab" in args and args["tab"] not in TABS:
        problems.append(f"tab 只能是 {', '.join(TABS)}")

    _raise_if(problems)
    return args
