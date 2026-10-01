#!/usr/bin/env python3
"""Render Bazi and Western adapter payloads as a standalone HTML chart."""

from __future__ import annotations

import argparse
import html
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import chart_guidance
import western_profile
import western_mascots
import western_emphasis


PLANET_ZH = {
    "sun": "太阳",
    "moon": "月亮",
    "mercury": "水星",
    "venus": "金星",
    "mars": "火星",
    "jupiter": "木星",
    "saturn": "土星",
    "uranus": "天王星",
    "neptune": "海王星",
    "pluto": "冥王星",
}
ASPECT_ZH = {
    "conjunction": "合相",
    "sextile": "六合",
    "square": "刑相",
    "trine": "拱相",
    "opposition": "冲相",
}
COLUMNS = ("year", "month", "day", "hour")
COLUMN_ZH = {"year": "年柱", "month": "月柱", "day": "日柱", "hour": "时柱"}
ELEMENT_ORDER = ("木", "火", "土", "金", "水")
CALENDAR_ZH = {"gregorian": "公历", "lunar": "农历"}
TIME_PRECISION_ZH = {
    "exact": "精确时间",
    "shichen": "时辰范围",
    "approximate": "大概时间",
    "range": "时间范围",
    "unknown": "时间未知",
    "withheld": "时间保密",
    "unspecified": "未提供精确时间",
}


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def load_payload(path: Path | None, expected: str) -> dict[str, Any] | None:
    if path is None:
        return None
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if payload.get("chart_system") != expected:
        raise ValueError(f"{path} 不是 {expected} 盘面。")
    return payload


def input_summary(payload: dict[str, Any]) -> str:
    item = payload.get("input", {})
    location = item.get("location", {})
    precision = item.get("time_precision", {})
    precision_label = TIME_PRECISION_ZH.get(
        precision.get("kind"), "时间状态未标注"
    )
    if item.get("chart_precision") == "time-range":
        return bazi_input_summary(payload)
    if item.get("chart_precision") == "date-only":
        return (
            f"{esc(item.get('birth_date', '—'))} · "
            f"{esc(location.get('label', '—'))} · "
            f"日期初盘（{esc(precision_label)}）"
        )
    local_datetime = str(item.get("local_datetime") or "—").replace("T", " ")[:16]
    return (
        f"{esc(local_datetime)} · "
        f"{esc(location.get('label', '—'))} · {esc(precision_label)}"
    )


def bazi_input_summary(payload: dict[str, Any]) -> str:
    item = payload.get("input", {})
    location = item.get("location", {})
    precision = item.get("time_precision", {})
    calendar = CALENDAR_ZH.get(item.get("calendar"), "公历")
    precision_label = TIME_PRECISION_ZH.get(
        precision.get("kind"), str(precision.get("kind", "—"))
    )
    if item.get("chart_precision") == "time-range":
        return (
            f"{esc(item.get('birth_date', '—'))} · {esc(item.get('time_range_label', '出生时段'))} · "
            f"{esc(location.get('label', '—'))} · {calendar}"
        )
    if item.get("chart_precision") == "date-only":
        return (
            f"{esc(item.get('birth_date', '—'))} · "
            f"{esc(location.get('label', '—'))} · {calendar} · 日期初盘（{esc(precision_label)}）"
        )
    datetime_value = (
        item.get("original_lunar_datetime")
        if item.get("calendar") == "lunar"
        else item.get("local_datetime")
    )
    local_datetime = str(datetime_value or "—").replace("T", " ")[:16]
    return (
        f"{esc(local_datetime)} · {esc(location.get('label', '—'))} · "
        f"{calendar} · {esc(precision_label)}"
    )


def boundary_date(value: Any) -> str:
    if not value:
        return ""
    return str(value).replace("T", " ")[:10]


