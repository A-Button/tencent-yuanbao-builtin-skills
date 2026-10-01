#!/usr/bin/env python3
"""Component stocks visualization for a Shenwan index.

Fetches component stocks/funds and computes concentration stats for a pie chart.

Usage:
  python sw_comp.py --code 801780                  # Auto-detect type
  python sw_comp.py --code 807100 --type fund      # Fund index
  python sw_comp.py --code 801271 --type style     # Style broad
  python sw_comp.py --code 802612 --type jc        # JinChuang
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
sys.path.insert(0, SCRIPT_DIR)

from sw_common import (  # noqa: E402
    attach_render,

    emit_artifact, emit_progress, emit_error, emit_phase,
    fetch_component_stocks_auto, call_analysis_llm,
    is_fund, is_style_broad, is_jc,
    INDUSTRY_NAME_BY_CODE, get_index_display_name,
)

TEMPLATE = "SW_COMP"
_EXTERNAL_INDEX_CLIENT = None


def _load_external_index_client():
    global _EXTERNAL_INDEX_CLIENT
    if _EXTERNAL_INDEX_CLIENT is not None:
        return _EXTERNAL_INDEX_CLIENT

    candidates = [
        os.path.join(SCRIPT_DIR, "external_indices.py"),
        "/agents/_shared/market_indices/client.py",  # 平台 fallback
    ]
    for path in candidates:
        if os.path.exists(path):
            spec = importlib.util.spec_from_file_location("shared_market_indices", path)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                _EXTERNAL_INDEX_CLIENT = mod
                return mod
    raise RuntimeError("外部常用指数成分查询暂不可用")


def _is_external_index(code: str) -> bool:
    try:
        return bool(_load_external_index_client().is_supported_index(code))
    except Exception:
        return False


def _detect_type(code: str, override: str) -> str:
    if override and override != "auto":
        return override
    if _is_external_index(code):
        return "external_index"
    if is_fund(code):
        return "fund"
    if is_style_broad(code):
        return "style"
    if is_jc(code):
        return "jc"
    return "normal"


def _date_key(value: str) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _dedupe_items_by_code(items: list[dict]) -> list[dict]:
    deduped = {}
    passthrough = []
    for idx, item in enumerate(items):
        code = str(item.get("code") or "").strip()
        if not code:
            passthrough.append(item)
            continue
        current = deduped.get(code)
        if current is None:
            deduped[code] = item
            continue
        if (_date_key(item.get("beginDate")), item.get("weight", 0), idx) > (
            _date_key(current.get("beginDate")), current.get("weight", 0), -1
        ):
            deduped[code] = item
    return list(deduped.values()) + passthrough


def _extract_items(raw: list, idx_type: str) -> list[dict]:
    """Normalize raw API records into a uniform item list sorted by weight desc."""
    items = []
    for r in raw:
        code = r.get("stockCode") or r.get("securityCode") or r.get("fundCode") or ""
        name = r.get("stockName") or r.get("securityName") or r.get("fundName") or ""
        weight_raw = r.get("newWeight")
        try:
            weight = round(float(weight_raw), 4) if weight_raw else 0.0
        except (ValueError, TypeError):
            weight = 0.0
        begin = r.get("beginningDate") or r.get("beginningdate") or r.get("beginDate") or ""
        items.append({"code": code, "name": name, "weight": weight, "beginDate": begin})

    items = _dedupe_items_by_code(items)
    items.sort(key=lambda x: x["weight"], reverse=True)
    for i, item in enumerate(items, 1):
        item["rank"] = i
    return items


def _compute_stats(items: list[dict]) -> dict:
    total = len(items)
    weights = [it["weight"] for it in items]
    total_w = sum(weights) or 1.0
    top5 = sum(weights[:5]) if total >= 5 else sum(weights)
    top10 = sum(weights[:10]) if total >= 10 else sum(weights)
    return {
        "total": total,
        "top5Pct": round(top5 / total_w * 100, 2) if total_w > 0 else 0,
        "top10Pct": round(top10 / total_w * 100, 2) if total_w > 0 else 0,
        "maxWeight": round(weights[0], 2) if weights else 0,
        "minWeight": round(weights[-1], 2) if weights else 0,
        "maxName": items[0]["name"] if items else "",
        "minName": items[-1]["name"] if items else "",
    }


def _build_pie(items: list[dict], top_n: int = 10) -> list[dict]:
    """Build pie chart data normalized to percentage of total weight."""
    total_w = sum(it["weight"] for it in items) or 1.0
    pie = []
    for it in items[:top_n]:
        pct = round(it["weight"] / total_w * 100, 2)
        pie.append({"name": it["name"], "value": pct})
    if len(items) > top_n:
        others_w = sum(it["weight"] for it in items[top_n:])
        pie.append({"name": "其他", "value": round(others_w / total_w * 100, 2)})
    return pie


def main():
    parser = argparse.ArgumentParser(description="Shenwan index component stocks visualization")
    parser.add_argument("--code", required=True, help="Index code")
    parser.add_argument("--type", default="auto", choices=["auto", "normal", "fund", "style", "jc", "external_index"])
    parser.add_argument("--name", default="", help="Index name (optional)")
    args = parser.parse_args()

    code = args.code
    idx_type = _detect_type(code, args.type)
    if idx_type == "external_index" and not args.name:
        idx_name = _load_external_index_client().index_name(code)
    else:
        idx_name = get_index_display_name(code, args.name or INDUSTRY_NAME_BY_CODE.get(code, code))

    identifier = f"comp-{code}-{idx_type}"
    title = f"{idx_name}({code}) 成分{'基金' if idx_type == 'fund' else '股'}"

    emit_artifact(TEMPLATE, identifier, title, {"loading": True})
    emit_progress(TEMPLATE, identifier, title, 1, 4, "正在获取成分数据")

    if idx_type == "external_index":
        external_raw = _load_external_index_client().index_components(code)
        raw = external_raw.get("components") or []
    else:
        external_raw = {}
        raw = fetch_component_stocks_auto(code)
    if not raw:
        emit_error(TEMPLATE, identifier, title, f"未获取到 {idx_name}({code}) 的成分数据")
        sys.exit(1)

    if any(r.get("newWeight") is None for r in raw):
        from sw_render import md_table_from_payload
        from sw_common import get_render_dir, add_render_file
        payload = {"title": title + "（成分名单）", "columns": [{"key":"code","title":"代码"},{"key":"name","title":"名称"}],
                   "rows": [{"code":r.get("stockCode"),"name":r.get("stockName")} for r in raw]}
        out = os.path.join(get_render_dir(), f"components-{code}.md")
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            f.write(md_table_from_payload(payload))
        add_render_file(identifier, "md", out)
        print(json.dumps(attach_render({"status":"degraded", "indexCode":code,"indexName":idx_name,
            "total":len(raw),"weights_available":False,"summary_text":f"{idx_name} 共{len(raw)}只成分；本次展示成分名单，未计算权重集中度或行业权重。"}),ensure_ascii=False))
        return
    items = _extract_items(raw, idx_type)
    count = len(items)

    is_equal_weight = (
        count >= 50
        and items[0]["weight"] > 0
        and items[-1]["weight"] > 0
        and items[0]["weight"] / items[-1]["weight"] < 2.0
    )

    meta = {
        "indexCode": code,
        "indexName": idx_name,
        "indexType": idx_type,
        "count": count,
        "isEqualWeight": is_equal_weight,
        "source": external_raw.get("source") if idx_type == "external_index" else "westock",
        "asOf": external_raw.get("as_of") if idx_type == "external_index" else None,
    }

    emit_progress(TEMPLATE, identifier, title, 2, 4, "正在计算统计指标")
    time.sleep(0.15)
    emit_phase(TEMPLATE, identifier, title, "meta",
               {"indexCode": code, "indexName": idx_name, "indexType": idx_type,
                "count": count, "isEqualWeight": is_equal_weight})

    stats = _compute_stats(items)
    pie_data = _build_pie(items)

    MAX_ITEMS_IN_PAYLOAD = 200
    items_for_template = items[:MAX_ITEMS_IN_PAYLOAD] if count > MAX_ITEMS_IN_PAYLOAD else items

    data_payload = {
        "items": items_for_template,
        "stats": stats,
        "pieData": pie_data,
        "totalItemCount": count,
    }
    emit_progress(TEMPLATE, identifier, title, 3, 4, "正在生成分析")
    time.sleep(0.15)
    emit_phase(TEMPLATE, identifier, title, "data", data_payload, meta=meta)

    top5_desc = ", ".join(f"{it['name']}({it['weight']}%)" for it in items[:5])
    summary_text = (
        f"指数: {idx_name}({code}), 类型: {idx_type}, 共{count}只成分。\n"
        f"Top5权重: {stats['top5Pct']}%, Top10权重: {stats['top10Pct']}%。\n"
        f"最大权重: {stats['maxName']} {stats['maxWeight']}%, "
        f"最小权重: {stats['minName']} {stats['minWeight']}%。\n"
        f"Top5成分: {top5_desc}。"
    )
    analysis = call_analysis_llm(summary_text, "成分股权重分布")

    time.sleep(0.15)
    emit_phase(TEMPLATE, identifier, title, "final", {}, meta=meta, analysis=analysis)

    print(json.dumps(attach_render({
        "status": "ok",
        "indexCode": code,
        "indexName": idx_name,
        "indexType": idx_type,
        "total": count,
        "top5_pct": stats["top5Pct"],
        "top10_pct": stats["top10Pct"],
        "max_weight_stock": f"{stats['maxName']}({stats['maxWeight']}%)",
        "summary_text": summary_text,
    }), ensure_ascii=False))


if __name__ == "__main__":
    main()
