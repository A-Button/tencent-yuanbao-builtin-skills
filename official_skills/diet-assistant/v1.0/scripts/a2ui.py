#!/usr/bin/env python3
"""Attach XCard display fields onto the shared diet payload's current_meal."""

from __future__ import annotations

from store import MEAL_LABEL

# 绝对地址：前端不按自己的 origin 补相对路径，只能由 skill 给全。
# 代价是环境写死——测试和预发环境点开卡片也会跳到线上域名。
DETAIL_JUMP_URL = "https://yuanbao.tencent.com/e/diet-assistant?yb_top_bar=1&need_xcard_token=1"

# 用户没传图时出卡用的兜底图。只写进 structuredContent，不回写档案——
# 档案里 photo_url 仍是 null，下次有了真图不会被这张占位图卡住。
FALLBACK_PHOTO_URL = (
    "https://cdn-pro.yuanbao.tencent.com/public/pro/"
    "NTJjYzZjMDItMzI2Yy00ZjNmLWJiNDYtMmY3ZmVmZWY2NzEy.png?width=294&height=344"
)


def _text(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def _live_photo_url(value: object) -> str | None:
    """只认可给 <img src> 用的 http(s) 地址。data URI / 空串都当没图。"""
    raw = _text(value).strip()
    if raw.startswith(("https://", "http://")):
        return raw
    return None


def _fill_photo_url(meal: dict, *, with_badge: bool = False) -> None:
    """出卡时保证 photo_url 是可加载的地址：有实拍用实拍，没有用兜底图。

    今日食书的摘要对象没有 photo_badge 这个字段（schema 不允许多出来），
    只在 current_meal 上打角标。
    """
    live = _live_photo_url(meal.get("photo_url"))
    meal["photo_url"] = live or FALLBACK_PHOTO_URL
    if with_badge:
        meal["photo_badge"] = "实拍" if live else "无图"


def enrich_display_fields(app_view: dict) -> dict:
    """Write XCard-bound fields onto current_meal. Mutates and returns app_view.

    The A2UI / platform template binds paths like /current_meal/card_title directly.
    HTML still reads the same current_meal / today / stats object. No second payload.
    """
    meal = app_view.get("current_meal")
    if isinstance(meal, dict) and meal:
        meal_type = _text(meal.get("meal_type"))
        meal["card_title"] = "今日饮食记录"
        meal["foods_label"] = "本餐 食物"
        meal["jump_url"] = DETAIL_JUMP_URL
        meal["meal_type_display"] = MEAL_LABEL.get(meal_type, "一餐")
        _fill_photo_url(meal, with_badge=True)
        # 营养账单顶部「AI估值」。模板有的绑 /current_meal/totals/ai_price，有的绑顶层。
        price = (meal.get("totals") or {}).get("ai_price")
        if price is not None:
            meal["ai_price"] = price
            meal["ai_price_display"] = f"¥{price:g}"
        app_view["current_meal"] = meal

    # 今日食书每张卡自己决定用实拍还是兜底，不跟 current_meal 绑死。
    today = app_view.get("today")
    if isinstance(today, dict):
        grouped = today.get("meals_by_type") or {}
        if isinstance(grouped, dict):
            for meals in grouped.values():
                if not isinstance(meals, list):
                    continue
                for summary in meals:
                    if isinstance(summary, dict):
                        _fill_photo_url(summary)

    return app_view