def bazi_date_only_scope(payload: dict[str, Any]) -> str:
    if payload.get("chart", {}).get("precision") == "time-range":
        return "已按所给时段核验；以下保留范围内不变的结果，跨边界的柱并列显示。"
    kind = payload.get("input", {}).get("time_precision", {}).get("kind")
    if kind == "approximate":
        return "已记录大概时间；当前版本仍按当地整日采样，未按大概时间缩小范围。"
    if kind == "range":
        return "已记录时间范围；当前版本仍按当地整日采样，未缩小到所给时段。"
    if kind == "unknown":
        return "出生时间不清楚；以下只显示整日确定的结果，变化项单独标出。"
    if kind == "withheld":
        return "未使用未披露的出生时间；以下只显示整日确定的结果，变化项单独标出。"
    return "未提供精确出生时间；以下只显示整日确定的结果，变化项单独标出。"


def render_guidance(guide: dict[str, Any]) -> str:
    system = str(guide.get("system", "chart"))
    precision = str(guide.get("precision", "unknown"))
    guide_id = f"guide-{system}-{precision}"
    items = "".join(
        f"""
        <article class="guide-item">
          <span>{esc(item.get('label', ''))}</span>
          <strong>{esc(item.get('title', ''))}</strong>
          <p>{esc(item.get('body', ''))}</p>
        </article>"""
        for item in guide.get("items", [])
        if isinstance(item, dict)
    )
    return f"""
      <aside class="reading-guide" data-guide-system="{esc(system)}"
        data-guide-precision="{esc(precision)}"
        data-guide-version="{esc(guide.get('schema_version', ''))}"
        aria-labelledby="{esc(guide_id)}">
        <header>
          <div><span>规则生成</span><h3 id="{esc(guide_id)}">{esc(guide.get('title', '盘面导读'))}</h3></div>
          <p>{esc(guide.get('subtitle', ''))}</p>
        </header>
        <div class="guide-grid">{items}</div>
      </aside>"""


def render_bazi_date_only(payload: dict[str, Any]) -> str:
    chart = payload["chart"]
    stable = chart.get("stable", {})
    possible = chart.get("possible", {})
    stable_pillars = stable.get("pillars", {})
    possible_pillars = possible.get("pillars", {})
    cards = []
    for key in COLUMNS[:3]:
        value = stable_pillars.get(key)
        values = possible_pillars.get(key, [])
        if value:
            main = esc(value)
            note = ""
            state_class = ""
        elif values:
            main = " / ".join(esc(item) for item in values) if len(values) <= 2 else "待定"
            note = f"随出生时刻变化 · {len(values)} 种结果"
            state_class = " variable-pillar"
        else:
            main = "—"
            note = "当前不可确定"
            state_class = " variable-pillar"
        note_html = f'<div class="meta">{note}</div>' if note else ""
        cards.append(
            f"""
            <article class="pillar{state_class}">
              <div class="eyebrow">{COLUMN_ZH[key]}</div>
              <div class="glyph">{main}</div>
              {note_html}
            </article>"""
        )
    hour_values = possible_pillars.get("hour", [])
    stable_hour = stable_pillars.get("hour")
    hour_note = "所给时段范围内一致" if stable_hour else (
        f"随出生时刻变化 · {len(hour_values)} 种可能"
        if hour_values
        else "需要出生时刻才能确定"
    )
    hour_html = f"""
      <aside class="hour-status" aria-label="时柱状态">
        <div class="eyebrow">时柱</div>
        <strong>{esc(stable_hour or (' / '.join(hour_values) if chart.get('precision') == 'time-range' and 0 < len(hour_values) <= 2 else '待定'))}</strong>
        <p>{hour_note}</p>
      </aside>"""
    day_master = stable.get("day_master") or {}
    day_master_html = ""
    if day_master:
        polarity_zh = {"yang": "阳", "yin": "阴"}.get(day_master.get("polarity"), "—")
        day_master_html = (
            '<div class="day-master"><span>日主</span><strong>'
            f"{esc(day_master.get('stem', '—'))} · {polarity_zh}{esc(day_master.get('element', ''))}"
            "</strong></div>"
        )
    return f"""
    <section class="panel">
      <header class="panel-head">
        <div><span class="index">01</span><h2>四柱八字</h2></div>
        <span class="tag">{'时段范围盘' if chart.get('precision') == 'time-range' else '日期初盘'}</span>
      </header>
      <p class="input-summary">{bazi_input_summary(payload)}</p>
      <p class="scope date-only-scope">{bazi_date_only_scope(payload)}</p>
      {day_master_html}
      <div class="date-only-layout">
        <div class="date-pillar-grid">{''.join(cards)}</div>
        {hour_html}
      </div>
    </section>"""


