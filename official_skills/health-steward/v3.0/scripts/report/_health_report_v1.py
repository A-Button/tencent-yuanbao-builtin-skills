#!/usr/bin/env python3
"""health-report-v1.0 integration for health-assistant.

The existing report tools keep their legacy input/output contract. When callers pass
``report_data``, this module applies the richer daily/weekly gates and renders the
fixed mobile templates bundled under assets/ui/report/health-report-v1.0/.
"""

from __future__ import annotations

import sys
from pathlib import Path
_scripts = Path(__file__).resolve().parents[1]
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))
import _boot
_boot.install()

import html
import math
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import _report_html
from _errors import ActionError

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "assets" / "ui" / "report" / "health-report-v1.0"
DAILY_TEMPLATE = TEMPLATES / "daily_template.html"
WEEKLY_TEMPLATE = TEMPLATES / "weekly_template.html"
PLACEHOLDER_RE = re.compile(r"\{\{[^{}]+\}\}")
WEEKDAYS = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")
NUTRIENT_KEYS = ("kcal", "protein_g", "fat_g", "carb_g", "sodium_mg")


def _esc(value: object) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) else None


def _fmt(value, digits: int = 0, missing: str = "0") -> str:
    number = _number(value)
    if number is None:
        return missing
    if digits == 0:
        return f"{int(round(number)):,}"
    return f"{number:.{digits}f}"


def _artifact_filename(prefix: str, period: str, mode: str) -> str:
    """同一天、同一周只留一个文件名。

    ``mode`` 仍由调用方传入，用来标明这次写出的是完整报告；它不进文件名。
    以前文件名带微秒戳，同一次日报再写一遍就会在工作区里多一个 HTML，
    平台把这些 HTML 都当成产物下发。
    """
    del mode
    return f"{prefix}-{period}.html"


