#!/usr/bin/env python3
"""营养合计、4-4-9 交叉核验，以及日/周两档统计聚合。

模型只负责估每一项食物的 kcal / 蛋白 / 脂肪 / 碳水 / 钠，合计和核验一律走这里——
把「不许心算」从提示词约束变成代码事实。
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from datetime import timedelta

from store import CST, MEAL_LABEL, MEAL_TYPES, parse_time

NUTRIENT_KEYS = ["kcal", "protein_g", "fat_g", "carb_g", "sodium_mg"]

# 4-4-9：蛋白 4 kcal/g、碳水 4 kcal/g、脂肪 9 kcal/g
ATWATER = {"protein_g": 4, "carb_g": 4, "fat_g": 9}

CROSS_CHECK_TOLERANCE_PCT = 5.0

# 规律性评分要跨天比较用餐时刻，日视图也按这个窗口算（见 stats_for_day）。
REGULARITY_DAYS = 7

# 样本不够算离散度时给的分。不是满分：留一分的余地，免得刚记第一餐就宣布「完美规律」。
DEFAULT_REGULARITY = 99



def _qty(value: float) -> int:
    """展示用营养量一律取整，日/周摘要与本餐标签位数一致。"""
    return int(round(float(value or 0)))


def sum_items(items: list[dict]) -> dict:
    return {k: _qty(sum(float(it.get(k) or 0) for it in items)) for k in NUTRIENT_KEYS}


def cross_check(totals: dict) -> dict:
    """返回 {cross_check, delta_pct, passed}。kcal 为 0 时不做判定。"""
    computed = _qty(sum(totals.get(k, 0) * factor for k, factor in ATWATER.items()))
    kcal = totals.get("kcal") or 0
    if not kcal:
        return {"cross_check": computed, "delta_pct": None, "passed": True}
    delta = round(abs(computed - kcal) / kcal * 100, 2)
    return {"cross_check": computed, "delta_pct": delta, "passed": delta <= CROSS_CHECK_TOLERANCE_PCT}


def totals_of(meal: dict) -> dict:
    return meal.get("totals") or {}


def day_totals(meals: list[dict]) -> dict:
    return {k: _qty(sum(float(totals_of(m).get(k) or 0) for m in meals)) for k in NUTRIENT_KEYS}


def group_by_meal_type(meals: list[dict]) -> dict:
    """今日食书的六段。空段保留成空数组，前端折叠成「没有吃」。"""
    grouped: dict[str, list[dict]] = {mt: [] for mt in MEAL_TYPES}
    for meal in meals:
        grouped.setdefault(meal.get("meal_type") or "midnight", []).append({
            "meal_id": meal.get("meal_id"),
            "title": meal.get("title"),
            "meal_type": meal.get("meal_type"),
            # 卡片上每段要显示用餐时刻，钟点由端上格式化，这里只给原始 ISO
            "eaten_at": meal.get("eaten_at"),
            "items": [{"name": it.get("name")} for it in meal.get("items") or []],
            "totals": {"kcal": totals_of(meal).get("kcal", 0)},
            "nutrients": meal.get("nutrients") or [],
            "photo_url": meal.get("photo_url"),
            # 每段的图由 a2ui 从 photo_key 解，所以摘要里也得带着它。
            "photo_key": meal.get("photo_key"),
        })
    return grouped


def _minutes_of(meal: dict) -> int | None:
    try:
        dt = parse_time(meal["eaten_at"])
    except (KeyError, ValueError):
        return None
    return dt.hour * 60 + dt.minute


def regularity(meals: list[dict]) -> tuple[int, dict]:
    """按三个正餐各自用餐时刻的离散程度打分，并给出平均用餐时间。

    每个餐次至少两天有记录才算得出离散度。标准差越小越规律：90 分钟标准差约 50 分，
    180 分钟落到 0 分。

    同槽多卡后，同一天同一餐次可能有多条。规律性比的是「天与天之间几点吃」，
    所以先按 (日, 餐次) 取均值，再跨天算离散——否则同午两张卡会把「一天」当成两个样本，
    分数被同日补记噪声拉歪。

    样本不够就给 DEFAULT_REGULARITY，不再返回 None。以前返回 None 是想让卡片显示
    「—」而不是编一个数，但那个圈在卡片上占了一整块，空着比给个乐观的默认值更难看，
    用户也看不出「—」是「还没数据」还是「坏了」。档案整个为空时压根不出卡（见
    card_skipped=empty_archive），所以这里不会出现「零记录却打 99 分」。
    """
    per_day: dict[tuple[str, str], list[int]] = defaultdict(list)
    for meal in meals:
        minutes = _minutes_of(meal)
        mt = meal.get("meal_type")
        if minutes is None or mt not in ("breakfast", "lunch", "dinner"):
            continue
        day = str(meal.get("eaten_at", ""))[:10]
        if day:
            per_day[(day, mt)].append(minutes)

    buckets: dict[str, list[int]] = defaultdict(list)
    for (_day, mt), vals in per_day.items():
        buckets[mt].append(round(sum(vals) / len(vals)))

    avg_time = {
        mt: f"{int(sum(vals) / len(vals)) // 60:02d}:{int(sum(vals) / len(vals)) % 60:02d}"
        for mt, vals in buckets.items() if vals
    }

    spreads = [statistics.pstdev(vals) for vals in buckets.values() if len(vals) >= 2]
    if not spreads:
        return DEFAULT_REGULARITY, avg_time
    score = round(100 - min(100.0, (sum(spreads) / len(spreads)) / 1.8))
    return max(0, score), avg_time


def _window_from(anchor, days: int) -> list[str]:
    """最近 days 个日历日，从早到晚。"""
    return [(anchor - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days - 1, -1, -1)]


_CIRCLED = "①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳"


def _day_labels(todays: list[dict]) -> list[str]:
    """日视图每根柱子的名字。同一餐次当天出现多次才加序号。

    同槽多卡后一天可能有两顿夜宵，两根柱子都叫「夜宵」在图上分不出谁是谁。
    序号按用餐时刻先后走（调用方已排序），跟卡片从上到下的顺序对得上。
    只有一条时不加序号：绝大多数餐次一天就一顿，无谓的「①」纯属噪声。
    """
    counts = Counter(m.get("meal_type") for m in todays)
    seen: Counter = Counter()
    labels = []
    for meal in todays:
        meal_type = meal.get("meal_type")
        base = MEAL_LABEL.get(meal_type, "")
        if counts[meal_type] < 2:
            labels.append(base)
            continue
        seen[meal_type] += 1
        nth = seen[meal_type]
        # 带圈数字只到 ⑳，再多就退回普通数字——一天记二十顿同餐次不该让标签崩掉。
        labels.append(base + (_CIRCLED[nth - 1] if nth <= len(_CIRCLED) else str(nth)))
    return labels


def stats_for_day(meals: list[dict], date_str: str) -> dict:
    """日维度：一根柱 = 一顿，avg 是当日合计而非均值。

    规律性评分是个例外，它跟着最近 7 天算。只喂当天的话这一项永远出不来：
    每个餐次每天只算一个样本（同槽多卡会先按日均值），单日桶里最多一个点，
    标准差无从谈起，分数走 DEFAULT_REGULARITY。
    """
    todays = [m for m in meals if str(m.get("eaten_at", ""))[:10] == date_str]
    todays.sort(key=lambda m: m.get("eaten_at") or "")
    recent = set(_window_from(parse_time(date_str + "T12:00:00+08:00"), REGULARITY_DAYS))
    score, avg_time = regularity(
        [m for m in meals if str(m.get("eaten_at", ""))[:10] in recent]
    )
    labels = _day_labels(todays)
    return {
        "range_days": 1,
        "meal_count": len(todays),
        "avg": {k: _qty(sum(float(totals_of(m).get(k) or 0) for m in todays))
                for k in ["kcal", "protein_g", "carb_g", "fat_g"]},
        "daily_kcal_trend": [_qty(totals_of(m).get("kcal", 0)) for m in todays],
        "trend_labels": labels,
        "nutrition_composition": [{
            "date": label,
            "protein_g": _qty(totals_of(m).get("protein_g", 0)),
            "carb_g": _qty(totals_of(m).get("carb_g", 0)),
            "fat_g": _qty(totals_of(m).get("fat_g", 0)),
        } for m, label in zip(todays, labels)],
        "regularity_score": score,
        "avg_meal_time": avg_time,
    }


def stats_for_week(meals: list[dict], today, days: int = 7) -> dict:
    """周维度：一根柱 = 一天，当天所有餐次先求和。

    窗口是固定的最近 `days` 天日历日，中间没吃的那天补 0——否则「近 7 天」的柱子
    数量会随记录条数漂移，跟摘要里的均值对不上。
    """
    anchor = today.astimezone(CST)
    window = _window_from(anchor, days)
    by_day = {d: {k: 0.0 for k in NUTRIENT_KEYS} for d in window}
    in_window = []
    for meal in meals:
        d = str(meal.get("eaten_at", ""))[:10]
        if d in by_day:
            in_window.append(meal)
            for k in NUTRIENT_KEYS:
                by_day[d][k] += float(totals_of(meal).get(k) or 0)

    score, avg_time = regularity(in_window)
    # 均值只除有记录的天数。除以整个窗口的话，刚记第一餐的用户会看到
    # 「共 1 餐、平均 169 kcal」，而那一餐其实是 1180。
    active_days = len({str(m.get("eaten_at", ""))[:10] for m in in_window}) or 1
    return {
        "range_days": days,
        "meal_count": len(in_window),
        "avg": {k: _qty(sum(by_day[d][k] for d in window) / active_days)
                for k in ["kcal", "protein_g", "carb_g", "fat_g"]},
        "daily_kcal_trend": [_qty(by_day[d]["kcal"]) for d in window],
        "trend_labels": [d[5:] for d in window],
        "nutrition_composition": [{
            "date": d[5:],
            "protein_g": _qty(by_day[d]["protein_g"]),
            "carb_g": _qty(by_day[d]["carb_g"]),
            "fat_g": _qty(by_day[d]["fat_g"]),
        } for d in window],
        "regularity_score": score,
        "avg_meal_time": avg_time,
    }