def render_bazi(payload: dict[str, Any]) -> str:
    chart = payload["chart"]
    if chart.get("precision") == "date-only" or (chart.get("precision") == "time-range" and not chart.get("pillars")):
        return render_bazi_date_only(payload)
    pillars = chart["pillars"]
    details = chart["details"]
    elements = details["five_elements"]
    ten_gods = details.get("ten_gods", {}).get("heavenly_stems", {})
    hidden_stems = details.get("hidden_stems", {})
    growth = details.get("twelve_growth_stages", {})
    day_master = details.get("day_master", {})
    polarity_zh = {"yang": "阳", "yin": "阴"}.get(day_master.get("polarity"), "—")
    cells = []
    for key in COLUMNS:
        hidden_html = "".join(
            f"<span>{esc(item.get('stem', ''))}<small>{esc(item.get('ten_god', ''))}</small></span>"
            for item in hidden_stems.get(key, [])
        )
        cells.append(
            f"""
            <article class="pillar">
              <div class="eyebrow">{COLUMN_ZH[key]}</div>
              <div class="ten-god">{esc(ten_gods.get(key, '—'))}</div>
              <div class="glyph">{esc(pillars[key])}</div>
              <div class="meta">{esc(elements[key])}</div>
              <div class="mini-label">藏干</div>
              <div class="hidden">{hidden_html}</div>
              <div class="growth"><small>十二长生</small><span>{esc(growth.get(key, '—'))}</span></div>
            </article>"""
        )
    previous_jie = details.get("previous_jie") or {}
    next_jie = details.get("next_jie") or {}
    counts = details.get("element_counts", {}).get(
        "visible_stems_and_branches_unweighted", {}
    )
    hidden_counts = details.get("element_counts", {}).get(
        "hidden_stems_unweighted", {}
    )
    counts_html = "".join(
        f"<div><strong>{element}</strong><span>{esc(counts.get(element, 0))}</span></div>"
        for element in ELEMENT_ORDER
    )
    hidden_counts_html = "".join(
        f"<div><strong>{element}</strong><span>{esc(hidden_counts.get(element, 0))}</span></div>"
        for element in ELEMENT_ORDER
    )
    luck = details.get("luck_cycles")
    luck_html = ""
    if isinstance(luck, dict) and luck.get("cycles"):
        cycles_html = "".join(
            f"<div><strong>{esc(item['gan_zhi'])}</strong>"
            f"<span>{esc(item['start_age'])}—{esc(item['end_age'])}岁</span>"
            f"<small>{esc(item['start_year'])}—{esc(item['end_year'])}</small></div>"
            for item in luck["cycles"]
        )
        luck_html = f"""
        <div class="luck">
          <h3>大运周期 <small>{esc(luck.get('direction', ''))} · {esc(luck.get('calculation_method', ''))}</small></h3>
          <div class="luck-grid">{cycles_html}</div>
        </div>"""
    return f"""
    <section class="panel">
      <header class="panel-head">
        <div><span class="index">01</span><h2>四柱八字</h2></div>
        <span class="tag">{'范围内四柱一致' if chart.get('precision') == 'time-range' else '完整盘'}</span>
      </header>
      <p class="input-summary">{bazi_input_summary(payload)}</p>
      <div class="day-master"><span>日主</span><strong>{esc(day_master.get('stem', '—'))} · {polarity_zh}{esc(day_master.get('element', ''))}</strong></div>
      <div class="pillar-grid">{''.join(cells)}</div>
      <div class="facts-row">
        <div>
          <h3>五行计数 <small>仅作索引，不等于强弱</small></h3>
          <div class="count-block"><span>表层</span><div class="element-counts">{counts_html}</div></div>
          <div class="count-block"><span>藏干</span><div class="element-counts">{hidden_counts_html}</div></div>
        </div>
      </div>
      <div class="boundary">
        <div><span>前一节令</span><strong>{esc(previous_jie.get('name', '—'))}</strong><small>{esc(boundary_date(previous_jie.get('local_datetime')))}</small></div>
        <div><span>后一节令</span><strong>{esc(next_jie.get('name', '—'))}</strong><small>{esc(boundary_date(next_jie.get('local_datetime')))}</small></div>
      </div>
      {luck_html}
    </section>"""