def _replace(template: str, values: dict[str, object]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace("{{" + key + "}}", str(value))
    unresolved = sorted(set(PLACEHOLDER_RE.findall(out)))
    if unresolved:
        raise ActionError("INVALID_ARGUMENT", "报告模板仍有未替换字段：" + ", ".join(unresolved))
    return out


def _parse_date(raw: object, field: str) -> date:
    if not isinstance(raw, str):
        raise ActionError("INVALID_ARGUMENT", f"{field} 必须是 YYYY-MM-DD。")
    try:
        return datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ActionError("INVALID_ARGUMENT", f"{field} 不是合法日期：{raw}") from exc


def _profile_bmr(profile: dict) -> int | None:
    weight = _number(profile.get("weight_kg"))
    height = _number(profile.get("height_cm"))
    age = _number(profile.get("age"))
    sex = profile.get("sex")
    if None in (weight, height, age) or sex not in {"male", "female"}:
        return None
    offset = 5 if sex == "male" else -161
    return int(round(10 * weight + 6.25 * height - 5 * age + offset))


def _meal_totals(meals: list) -> dict[str, float]:
    keys = ("kcal", "protein_g", "fat_g", "carb_g", "sodium_mg")
    totals = {key: 0.0 for key in keys}
    for meal in meals:
        if not isinstance(meal, dict):
            continue
        nutrients = meal.get("totals") if isinstance(meal.get("totals"), dict) else {}
        for key in keys:
            value = _number(nutrients.get(key))
            if value is not None:
                totals[key] += value
    return totals


def _pct(value: float, target) -> tuple[str, int]:
    target_n = _number(target)
    if target_n is None or target_n <= 0:
        return "—", 0
    raw = int(round(value / target_n * 100))
    return str(raw), max(0, min(100, raw))


def _balance_style(balance: float) -> dict[str, str]:
    pos = max(10.0, min(90.0, 50 + max(-600.0, min(600.0, balance)) / 600 * 40))
    if balance < -100:
        return {
            "state": "热量缺口",
            "color": "#0F6E56",
            "shadow": "rgba(15,110,86,.25)",
            "bg": "#EAF5F0",
            "position": f"{pos:.1f}",
        }
    if balance > 100:
        return {
            "state": "摄入大于消耗",
            "color": "#993C1D",
            "shadow": "rgba(153,60,29,.25)",
            "bg": "#FAECE7",
            "position": f"{pos:.1f}",
        }
    return {
        "state": "接近持平",
        "color": "#5F5E5A",
        "shadow": "rgba(95,94,90,.22)",
        "bg": "#F1EFE8",
        "position": f"{pos:.1f}",
    }


def _meal_cards(meals: list) -> str:
    cards = []
    for meal in meals:
        if not isinstance(meal, dict):
            continue
        totals = meal.get("totals") if isinstance(meal.get("totals"), dict) else {}
        dishes = []
        for food in meal.get("foods") or []:
            if not isinstance(food, dict):
                continue
            dishes.append(
                '<div class="dish"><span class="emoji">•</span>'
                f'<span>{_esc(food.get("name"))}<span class="portion">{_esc(food.get("portion"))}</span></span></div>'
            )
        scene = _esc(meal.get("scene") or "基于已记录内容汇总。")
        signal = _esc(meal.get("signal") or "本餐仅按已记录食物估算。")
        cards.append(
            '<div class="sheet">'
            '<div class="meal-head">'
            f'<h3>{_esc(meal.get("meal_type") or "餐食")}</h3>'
            f'<span class="time">{_esc(meal.get("time") or "")}</span>'
            f'<span class="kcal">{_fmt(totals.get("kcal"))}<small> kcal</small></span>'
            '</div>'
            f'<p class="scene">{scene}</p>'
            f'<div class="dishes">{"".join(dishes)}</div>'
            f'<div class="meal-signal">{signal}</div>'
            '</div>'
        )
    return "".join(cards)


def _exercise_cards(exercises: list) -> str:
    cards = []
    for exercise in exercises:
        if not isinstance(exercise, dict):
            continue
        distance = _number(exercise.get("distance_km"))
        pace = str(exercise.get("pace") or "").strip()
        if distance is not None and distance > 0:
            metrics = [
                ("时长", _fmt(exercise.get("duration_min")), "分钟"),
                ("距离", _fmt(distance, 1), "km"),
                ("配速", _esc(pace or "0"), ""),
                ("消耗", _fmt(exercise.get("kcal")), "kcal"),
            ]
        else:
            metrics = [
                ("时长", _fmt(exercise.get("duration_min")), "分钟"),
                ("组数", _fmt(exercise.get("sets")), "组"),
                ("次数", _fmt(exercise.get("reps")), "次"),
                ("消耗", _fmt(exercise.get("kcal")), "kcal"),
            ]
        metric_html = "".join(
            f'<div class="metric"><div class="v num">{value}<small>{unit}</small></div><div class="k">{label}</div></div>'
            for label, value, unit in metrics
        )
        cards.append(
            '<article class="exercise-card">'
            '<div class="exercise-head"><span class="emoji">•</span>'
            f'<h3>{_esc(exercise.get("name") or "运动")}</h3>'
            f'<span class="time">{_esc(exercise.get("time") or "")}</span>'
            f'<span class="kcal">{_fmt(exercise.get("kcal"))} kcal</span></div>'
            f'<div class="metrics">{metric_html}</div></article>'
        )
    if cards:
        return "".join(cards)
    return '<div class="missing">今天没有记录专门运动</div>'


def _partial_daily_html(data: dict, meals: list, exercises: list, totals: dict) -> str:
    day = _esc(data.get("date") or "今天")
    meal_cards = _meal_cards(meals)
    exercise_cards = _exercise_cards(exercises)
    return f'''<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>健康日报 · {day}</title><style>
:root{{--ink:#2C2C2A;--muted:#77756F;--line:#E2DED3;--diet:#D85A30;--sport:#185FA5;--bg:#FBFAF7}}*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:14px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif}}.page{{max-width:430px;margin:auto;padding:24px 12px 36px}}header{{padding:18px 12px 22px}}h1{{font:500 28px/1.25 "Songti SC",serif;margin:6px 0}}p{{margin:0}}.muted{{color:var(--muted)}}section{{border:1px solid var(--line);border-radius:20px;padding:10px;margin-top:12px}}h2{{font-size:16px;margin:4px 5px 12px}}.sheet{{background:#fff;border-radius:14px;padding:15px;margin-top:8px}}.meal-head,.exercise-head{{display:flex;align-items:baseline;gap:7px}}.meal-head h3,.exercise-head h3{{font-size:14px;margin:0}}.time{{font-size:10px;color:var(--muted)}}.kcal{{margin-left:auto;color:var(--diet);font-weight:700}}.scene,.meal-signal{{font-size:12px;margin-top:7px}}.dishes{{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-top:9px}}.dish{{font-size:12px}}.portion{{color:var(--muted);margin-left:4px}}.metrics{{display:grid;grid-template-columns:repeat(4,1fr);margin-top:10px}}.metric{{text-align:center;font-size:11px}}.metric .k{{color:var(--muted);font-size:9px}}.missing{{text-align:center;color:var(--muted);padding:12px}}.summary{{font-size:22px;font-weight:700;color:var(--diet)}}footer{{text-align:center;color:var(--muted);font-size:10px;padding-top:20px}}</style></head><body><main class="page"><header><div class="muted">{day}</div><h1>今天已记录的部分</h1><p class="muted">数据还不完整，以下只汇总已经提供的饮食与运动，不推断全天情况。</p></header><section><h2>01 已知数据</h2><div class="sheet"><div class="summary">{_fmt(totals.get("kcal"))} kcal</div><p class="muted">来自 {len(meals)} 餐记录；暂不计算全天总消耗和能量差值。</p></div></section><section><h2>02 摄入 · 饮食</h2>{meal_cards or '<div class="sheet missing">暂无饮食记录</div>'}</section><section><h2>03 消耗 · 运动</h2><div class="sheet">{exercise_cards}</div></section><section><h2>04 下一步</h2><div class="sheet"><p>补充缺失餐次、当天是否已记录完整，以及是否有专门运动后，再刷新完整日报。</p></div></section><footer>仅汇总已记录内容，不使用默认三餐或平均活动量补齐。</footer></main></body></html>'''


def build_daily(report_data: dict) -> dict:
    if not isinstance(report_data, dict):
        raise ActionError("INVALID_ARGUMENT", "report_data 必须是对象。")
    meals = [item for item in report_data.get("meals") or [] if isinstance(item, dict)]
    exercises = [item for item in report_data.get("exercises") or [] if isinstance(item, dict)]
    totals = _meal_totals(meals)
    profile = report_data.get("profile") if isinstance(report_data.get("profile"), dict) else {}
    bmr = _number(report_data.get("bmr_kcal"))
    bmr_source = "身体档案估算"
    if bmr is None:
        bmr = _profile_bmr(profile)
    if bmr is None:
        weight = _number(profile.get("weight_kg"))
        if weight is not None and weight > 0:
            bmr = weight * 22
            bmr_source = "最近体重 × 22 估算"
        else:
            bmr = 1320.0
            bmr_source = "成人参考基础代谢估算"
    daily_activity = _number(report_data.get("daily_activity_kcal"))
    activity_source = str(report_data.get("daily_activity_source") or "").strip()
    if daily_activity is None:
        daily_activity = bmr * 0.2
        activity_source = "按基础代谢的 20% 估算"
    active = sum(_number(item.get("kcal")) or 0.0 for item in exercises)
    total_burn = bmr + daily_activity + active
    intake = totals["kcal"]
    balance = intake - total_burn
    day = str(report_data.get("date") or date.today().isoformat())

    style = _balance_style(balance)
    kcal_target = _number(profile.get("target_kcal")) or total_burn
    profile_targets = {
        "kcal": kcal_target,
        "protein_g": _number(profile.get("target_protein_g")) or kcal_target * 0.20 / 4,
        "fat_g": _number(profile.get("target_fat_g")) or kcal_target * 0.30 / 9,
        "carb_g": _number(profile.get("target_carb_g")) or kcal_target * 0.50 / 4,
    }
    percents = {key: _pct(totals[key], target) for key, target in profile_targets.items()}
    recorded = {str(item.get("meal_type") or "") for item in meals}
    missing = [name for name in ("早餐", "午餐", "晚餐") if name not in recorded]
    missing_html = "" if not missing else f'<div class="missing">未记录：{_esc("、".join(missing))}</div>'
    meal_names = "、".join(str(item.get("meal_type") or "餐食") for item in meals)
    exercise_names = "、".join(str(item.get("name") or "运动") for item in exercises) or "无专门运动"
    protein_target = profile_targets["protein_g"]
    protein_good = protein_target is not None and totals["protein_g"] >= protein_target * 0.8
    goal = profile.get("goal")
    if protein_good:
        good_title = "蛋白质基础比较稳"
        good_body = f"今天记录到 {_fmt(totals['protein_g'])}g 蛋白质，接近或达到目标区间。"
    elif exercises:
        good_title = "今天有主动运动"
        good_body = f"记录了 {len(exercises)} 项运动，合计约 {_fmt(active)} kcal。"
    else:
        good_title = "饮食记录比较完整"
        good_body = f"今天共记录 {len(meals)} 餐，可以看清主要摄入结构。"
    if protein_target is not None and totals["protein_g"] < protein_target * 0.8:
        warn_title = "蛋白质还有缺口"
        warn_body = f"记录值约 {_fmt(totals['protein_g'])}g，低于目标 {_fmt(protein_target)}g。"
        tomorrow_title = "给一餐补上明确的蛋白质"
        tomorrow_body = "例如加 2 个鸡蛋、150g 鸡胸肉或 200g 豆腐，三选一即可。"
    else:
        warn_title = "只看一天，不下长期结论"
        warn_body = "单日能量差值会受份量估算和活动记录影响，重点看连续趋势。"
        tomorrow_title = "继续按餐次记录"
        tomorrow_body = "保持记录份量和运动时长，明天就能与今天直接比较。"
    if goal == "fat_loss" and balance < 0:
        energy_explanation = f"摄入 <b>{_fmt(intake)} kcal</b>，总消耗 <b>{_fmt(total_burn)} kcal</b>，形成 <b>{_fmt(abs(balance))} kcal</b> 热量缺口。"
    else:
        energy_explanation = f"摄入 <b>{_fmt(intake)} kcal</b>，总消耗 <b>{_fmt(total_burn)} kcal</b>，两者相差 <b>{_fmt(abs(balance))} kcal</b>。"

    values = {
        "DATE_SHORT": _esc(day[5:] if len(day) >= 10 else day),
        "DATE_DISPLAY": _esc(f"{day} · {report_data.get('weekday') or ''}".strip(" ·")),
        "HERO_TITLE": "今天的健康日报",
        "DAY_DESCRIPTION_HTML": _esc(f"按当前已记录的 {len(meals)} 餐和 {len(exercises)} 项运动计算；未记录餐次按 0 计入当前记录口径。"),
        "BALANCE_ABS_KCAL": _fmt(abs(balance)),
        "BALANCE_STATE_LABEL": style["state"],
        "BALANCE_DOT_COLOR": style["color"],
        "BALANCE_DOT_POSITION": style["position"],
        "BALANCE_DOT_SHADOW": style["shadow"],
        "BALANCE_EXPLAIN_BG": style["bg"],
        "BALANCE_SIGNED_TEXT": f"{int(round(balance)):+d}",
        "ENERGY_LEAD": _esc("今天的能量收支按当前饮食记录、基础代谢、日常活动和主动运动计算。"),
        "ENERGY_EXPLANATION_HTML": energy_explanation,
        "KCAL_EQUIVALENT_EMOJI": "●",
        "KCAL_EQUIVALENT_TITLE": f"约 {_fmt(abs(balance) / 116, 1)} 根中等香蕉",
        "KCAL_EQUIVALENT_NOTE": "按每根约116 kcal估算",
        "ACTIVITY_EQUIVALENT_EMOJI": "●",
        "ACTIVITY_EQUIVALENT_TITLE": f"约 {_fmt(abs(balance) / 60 * 10)} 分钟快走",
        "ACTIVITY_EQUIVALENT_NOTE": "仅作能量量级参考",
        "EQUIVALENT_DISCLAIMER": "仅帮助理解能量量级，不代表建议补吃或通过运动抵消。",
        "INTAKE_EMOJIS": "饮食",
        "INTAKE_SUMMARY": _esc(meal_names),
        "INTAKE_KCAL": _fmt(intake),
        "BURN_EMOJIS": "活动",
        "BURN_SUMMARY": _esc(f"基础代谢 + 日常活动 + {exercise_names}"),
        "TOTAL_BURN_KCAL": _fmt(total_burn),
        "MEAL_COUNT": str(len(meals)),
        "MEAL_CARDS_HTML": _meal_cards(meals) or '<div class="sheet missing">今天没有记录饮食</div>',
        "MISSING_MEAL_HTML": missing_html,
        "NUTRITION_CHART_SUBTITLE": "按个人目标计算；柱高上限为100%",
        "KCAL_PERCENT": percents["kcal"][0], "KCAL_BAR_HEIGHT": percents["kcal"][1],
        "PROTEIN_PERCENT": percents["protein_g"][0], "PROTEIN_BAR_HEIGHT": percents["protein_g"][1],
        "FAT_PERCENT": percents["fat_g"][0], "FAT_BAR_HEIGHT": percents["fat_g"][1],
        "CARB_PERCENT": percents["carb_g"][0], "CARB_BAR_HEIGHT": percents["carb_g"][1],
        "PROTEIN_G": _fmt(totals["protein_g"]), "FAT_G": _fmt(totals["fat_g"]), "CARB_G": _fmt(totals["carb_g"]),
        "NUTRITION_SUMMARY_HTML": _esc(f"已记录热量 {_fmt(intake)} kcal、蛋白质 {_fmt(totals['protein_g'])}g、脂肪 {_fmt(totals['fat_g'])}g、碳水 {_fmt(totals['carb_g'])}g。"),
        "EXERCISE_CARDS_HTML": _exercise_cards(exercises),
        "BMR_KCAL": _fmt(bmr), "DAILY_ACTIVITY_KCAL": _fmt(daily_activity), "ACTIVE_KCAL": _fmt(active),
        "BMR_EQUIVALENT": _esc(f"来源：{bmr_source}。"),
        "DAILY_ACTIVITY_EQUIVALENT": _esc(f"来源：{activity_source}。"),
        "ACTIVE_EMOJI": "●", "ACTIVE_SOURCE_TEXT": _esc(exercise_names), "ACTIVE_EQUIVALENT": "主动运动按已记录项目加总。",
        "GOOD_TITLE": good_title, "GOOD_BODY": _esc(good_body), "GOOD_CALC": _esc(f"蛋白质 {_fmt(totals['protein_g'])}g · 运动 {_fmt(active)} kcal"),
        "WARN_TITLE": warn_title, "WARN_BODY": _esc(warn_body), "WARN_CALC": _esc(f"摄入 {_fmt(intake)} − 消耗 {_fmt(total_burn)} = {int(round(balance)):+d} kcal"),
        "TOMORROW_TITLE": tomorrow_title, "TOMORROW_BODY": _esc(tomorrow_body),
        "FOOTER_TEXT": _esc(f"基于 {len(meals)} 条饮食记录与 {len(exercises)} 条运动记录；未记录项按 0 计入，基础消耗等估算项已标注来源。"),
    }
    html_text = _replace(DAILY_TEMPLATE.read_text(encoding="utf-8"), values)
    path = _report_html.write(html_text, _artifact_filename("health-daily", day, "complete"))
    return {
        "report_mode": "complete",
        "report_path": path,
        "intake_kcal": int(round(intake)),
        "total_burn_kcal": int(round(total_burn)),
        "balance_kcal": int(round(balance)),
    }


def _valid_day(item: dict) -> bool:
    if item.get("is_valid_day") is True:
        return True
    meals = item.get("meals") if isinstance(item.get("meals"), dict) else {}
    meal_count = sum(bool(meals.get(key)) for key in ("breakfast", "lunch", "dinner"))
    slots = item.get("exercise_slots") if isinstance(item.get("exercise_slots"), dict) else {}
    exercise_count = sum(bool(slots.get(key)) for key in ("noon", "commute", "evening"))
    return meal_count >= 2 or (meal_count >= 1 and exercise_count >= 1)


def _sparse_weekly_summary(data: dict, valid: list[dict]) -> str:
    meal_count = 0
    exercise_count = 0
    for item in valid:
        meals = item.get("meals") if isinstance(item.get("meals"), dict) else {}
        slots = item.get("exercise_slots") if isinstance(item.get("exercise_slots"), dict) else {}
        meal_count += sum(bool(meals.get(key)) for key in ("breakfast", "lunch", "dinner"))
        exercise_count += sum(bool(slots.get(key)) for key in ("noon", "commute", "evening"))
    return (
        f"本周仅记录 {len(valid)} 天，共有 {meal_count} 餐和 {exercise_count} 条运动记录。"
        "先继续按天记录饮食和运动；下周累计满 3 个有效日后生成完整周报，并在下一次周报查看双周趋势。"
    )


def _cell(value: object, css: str = "") -> str:
    if value is None or str(value).strip() == "":
        return '<td class="empty">暂无记录</td>'
    class_attr = f' class="{css}"' if css else ""
    return f"<td{class_attr}>{_esc(value)}</td>"


def _matrix_header(dates: list[date]) -> str:
    heads = ['<th class="corner">项目</th>']
    for index, current in enumerate(dates):
        heads.append(f"<th>{WEEKDAYS[index]}<small>{current.strftime('%m/%d')}</small></th>")
    return "<thead><tr>" + "".join(heads) + "</tr></thead>"


def _weekly_diet_matrix(dates: list[date], by_date: dict[str, dict]) -> str:
    rows = []
    for key, label in (("breakfast", "早餐"), ("lunch", "午餐"), ("dinner", "晚餐")):
        cells = []
        for current in dates:
            item = by_date.get(current.isoformat()) or {}
            meals = item.get("meals") if isinstance(item.get("meals"), dict) else {}
            meal = meals.get(key)
            cells.append(_cell(meal.get("summary") if isinstance(meal, dict) else None))
        rows.append(f"<tr><th>{label}</th>{''.join(cells)}</tr>")
    total_cells = [_cell(f"{_fmt((by_date.get(d.isoformat()) or {}).get('intake_kcal'))} kcal" if _number((by_date.get(d.isoformat()) or {}).get("intake_kcal")) is not None else None) for d in dates]
    rows.append(f'<tr class="total-row"><th>当日摄入</th>{"".join(total_cells)}</tr>')
    return _matrix_header(dates) + "<tbody>" + "".join(rows) + "</tbody>"


def _weekly_sport_matrix(dates: list[date], by_date: dict[str, dict]) -> str:
    rows = []
    for key, label in (("noon", "午间"), ("commute", "通勤/下班"), ("evening", "晚间")):
        cells = []
        for current in dates:
            item = by_date.get(current.isoformat()) or {}
            slots = item.get("exercise_slots") if isinstance(item.get("exercise_slots"), dict) else {}
            slot = slots.get(key)
            cells.append(_cell(slot.get("summary") if isinstance(slot, dict) else None))
        rows.append(f"<tr><th>{label}</th>{''.join(cells)}</tr>")
    total_cells = [_cell(f"{_fmt((by_date.get(d.isoformat()) or {}).get('active_kcal'))} kcal" if _number((by_date.get(d.isoformat()) or {}).get("active_kcal")) is not None else None) for d in dates]
    rows.append(f'<tr class="total-row"><th>运动消耗</th>{"".join(total_cells)}</tr>')
    return _matrix_header(dates) + "<tbody>" + "".join(rows) + "</tbody>"


def _weekly_plan_matrix(dates: list[date], plan: dict | None) -> tuple[str, list[dict]]:
    items = plan.get("days") if isinstance(plan, dict) and isinstance(plan.get("days"), list) else []
    by_weekday = {str(item.get("weekday")): item for item in items if isinstance(item, dict)}
    rows = []
    for key, label, css in (("breakfast", "早餐", "meal-cell"), ("lunch", "午餐", "meal-cell"), ("dinner", "晚餐", "meal-cell"), ("movement", "顺手运动", "move-cell")):
        rows.append(f"<tr><th>{label}</th>" + "".join(_cell((by_weekday.get(WEEKDAYS[i]) or {}).get(key), css) for i in range(7)) + "</tr>")
    targets = []
    for i in range(7):
        value = _number((by_weekday.get(WEEKDAYS[i]) or {}).get("target_balance_kcal"))
        targets.append(value)
    rows.append('<tr class="target-row"><th>目标差值</th>' + "".join(_cell(f"{int(round(v)):+d} kcal" if v is not None else None) for v in targets) + "</tr>")
    return _matrix_header(dates) + "<tbody>" + "".join(rows) + "</tbody>", items


def _trend_svg(dates: list[date], by_date: dict[str, dict]) -> str:
    intake = [_number((by_date.get(d.isoformat()) or {}).get("intake_kcal")) for d in dates]
    burn = [_number((by_date.get(d.isoformat()) or {}).get("total_burn_kcal")) for d in dates]
    values = [v for v in intake + burn if v is not None]
    if not values:
        return '<div class="trend-table"><div class="chart-note" style="padding:16px;text-align:center">暂无同口径能量数据</div></div>'
    low, high = min(values), max(values)
    spread = max(1.0, high - low)
    xs = [30 + i * 55 for i in range(7)]
    def points(series):
        return " ".join(f"{xs[i]},{18 + (high-v)/spread*100:.1f}" for i, v in enumerate(series) if v is not None)
    labels = "".join(f'<text x="{xs[i]}" y="142" text-anchor="middle" font-size="9" fill="#77756F">{WEEKDAYS[i][1:]}</text>' for i in range(7))
    return f'''<div class="trend-table"><div class="trend-plot"><svg viewBox="0 0 390 150" role="img" aria-label="每日摄入与消耗趋势"><polyline points="{points(intake)}" fill="none" stroke="#D85A30" stroke-width="3"/><polyline points="{points(burn)}" fill="none" stroke="#378ADD" stroke-width="3"/>{labels}</svg></div></div>'''


def build_weekly(report_data: dict) -> dict:
    if not isinstance(report_data, dict):
        raise ActionError("INVALID_ARGUMENT", "report_data 必须是对象。")
    start = _parse_date(report_data.get("week_start"), "week_start")
    end = _parse_date(report_data.get("week_end"), "week_end")
    if end - start != timedelta(days=6):
        raise ActionError("INVALID_ARGUMENT", "周报区间必须正好覆盖周一至周日 7 天。")
    dates = [start + timedelta(days=i) for i in range(7)]
    days = [item for item in report_data.get("days") or [] if isinstance(item, dict)]
    valid = [item for item in days if _valid_day(item)]
    if len(valid) < 3:
        return {"report_mode": "sparse", "report_path": None, "valid_days": len(valid), "summary": _sparse_weekly_summary(report_data, valid)}

    by_date = {str(item.get("date")): item for item in days if item.get("date")}
    energy_days = [item for item in valid if _number(item.get("intake_kcal")) is not None and _number(item.get("total_burn_kcal")) is not None]
    intake = sum(_number(item.get("intake_kcal")) or 0 for item in energy_days)
    burn = sum(_number(item.get("total_burn_kcal")) or 0 for item in energy_days)
    balance = intake - burn if energy_days else None
    style = _balance_style(balance or 0)
    complete_energy = len(energy_days) == len(valid)
    energy_label = style["state"] if balance is not None else "暂无法计算"
    signed = f"{int(round(balance)):+d}" if balance is not None else "未知"
    profile = report_data.get("profile") if isinstance(report_data.get("profile"), dict) else {}

    overall = [
        '<div class="sheet">',
        '<div class="energy-kicker">本周有效记录日的能量收支</div>',
        f'<div class="energy-result"><span class="value num">{_fmt(abs(balance) if balance is not None else None)}</span><span class="unit">kcal</span><span class="label">{energy_label}</span></div>',
        f'<p class="energy-lead">按 {len(energy_days)} 个摄入与消耗口径完整的有效日统计，未记录日不按 0 计算。</p>',
        '<div class="energy-coverage"><div class="balance-axis"><div class="balance-track"></div><div class="balance-center"></div><div class="balance-dot"></div></div><div class="balance-labels"><span class="left">消耗大于摄入</span><span class="mid">持平</span><span class="right">摄入大于消耗</span></div></div>',
        '<div class="week-kpis">',
        f'<div class="week-kpi"><div class="v num">{_fmt(intake)}</div><div class="k">累计摄入 kcal</div></div>',
        f'<div class="week-kpi"><div class="v num">{_fmt(burn)}</div><div class="k">累计消耗 kcal</div></div>',
        f'<div class="week-kpi"><div class="v num">{signed}</div><div class="k">累计差值 kcal</div></div>',
        f'<div class="week-kpi"><div class="v num">{len(valid)}</div><div class="k">有效记录日</div></div>',
        '</div></div>',
        '<div class="sheet"><div class="chart-head"><div><div class="chart-title">每日摄入与消耗</div><div class="chart-sub">橙色摄入 · 蓝色消耗</div></div></div>',
        _trend_svg(dates, by_date),
        f'<div class="chart-note">{"7 天口径完整" if complete_energy and len(valid) == 7 else f"仅按 {len(energy_days)} 个同口径有效日展示"}；空白日不补造。</div></div>',
    ]

    nutrition_rows = [item.get("nutrition") for item in valid if isinstance(item.get("nutrition"), dict)]
    averages = {}
    for key in ("protein_g", "fat_g", "carb_g"):
        values_n = [_number(row.get(key)) for row in nutrition_rows]
        known = [v for v in values_n if v is not None]
        averages[key] = sum(known) / len(known) if known else None
    kcal_avg = intake / len(energy_days) if energy_days else None
    nutrient_values = {"kcal": kcal_avg, **averages}
    target_values = {"kcal": profile.get("target_kcal"), "protein_g": profile.get("target_protein_g"), "fat_g": profile.get("target_fat_g"), "carb_g": profile.get("target_carb_g")}
    labels = (("kcal", "热量", "over"), ("protein_g", "蛋白质", "protein"), ("fat_g", "脂肪", "fat"), ("carb_g", "碳水", "carb"))
    bars = []
    for key, label, css in labels:
        value = nutrient_values[key]
        pct_text, height = _pct(value or 0, target_values[key])
        unit = "kcal" if key == "kcal" else "g"
        bars.append(f'<div class="col"><div class="bar-value num">{pct_text}%</div><div class="bar {css}" style="height:{height}%"></div><div class="bar-label">{label}<small>{_fmt(value)} {unit}</small></div></div>')
    nutrition_sheet = f'<div class="sheet"><div class="nutri-title">有效记录日营养日均</div><div class="nutri-sub">仅统计有营养数据的记录日</div><div class="nutri-chart"><div class="scale-line s100"><span>100%</span></div><div class="scale-line s50"><span>50%</span></div><div class="bars">{"".join(bars)}</div></div><p class="insight-line">蛋白质、脂肪和碳水均按现有记录求日均；缺失字段保持未知。</p></div>'

    exercise_items = []
    active_total = 0.0
    duration_total = 0.0
    for item in valid:
        slots = item.get("exercise_slots") if isinstance(item.get("exercise_slots"), dict) else {}
        for slot in slots.values():
            if isinstance(slot, dict):
                exercise_items.append(slot)
                active_total += _number(slot.get("kcal")) or 0
                duration_total += _number(slot.get("duration_min")) or 0
    sport_summary = f'<div class="sheet"><div class="sport-kpis"><div class="sport-kpi"><div class="v num">{len(exercise_items)}</div><div class="k">运动记录</div></div><div class="sport-kpi"><div class="v num">{_fmt(duration_total)}<small> 分钟</small></div><div class="k">已知时长</div></div><div class="sport-kpi"><div class="v num">{_fmt(active_total)}<small> kcal</small></div><div class="k">运动消耗</div></div></div><div class="sport-summary">只汇总已记录项目；未提供时长或消耗的项目不补估。</div></div>'

    plan_matrix, plan_items = _weekly_plan_matrix(dates, report_data.get("next_week_plan"))
    plan_targets = [_number(item.get("target_balance_kcal")) for item in plan_items]
    known_targets = [v for v in plan_targets if v is not None]
    target_sum = sum(known_targets) if known_targets else None
    plan_result = "" if target_sum is None else f'<div class="plan-result"><div class="k">计划口径</div><div class="main">下周 7 天目标差值合计 {_fmt(target_sum)} kcal</div><div class="math">仅汇总执行表中明确填写的目标</div><div class="note">实际结果以真实饮食与活动记录为准。</div></div>'
    advice_sheet = '<div class="sheet"><div class="advice-pair"><article class="advice-card d"><span class="advice-tag">饮食</span><h3>延续记录最稳定的餐次</h3><p>先复用本周最容易执行的早餐或午餐结构，再按真实份量调整。</p><div class="why">不根据空白日推断饮食问题。</div></article><article class="advice-card s"><span class="advice-tag">运动</span><h3>把运动放回已有时段</h3><p>优先复用本周已经做到的快走、力量或球类时段。</p><div class="why">不使用高强度运动补偿饮食。</div></article></div></div>'

    valid_dates = {str(item.get("date")) for item in valid}
    coverage = "".join(f'<i class="{"on" if d.isoformat() in valid_dates else ""}"></i>' for d in dates)
    values = {
        "WEEK_TITLE": _esc(f"{start.strftime('%m/%d')}–{end.strftime('%m/%d')}"),
        "DATE_RANGE_DISPLAY": _esc(f"{start.isoformat()} — {end.isoformat()}"),
        "HERO_TITLE": "这一周，吃与动放在一起看",
        "WEEK_DESCRIPTION_HTML": _esc(f"本周共有 {len(valid)} 个有效记录日；未记录日保持空白，不按 0 计算。"),
        "COVERAGE_DOTS_HTML": coverage,
        "COVERAGE_TEXT": f"{len(valid)}/7 天有效记录",
        "BALANCE_DOT_COLOR": style["color"], "BALANCE_DOT_POSITION": style["position"], "BALANCE_DOT_SHADOW": style["shadow"], "BALANCE_SIGNED_TEXT": signed,
        "OVERALL_SHEETS_HTML": "".join(overall),
        "DIET_META": f"{len(valid)} 天有效记录",
        "NUTRITION_SHEET_HTML": nutrition_sheet,
        "DIET_MATRIX_HTML": _weekly_diet_matrix(dates, by_date),
        "SPORT_META": f"{len(exercise_items)} 条运动",
        "SPORT_SUMMARY_SHEET_HTML": sport_summary,
        "SPORT_MATRIX_HTML": _weekly_sport_matrix(dates, by_date),
        "ADVICE_SHEET_HTML": advice_sheet,
        "PLAN_MATRIX_HTML": plan_matrix,
        "PLAN_RESULT_HTML": plan_result,
        "FOOTER_TEXT": _esc(f"周累计按 {len(energy_days)} 个同口径有效日计算；未记录日不按 0 处理。"),
    }
    html_text = _replace(WEEKLY_TEMPLATE.read_text(encoding="utf-8"), values)
    path = _report_html.write(html_text, _artifact_filename("health-weekly", end.isoformat(), "complete"))
    return {"report_mode": "complete", "report_path": path, "valid_days": len(valid), "energy_days": len(energy_days), "intake_kcal": int(round(intake)), "total_burn_kcal": int(round(burn)), "balance_kcal": int(round(balance)) if balance is not None else None, "calendar_prompt": "要不要一键帮你同步到日历？"}