def render_western_date_only(
    payload: dict[str, Any], panel_index: int = 1
) -> str:
    return render_western(payload, panel_index)


def render_western(payload: dict[str, Any], panel_index: int = 1) -> str:
    profile = western_profile.build_profile(payload)
    sun_hero, rows = "", []
    for item in profile["items"]:
        key = item["key"]
        status = item["status"]
        if key == "sun":
            mascot = western_mascots.asset_for_sun(item)
            mascot_html = (
                f'<img class="zodiac-mascot" data-mascot-sign="{esc(mascot["sign"])}" '
                f'src="{mascot["src"]}" width="{mascot["width"]}" height="{mascot["height"]}" '
                'alt="" decoding="async">'
                if mascot else ""
            )
            identity_tag = "h1" if panel_index == 1 else "h2"
            hero_class = " zodiac-hero-text-only" if not mascot else ""
            status_note = (
                f'<p class="zodiac-status-note">{esc(item["summary"])}</p>'
                if status != "available" else ""
            )
            hero_note = (
                f'<p class="zodiac-hero-note">{western_emphasis.paragraph_html(item, "summary")}</p>'
                if status == "available" else ""
            )
            sun_hero = f"""
          <header class="zodiac-hero{hero_class}" data-zodiac-key="sun" data-status="{status}">
            <div class="zodiac-hero-copy">
              <{identity_tag} class="zodiac-sign" aria-label="太阳{esc(item['sign_label'])}">{esc(item['sign_label'])}</{identity_tag}>
              {hero_note}
              {status_note}
            </div>
            <div class="zodiac-hero-art">{mascot_html}</div>
          </header>"""
        else:
            status_note = (
                f'<dd class="zodiac-fact-note">{esc(item["summary"])}</dd>'
                if status != "available"
                else f'<dd class="zodiac-fact-note">{esc(item["tagline"])}</dd>'
            )
            rows.append(f"""
            <div class="zodiac-fact" data-zodiac-key="{key}" data-status="{status}">
              <dt>{esc(item['label'])}</dt>
              <dd class="zodiac-fact-sign">{esc(item['sign_label'])}</dd>
              {status_note}
            </div>""")
    return f"""
    <section class="panel zodiac-panel" aria-label="天体星座" data-zodiac-profile="1.0.0" data-precision="{profile['precision']}">
      <div class="zodiac-report-card">
        {sun_hero}
        <section class="zodiac-overview" aria-label="星盘速览">
          <h2 class="zodiac-section-heading">星盘速览</h2>
          <dl class="zodiac-facts" aria-label="上升、月亮、金星、水星">{''.join(rows)}</dl>
        </section>
      </div>
    </section>"""


def render_document(bazi: dict[str, Any] | None, western: dict[str, Any] | None) -> str:
    if not bazi and not western:
        raise ValueError("至少提供一个盘面文件。")
    panels = []
    if bazi:
        panels.append(render_bazi(bazi))
    if western:
        panels.append(render_western(western, panel_index=2 if bazi else 1))
    if bazi and not western:
        document_title = "八字排盘"
        document_kicker = "盘面事实 · 简析见对话"
    elif western and not bazi:
        document_title = "我的星座"
        document_kicker = "看见不止一面的自己"
    else:
        document_title = "出生盘面"
        document_kicker = "两套体系 · 分别解读"
    footer_html = (
        "" if western and not bazi else
        "<footer>AI生成内容｜传统文化与自我反思，仅供参考，不是经科学验证的预测，也不构成医疗、法律、投资或其他专业建议。</footer>"
    )
    location_source = (western or {}).get("input", {}).get("location", {}).get("source", "")
    body_class = "zodiac-only" if western and not bazi else "traditional-chart"
    zodiac_css = (
        (Path(__file__).resolve().parents[1] / "assets" / "zodiac-result.css").read_text(encoding="utf-8")
        if western else ""
    )
    zodiac_poster_scripts = (
        '<script>'
        + (Path(__file__).resolve().parents[1] / "assets" / "vendor" / "html2canvas.min.js").read_text(encoding="utf-8")
        + '</script><script>'
        + (Path(__file__).resolve().parents[1] / "assets" / "result-image.js").read_text(encoding="utf-8")
        + '</script><script>'
        + (Path(__file__).resolve().parents[1] / "assets" / "zodiac-result.js").read_text(encoding="utf-8")
        + '</script>'
        if western and not bazi else ""
    )
    zodiac_actions = """
  <div class="zodiac-actions" aria-label="结果操作">
    <button type="button" id="zodiac-copy-result" class="secondary">复制给元宝</button>
    <button type="button" id="zodiac-save-image" class="primary">保存或分享图片</button>
  </div>
  <div id="zodiac-image-mount"></div>
  <div id="zodiac-toast" class="zodiac-toast" role="status" aria-live="polite" hidden></div>
  <dialog id="zodiac-copy-dialog" aria-labelledby="zodiac-copy-title">
    <h2 id="zodiac-copy-title">手动复制星盘结果</h2>
    <p>浏览器未允许自动复制。选中下方内容后，可使用系统复制粘贴给元宝。</p>
    <textarea id="zodiac-copy-fallback" readonly aria-label="星盘结果复制内容"></textarea>
    <div class="zodiac-dialog-actions">
      <button type="button" id="zodiac-close-copy">关闭</button>
      <button type="button" id="zodiac-select-copy" class="primary">全选内容</button>
    </div>
  </dialog>
""" if western and not bazi else ""
    masthead_html = (
        f'<header class="masthead"><h1>{document_title}</h1><p>{document_kicker}</p></header>'
        if bazi else ""
    )
    # Keep source provenance in the document metadata, not in the result-page footer.
    attribution_meta = ""
    if "GeoNames:" in str(location_source):
        attribution_meta = '<meta name="data-attribution" content="Coordinates: GeoNames (https://www.geonames.org/), CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/); selected city coordinates mapped to built-in aliases.">'
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{document_title}</title>
  {attribution_meta}
  <style>
    :root {{ color-scheme: light; --paper:#f5f1e8; --ink:#20211f; --muted:#77736a; --line:#d8d0c1; --accent:#9b4038; --card:#fffdf7; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:var(--paper); color:var(--ink); font-family:ui-serif,"Songti SC","Noto Serif CJK SC",serif; }}
    main {{ width:min(1080px,100%); margin:0 auto; padding:clamp(22px,5vw,64px); }}
    .masthead {{ display:flex; justify-content:space-between; align-items:end; gap:18px; margin-bottom:28px; border-bottom:1px solid var(--ink); padding-bottom:18px; }}
    h1 {{ margin:0; font-size:clamp(30px,6vw,58px); letter-spacing:-.04em; font-weight:500; }}
    .masthead p {{ margin:0 0 6px; color:var(--muted); font:12px ui-monospace,monospace; letter-spacing:.12em; text-transform:uppercase; }}
    .panel {{ background:var(--card); border:1px solid var(--line); padding:clamp(18px,4vw,34px); margin:18px 0; box-shadow:0 18px 60px rgba(45,38,27,.06); }}
    .panel-head {{ display:flex; justify-content:space-between; align-items:center; gap:16px; }}
    .panel-head>div {{ display:flex; align-items:baseline; gap:12px; }}
    .panel h2 {{ margin:0; font-size:24px; font-weight:600; }}
    .index {{ color:var(--accent); font:12px ui-monospace,monospace; }}
    .tag {{ border:1px solid var(--line); padding:5px 9px; color:var(--muted); font:11px ui-monospace,monospace; }}
    .input-summary,.scope {{ color:var(--muted); font:12px/1.7 ui-monospace,monospace; }}
    .input-summary {{ padding-bottom:16px; border-bottom:1px solid var(--line); }}
    .day-master {{ display:flex; align-items:baseline; gap:10px; width:max-content; margin:18px auto 0; border-bottom:1px solid var(--accent); padding:0 4px 5px; }}
    .day-master span {{ color:var(--muted); font-size:11px; letter-spacing:.12em; }}
    .day-master strong {{ color:var(--accent); font-size:16px; }}
    .pillar-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:10px; margin:22px 0; }}
    .pillar {{ text-align:center; border-right:1px solid var(--line); padding:8px; }}
    .pillar:last-child {{ border:0; }}
    .date-only-scope {{ max-width:760px; margin:12px 0 0; }}
    .date-only-layout {{ display:grid; grid-template-columns:minmax(0,3fr) minmax(150px,1fr); gap:16px; align-items:stretch; margin:22px 0 4px; }}
    .date-pillar-grid {{ min-width:0; display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); border:1px solid var(--line); }}
    .date-pillar-grid .pillar {{ min-width:0; display:flex; flex-direction:column; justify-content:center; padding:16px 10px; }}
    .date-pillar-grid .glyph {{ overflow-wrap:anywhere; }}
    .variable-pillar {{ background:rgba(155,64,56,.045); }}
    .variable-pillar .glyph {{ color:var(--accent); font-size:clamp(22px,4.5vw,38px); letter-spacing:.02em; }}
    .variable-pillar .meta {{ color:var(--accent); }}
    .hour-status {{ min-width:0; display:flex; flex-direction:column; justify-content:center; align-items:center; border:1px solid var(--accent); padding:16px 12px; text-align:center; background:rgba(155,64,56,.045); }}
    .hour-status strong {{ margin:10px 0 5px; color:var(--accent); font-size:24px; font-weight:500; letter-spacing:.08em; }}
    .hour-status p {{ margin:0; color:var(--muted); font:10px/1.6 ui-monospace,monospace; }}
    .eyebrow {{ color:var(--muted); font-size:11px; letter-spacing:.16em; }}
    .ten-god {{ margin-top:10px; color:var(--accent); font-size:11px; }}
    .glyph {{ font-size:clamp(28px,6vw,48px); line-height:1.25; margin:12px 0 7px; letter-spacing:.08em; }}
    .meta {{ margin-top:8px; font-size:12px; }}
    .mini-label {{ margin-top:10px; color:var(--muted); font-size:9px; letter-spacing:.12em; }}
    .hidden {{ min-height:53px; margin-top:4px; display:flex; flex-wrap:wrap; justify-content:center; align-items:flex-start; align-content:flex-start; gap:5px; }}
    .hidden span {{ flex:0 0 auto; height:24px; display:inline-flex; align-items:center; gap:3px; border:1px solid var(--line); padding:2px 5px; font-size:10px; line-height:1; }}
    .hidden small {{ color:var(--muted); font-size:9px; line-height:1; }}
    .growth {{ margin-top:8px; display:flex; justify-content:center; gap:5px; font-size:10px; }}
    .growth small {{ color:var(--muted); font-size:9px; }}
    .growth span {{ color:var(--accent); }}
    .facts-row {{ margin:4px 0 22px; padding-top:18px; border-top:1px solid var(--line); }}
    .facts-row h3,.luck h3 {{ margin:0 0 10px; font-size:12px; letter-spacing:.12em; }}
    .facts-row h3 small {{ color:var(--muted); font-size:9px; letter-spacing:0; font-weight:400; }}
    .count-block {{ display:grid; grid-template-columns:32px 1fr; gap:6px; align-items:center; margin-top:6px; }}
    .count-block>span {{ color:var(--muted); font-size:10px; }}
    .element-counts {{ display:grid; grid-template-columns:repeat(5,1fr); gap:6px; }}
    .element-counts div {{ border:1px solid var(--line); padding:8px 4px; text-align:center; }}
    .element-counts strong,.element-counts span {{ display:block; }}
    .element-counts span {{ color:var(--muted); font:10px ui-monospace,monospace; }}
    .boundary {{ display:grid; grid-template-columns:1fr 1fr; border-top:1px solid var(--line); border-bottom:1px solid var(--line); }}
    .boundary>div {{ display:grid; gap:4px; padding:14px 4px; }}
    .boundary>div+div {{ padding-left:18px; border-left:1px solid var(--line); }}
    .boundary span,.boundary small {{ color:var(--muted); font-size:11px; }}
    .luck {{ margin-top:20px; border-top:1px solid var(--line); padding-top:16px; }}
    .luck h3 small {{ color:var(--muted); font:10px ui-monospace,monospace; letter-spacing:0; }}
    .luck-grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:7px; }}
    .luck-grid div {{ display:grid; gap:3px; border:1px solid var(--line); padding:9px; text-align:center; }}
    .luck-grid span,.luck-grid small {{ color:var(--muted); font-size:10px; }}
    .planet-grid {{ display:grid; grid-template-columns:repeat(5,1fr); gap:8px; margin:22px 0; }}
    .planet {{ border:1px solid var(--line); padding:14px 10px; text-align:center; }}
    .planet-name {{ color:var(--muted); font-size:11px; }}
    .planet-sign {{ font-size:18px; margin:8px 0 2px; }}
    .planet-degree {{ color:var(--accent); font:12px ui-monospace,monospace; }}
    .reading-guide {{ margin:22px 0; padding:18px 0; border-top:1px solid var(--line); border-bottom:1px solid var(--line); }}
    .reading-guide>header {{ display:grid; grid-template-columns:minmax(150px,.7fr) minmax(260px,1.3fr); gap:18px; align-items:end; margin-bottom:18px; }}
    .reading-guide>header>div>span {{ color:var(--accent); font:10px ui-monospace,monospace; letter-spacing:.12em; }}
    .reading-guide h3 {{ margin:4px 0 0; font-size:18px; letter-spacing:.06em; }}
    .reading-guide>header>p {{ margin:0; color:var(--muted); font-size:11px; line-height:1.7; }}
    .guide-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(210px,1fr)); gap:16px 22px; }}
    .guide-item {{ min-width:0; border-left:2px solid rgba(155,64,56,.5); padding-left:12px; }}
    .guide-item span {{ display:block; color:var(--muted); font:9px ui-monospace,monospace; letter-spacing:.12em; }}
    .guide-item strong {{ display:block; margin-top:5px; font-size:13px; line-height:1.45; }}
    .guide-item p {{ margin:6px 0 0; color:#57554f; font-size:12px; line-height:1.75; }}
    .aspects {{ border-top:1px solid var(--line); padding-top:16px; }}
    .aspects h3 {{ margin:0 0 10px; font-size:13px; letter-spacing:.12em; }}
    .aspects ul {{ list-style:none; margin:0; padding:0; display:grid; grid-template-columns:1fr 1fr; gap:8px 20px; }}
    .aspects li {{ display:flex; gap:6px; align-items:baseline; font-size:12px; border-bottom:1px dotted var(--line); padding:7px 0; }}
    .aspects li span {{ margin-left:auto; color:var(--muted); font:10px ui-monospace,monospace; }}
    footer {{ margin-top:24px; padding-top:16px; border-top:1px solid var(--ink); color:var(--muted); font-size:12px; line-height:1.7; }}
    @media (max-width:680px) {{ .masthead {{ align-items:start; flex-direction:column; }} .planet-grid {{ grid-template-columns:repeat(2,1fr); }} .aspects ul {{ grid-template-columns:1fr; }} .pillar-grid {{ gap:0; }} .pillar {{ padding:6px 3px; }} .glyph {{ font-size:26px; }} .luck-grid {{ grid-template-columns:repeat(2,1fr); }} .reading-guide>header {{ grid-template-columns:1fr; gap:8px; }} .guide-grid {{ grid-template-columns:1fr; }} .date-only-layout {{ grid-template-columns:1fr; }} .hour-status {{ min-height:108px; }} }}
    @media (max-width:420px) {{ .date-pillar-grid .pillar {{ padding:14px 5px; }} .date-pillar-grid .glyph {{ font-size:24px; }} .variable-pillar .glyph {{ font-size:20px; }} .date-pillar-grid .meta {{ font-size:10px; }} }}
    {zodiac_css}
  </style>
</head>
<body class="{body_class}"><main>
  {masthead_html}
  {''.join(panels)}
  {zodiac_actions}
  {footer_html}
</main>{zodiac_poster_scripts}</body></html>"""


def atomic_write(path: Path, content: str) -> None:
    if path.exists():
        raise FileExistsError(f"输出文件已存在：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temp_name, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render standalone chart HTML.")
    parser.add_argument("--bazi", type=Path)
    parser.add_argument("--western", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bazi = load_payload(args.bazi, "bazi")
    western = load_payload(args.western, "western")
    atomic_write(args.output, render_document(bazi, western))
    print(json.dumps({"ok": True, "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
