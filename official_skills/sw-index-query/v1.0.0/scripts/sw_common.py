#!/usr/bin/env python3
"""Shared utilities for all SW index analysis scripts."""

from __future__ import annotations

import json
import sys
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from client import sw_get, sw_post, APIOfflineError, USE_WESTOCK
from datasource import (get_kline, get_klines, get_quote, get_quotes, get_valuation, get_component, get_risk_return, SOURCE_NOTE, UnsupportedCapabilityError, IncompleteDataError)  # noqa: E402


# ── Index code registries ────────────────────────────────────────────────────

INDUSTRY_L1 = {
    "801010": "农林牧渔", "801030": "基础化工", "801040": "钢铁",
    "801050": "有色金属", "801080": "电子", "801110": "家用电器",
    "801120": "食品饮料", "801130": "纺织服饰", "801140": "轻工制造",
    "801150": "医药生物", "801160": "公用事业", "801170": "交通运输",
    "801180": "房地产", "801200": "商贸零售", "801210": "社会服务",
    "801230": "综合", "801710": "建筑材料", "801720": "建筑装饰",
    "801730": "电力设备", "801740": "国防军工", "801750": "计算机",
    "801760": "传媒", "801770": "通信", "801780": "银行",
    "801790": "非银金融", "801880": "汽车", "801890": "机械设备",
    "801950": "煤炭", "801960": "石油石化", "801970": "环保",
    "801980": "美容护理",
}

MARKET_INDICES = {
    "801001": "申万50", "801003": "申万A指",
    "801300": "申万300", "801005": "申万创业",
}

# Name recognition keeps 801001 distinct. Market-reference routes use the real
# replacement code/name below before fetching; never relabel replacement data.
SW50_REFERENCE_SUBSTITUTES = {"930050": "中证A50", "000016": "上证50"}

STYLE_INDICES = {
    "801811": "大盘指数", "801812": "中盘指数", "801813": "小盘指数",
    "801821": "高市盈率指数", "801822": "中市盈率指数", "801823": "低市盈率指数",
    "801831": "高市净率指数", "801832": "中市净率指数", "801833": "低市净率指数",
    "801841": "高价股指数", "801842": "中价股指数", "801843": "低价股指数",
    "801851": "亏损股指数", "801852": "微利股指数", "801853": "绩优股指数",
    "801861": "配股指数", "801862": "活跃指数", "801863": "新股指数",
}

COLOR_POOL = ["#e6574c", "#4a90d9", "#67c23a", "#e6a23c", "#9b59b6", "#1abc9c"]

INDUSTRY_GROUPS = {
    "consumer":  {"食品饮料": "801120", "家用电器": "801110", "医药生物": "801150",
                  "社会服务": "801210", "商贸零售": "801200", "美容护理": "801980",
                  "农林牧渔": "801010", "轻工制造": "801140", "纺织服饰": "801130"},
    "tmt":       {"电子": "801080", "计算机": "801750", "通信": "801770", "传媒": "801760"},
    "cyclical":  {"基础化工": "801030", "有色金属": "801050", "钢铁": "801040",
                  "煤炭": "801950", "石油石化": "801960", "建筑材料": "801710",
                  "建筑装饰": "801720"},
    "finance":   {"银行": "801780", "非银金融": "801790", "房地产": "801180"},
    "mfg":       {"机械设备": "801890", "电力设备": "801730", "汽车": "801880",
                  "国防军工": "801740"},
    "defensive": {"公用事业": "801160", "交通运输": "801170", "环保": "801970"},
}

FUND_INDEX_GROUPS = {
    "fund_l1": {
        "807100": "权益基金", "807200": "债券基金", "807300": "混合基金",
        "807400": "货币基金", "807500": "另类基金", "807600": "组合基金",
        "807700": "QDII基金",
    },
    "fund_equity": {
        "807110": "主动权益", "807120": "标准指数", "807130": "增强指数",
        "807140": "行业主题",
    },
    "fund_bond": {
        "807210": "纯债指数", "807220": "短期纯债", "807230": "中长期纯债",
        "807240": "债券增强",
    },
    "fund_theme": {
        "807141": "消费基金", "807142": "医药医疗基金", "807143": "周期基金",
        "807144": "金融地产基金", "807145": "先进制造基金", "807146": "科技TMT基金",
        "807147": "北交所基金", "807148": "港股通基金",
    },
    "fund_enhance": {
        "807131": "沪深300增强", "807132": "中证500增强", "807133": "中证1000增强",
        "808001": "300增强超额", "808002": "500增强超额", "808003": "1000增强超额",
    },
}

CATEGORY_PRESETS = {
    "l1":           {"source": "industry",  "label": "一级行业"},
    "fund":         {"source": "fund_l1",   "label": "基金大类"},
    "fund_equity":  {"source": "fund_equity", "label": "权益基金"},
    "fund_bond":    {"source": "fund_bond",   "label": "债券基金"},
    "fund_theme":   {"source": "fund_theme",  "label": "行业主题基金"},
    "fund_enhance": {"source": "fund_enhance", "label": "增强/超额基金"},
    "style":        {"source": "style",        "label": "风格指数"},
    "consumer":     {"source": "consumer",     "label": "消费板块"},
    "tmt":          {"source": "tmt",          "label": "TMT板块"},
    "cyclical":     {"source": "cyclical",     "label": "周期板块"},
    "finance":      {"source": "finance",      "label": "金融板块"},
    "mfg":          {"source": "mfg",          "label": "制造板块"},
    "defensive":    {"source": "defensive",    "label": "防御板块"},
}

_EXTRA_INDEX_NAMES = {
    "801271": "大类风格-周期", "801272": "大类风格-先进制造",
    "801273": "大类风格-消费", "801274": "大类风格-医药医疗",
    "801275": "大类风格-科技(TMT)", "801276": "大类风格-金融地产",
    **MARKET_INDICES, **STYLE_INDICES,
}

for _g in FUND_INDEX_GROUPS.values():
    _EXTRA_INDEX_NAMES.update(_g)

INDUSTRY_NAME_BY_CODE = {**INDUSTRY_L1, **_EXTRA_INDEX_NAMES}

SCOPE_LABELS = {
    "consumer": "消费板块", "tmt": "TMT板块", "cyclical": "周期板块",
    "finance": "金融板块", "mfg": "制造板块", "defensive": "防御板块",
}

FUND_CODES = set(range(807000, 809000))
STYLE_BROAD_CODES = set(range(801271, 801277))
JC_CODES = set(range(802608, 802613))


def is_fund(code: str) -> bool:
    return int(code) in FUND_CODES


def is_style_broad(code: str) -> bool:
    return int(code) in STYLE_BROAD_CODES


def is_jc(code: str) -> bool:
    return int(code) in JC_CODES


def get_index_display_name(code: str, fallback: str | None = None) -> str:
    """Return a safe display name for one index code."""
    code_s = str(code)
    if fallback:
        return fallback
    return INDUSTRY_NAME_BY_CODE.get(code_s, code_s)


def resolve_market_reference(code: str, substitute: str = "930050") -> tuple:
    """申万50市场参照默认用中证A50；沪市范围可指定上证50。

    返回实际查询代码和名称。仅用于市场参照替代路由，不修改原指数身份，
    不把替代指数的成分、权重或历史当作申万50。外部指数使用 external_indices
    或可用 westock skill/websearch，不送入申万行业的 pt01 代码转换。
    """
    if str(code) != "801001":
        return str(code), get_index_display_name(str(code))
    if substitute not in SW50_REFERENCE_SUBSTITUTES:
        raise ValueError('申万50市场参照仅选择中证A50（930050）或上证50（000016）')
    return substitute, SW50_REFERENCE_SUBSTITUTES[substitute]


TRADING_DAYS_PER_YEAR = 250
MIN_KLINE_DAYS = 60

# Technical signal thresholds (shared across stock_deep, sw_deep, stock_tech, sw_tech)
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
KDJ_OVERBOUGHT = 80
KDJ_OVERSOLD = 20
CCI_STRONG = 100
CCI_WEAK = -100
ATR_EXPAND_RATIO = 1.2
ATR_SHRINK_RATIO = 0.8


# ── Scope resolution ─────────────────────────────────────────────────────────

def resolve_scope(scope: str = "all", codes: str | None = None) -> dict:
    """Return {name: code} dict based on --scope or --codes.
    --codes takes precedence over --scope."""
    if codes:
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
        return {INDUSTRY_NAME_BY_CODE.get(c, c): c for c in code_list}
    if scope and scope != "all" and scope in INDUSTRY_GROUPS:
        return INDUSTRY_GROUPS[scope]
    return {v: k for k, v in INDUSTRY_L1.items()}


def resolve_category(category: str = "l1", codes: str | None = None) -> tuple[str, dict[str, str]]:
    """Resolve a ranking category to (label, {code: name}).

    Args:
        category: preset key from CATEGORY_PRESETS, or 'custom'.
        codes: comma-separated index codes (overrides category).

    Returns:
        (human_label, {code: name}) where code is the index code string.
    """
    if codes:
        code_list = [c.strip() for c in codes.split(",") if c.strip()]
        resolved = {c: INDUSTRY_NAME_BY_CODE.get(c, c) for c in code_list}
        return "自定义指数", resolved

    preset = CATEGORY_PRESETS.get(category)
    if not preset:
        return resolve_category("l1", None)

    source = preset["source"]
    label = preset["label"]

    if source == "industry":
        return label, dict(INDUSTRY_L1)
    if source == "style":
        return label, dict(STYLE_INDICES)
    if source in INDUSTRY_GROUPS:
        grp = INDUSTRY_GROUPS[source]
        return label, {v: k for k, v in grp.items()}
    if source in FUND_INDEX_GROUPS:
        grp = FUND_INDEX_GROUPS[source]
        return label, dict(grp)

    return resolve_category("l1", None)


# ── Artifact helpers ─────────────────────────────────────────────────────────

_SPLIT_THRESHOLD = 25_000


def _load_artifact_client():
    """Load the platform artifact client, or return None (no-op) when absent.

    可移植策略：优先探测平台 artifact_client（原 /agents/_shared/artifact_client.py），
    找不到时返回 None，使 emit_* 降级为 no-op —— 纯 CLI 环境也能运行，
    且不污染 stdout 的"最后一行 JSON 摘要"约定。
    """
    import importlib.util

    candidates = []
    env = os.environ.get("SW_ARTIFACT_CLIENT")
    if env and os.path.isfile(env):
        candidates.append(env)
    local = os.path.join(SCRIPT_DIR, "artifact_client.py")
    if os.path.isfile(local):
        candidates.append(local)
    candidates.append("/agents/_shared/artifact_client.py")  # 原平台路径

    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            spec = importlib.util.spec_from_file_location("artifact_client", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod
        except Exception:
            continue
    return None


_artifact_client = _load_artifact_client()


def has_platform_artifact() -> bool:
    """是否具备平台 artifact client（决定走平台模板推送还是本地 HTML/Markdown 渲染）。"""
    return _artifact_client is not None


# ── 本地渲染桥（无平台时把 emit 数据渲染为交互式 HTML + Markdown 表格）──────

_RENDER_CACHE: dict = {}          # identifier -> {"template","title","data","meta"}
_EXTRA_RENDER_FILES: dict = {}    # identifier -> {"md": path|None}


def get_workspace_dir() -> str:
    """工作目录：SW_WORKSPACE 环境变量优先，否则当前目录下 workspace/。"""
    ws = os.environ.get("SW_WORKSPACE")
    if ws:
        return os.path.abspath(ws)
    return os.path.abspath(os.path.join(os.getcwd(), "workspace"))


def get_render_dir() -> str:
    """本地渲染产物目录：<工作目录>/.swi/render/"""
    return os.path.join(get_workspace_dir(), ".swi", "render")


def _cache_emit_payload(template: str, identifier: str, title: str,
                        data: dict, meta: dict | None):
    """无平台时缓存 data/final 阶段 payload，供脚本结束前渲染为 HTML/Markdown。

    只在 data/final 阶段且 data 非空时缓存；meta 阶段（查询参数）不缓存。
    """
    if _artifact_client is not None or not isinstance(data, dict) or not data:
        return
    _RENDER_CACHE[identifier] = {
        "template": template, "title": title,
        "data": dict(data), "meta": dict(meta) if meta else None,
    }


def add_render_file(identifier: str, kind: str, path: str):
    """供 pi-table 等不经过 emit 层的脚本登记本地渲染产物。"""
    _EXTRA_RENDER_FILES.setdefault(identifier, {"md": None})[kind] = path


def attach_render(summary: dict) -> dict:
    """把本次运行所有本地渲染产物路径挂到 summary["render_files"]。

    无平台时（纯 CLI / WorkBuddy 本地环境）由各脚本在 print summary 前调用；
    有平台时不做任何事（仍走平台模板推送），保证功能不变。
    """
    summary["data_source"] = "westock" if USE_WESTOCK else "swsresearch"
    summary["data_note"] = SOURCE_NOTE if USE_WESTOCK else "申万官方接口"
    if _artifact_client is not None:
        return summary
    files: dict = {}
    try:
        from sw_render import render_payload, set_render_dir
        out_dir = get_render_dir()
        set_render_dir(out_dir)
        for ident, item in _RENDER_CACHE.items():
            try:
                r = render_payload(item["template"], ident, item["title"],
                                   item["data"], item.get("meta"), out_dir=out_dir)
                if r.get("md") or r.get("html"):
                    files[ident] = r
            except Exception as e:
                print(f"[attach_render] {ident} 渲染失败: {e}", file=sys.stderr)
    except ImportError:
        pass
    for ident, r in _EXTRA_RENDER_FILES.items():
        if r.get("md"):
            files[ident] = r
    _RENDER_CACHE.clear()
    _EXTRA_RENDER_FILES.clear()
    if files:
        for artifact in files.values():
            md_path = artifact.get('md')
            if md_path and os.path.isfile(md_path):
                with open(md_path,encoding='utf-8') as f:
                    content = f.read()
                if summary['data_note'] not in content:
                    with open(md_path,'a',encoding='utf-8') as f:
                        f.write('\n\n> '+summary['data_note']+'\n')
        summary["render_files"] = files
    return summary


def _raw_emit(template: str, identifier: str, title: str, data: dict):
    if _artifact_client is None:
        if os.environ.get("SW_PORTABLE_DEBUG"):
            print(f"[sw_common] emit_artifact({template}) 降级为 no-op（无平台 artifact client）",
                  file=sys.stderr)
        return
    _artifact_client.emit_artifact_event(
        template=template,
        identifier=identifier,
        title=title,
        payload=data,
    )


def emit_artifact(template: str, identifier: str, title: str, data: dict):
    """Emit an artifact event with 25KB auto-split safety net.

    Uses sequential bin-packing: iterates data's top-level keys and groups
    them into chunks targeting < 25KB each.  Every chunk carries the
    non-splittable envelope fields (meta, analysis, __phase) per the
    Payload Schema (see progressive-rendering-architecture.md Section 3.1.1).
    """
    inner = data.get("data") if isinstance(data, dict) else None
    if inner is None or not isinstance(inner, dict):
        _raw_emit(template, identifier, title, data)
        return

    payload_bytes = len(json.dumps(data, ensure_ascii=False).encode("utf-8"))
    if payload_bytes <= _SPLIT_THRESHOLD:
        _raw_emit(template, identifier, title, data)
        return

    phase = inner.get("__phase")
    envelope: dict = {}
    if "meta" in data:
        envelope["meta"] = data["meta"]
    if "analysis" in data:
        envelope["analysis"] = data["analysis"]

    envelope_size = len(json.dumps(envelope, ensure_ascii=False).encode("utf-8")) if envelope else 0
    phase_overhead = len(json.dumps(phase, ensure_ascii=False).encode("utf-8")) + 20 if phase else 0
    overhead = envelope_size + phase_overhead
    budget = max(_SPLIT_THRESHOLD - overhead, _SPLIT_THRESHOLD // 2)

    # Pre-process: expand large array fields into key_0, key_1, ...
    # so each sub-array fits within the split budget.
    expanded: dict = {}
    for k, v in inner.items():
        if k == "__phase":
            continue
        field_size = len(json.dumps(v, ensure_ascii=False).encode("utf-8"))
        if field_size > budget and isinstance(v, list) and len(v) > 1:
            per_item = field_size / len(v)
            page_size = max(1, int(budget * 0.9 / per_item))
            for i in range(0, len(v), page_size):
                expanded[f"{k}_{i // page_size}"] = v[i:i + page_size]
        else:
            expanded[k] = v

    chunk: dict = {}
    chunk_size = 0
    for k, v in expanded.items():
        field_size = len(json.dumps(v, ensure_ascii=False).encode("utf-8"))
        if chunk and chunk_size + field_size > budget:
            out: dict = {"data": {**chunk}}
            if phase:
                out["data"]["__phase"] = phase
            out.update(envelope)
            _raw_emit(template, identifier, title, out)
            chunk = {}
            chunk_size = 0
        chunk[k] = v
        chunk_size += field_size
        if field_size > budget:
            print(f"[emit_artifact] WARN: field '{k}' is {field_size}B (>{budget})", file=sys.stderr)

    if chunk:
        out = {"data": {**chunk}}
        if phase:
            out["data"]["__phase"] = phase
        out.update(envelope)
        _raw_emit(template, identifier, title, out)


def emit_progress(template: str, identifier: str, title: str,
                  current: int, total: int, message: str):
    emit_artifact(template, identifier, title, {
        "loading": True,
        "progress": current,
        "total": total,
        "message": f"{message} {current}/{total}...",
    })


def emit_error(template: str, identifier: str, title: str, error: str):
    emit_artifact(template, identifier, title, {
        "loading": False,
        "error": error,
    })


def emit_phase(template: str, identifier: str, title: str,
               phase: str, data: dict, *,
               meta: dict | None = None, analysis: str | None = None):
    """Emit a partial/cumulative data update tagged with a phase name."""
    meta = dict(meta or {})
    meta["data_note"] = SOURCE_NOTE if USE_WESTOCK else "申万官方接口"
    _cache_emit_payload(template, identifier, title, data, meta)
    payload: dict = {"data": {**data, "__phase": phase}}
    if meta is not None:
        payload["meta"] = meta
    if analysis is not None:
        payload["analysis"] = analysis
    emit_artifact(template, identifier, title, payload)


# ── Batch API helpers ────────────────────────────────────────────────────────

def fetch_realtime_one(code: str) -> dict | None:
    """Fetch realtime data for one index, return summary dict or None on error."""
    if USE_WESTOCK:
        return get_quote(code)
    try:
        raw = sw_get(
            "/institute-sw/api/index_publish/details/timelines/",
            params={"swindexcode": code},
            timeout=15,
        )
        data = raw.get("data")
        if not data:
            print(f"[sw_common] fetch_realtime_one({code}): API returned empty data", file=sys.stderr)
            return None
        last = data[-1]
        prev_close = float(last["l3"])
        latest = float(last["l8"])
        chg = latest - prev_close
        return {
            "code": code,
            "name": last.get("l2", code),
            "latest": latest,
            "prev_close": prev_close,
            "change": round(chg, 2),
            "change_pct": round(chg / prev_close * 100, 2) if prev_close else 0,
            "open": float(last["l4"]),
            "high": float(last["l6"]),
            "low": float(last["l7"]),
            "amount": round(float(last["l5"]) / 100, 2),
            "volume": round(float(last["l11"]) / 100, 2),
            "time": last.get("trading_time", ""),
            "date": last.get("trading_date", ""),
        }
    except Exception as e:
        print(f"[sw_common] fetch_realtime_one({code}): {type(e).__name__}: {e}", file=sys.stderr)
        return None


def fetch_realtime_batch(codes_dict: dict, template: str, identifier: str,
                         title: str, msg: str = "正在获取行情数据") -> list:
    """Fetch realtime for multiple codes with progress updates.

    DEPRECATED for bulk snapshot scenarios — prefer fetch_snapshot_batch()
    which uses a single /current/ batch API (1 call vs N calls) and is
    immune to the dawn-maintenance window where /timelines/ returns empty.
    Kept for scripts that need full intraday series.
    """
    results = []
    total = len(codes_dict)
    for i, (code, name) in enumerate(codes_dict.items()):
        if i % 3 == 0:
            emit_progress(template, identifier, title, i, total, msg)
        info = fetch_realtime_one(code)
        if info:
            info["name"] = name
            results.append(info)
    emit_progress(template, identifier, title, total, total, msg)
    return results


# ── current/ batch snapshot — 1 call replaces N × timelines/ ─────────────────

# Friendly name → API indextype parameter
_INDEXTYPE_ALIASES = {
    "market": "市场表征",
    "l1": "一级行业",
    "l2": "二级行业",
    "style": "风格指数",
    # Also accept the API-native names directly
    "市场表征": "市场表征",
    "一级行业": "一级行业",
    "二级行业": "二级行业",
    "风格指数": "风格指数",
}


def fetch_snapshot_batch(indextype: str, page_size: int = 150) -> list[dict]:
    """Fetch current-day snapshot for all indices of one category in ONE request.

    Uses /institute-sw/api/index_publish/current/ — the batch snapshot API.
    Returns latest close, prev close, open/high/low, amount/volume, change_pct.

    This replaces N × fetch_realtime_one() calls in dashboard/heatmap/style scripts:
      - Much faster (1 request vs 31+ sequential)
      - Available around the clock, including the dawn maintenance window
        (~00:00–06:00) where /timelines/ returns empty → was the root cause
        of the 2026-04-17 "未获取到任何行业数据" bug

    Args:
        indextype: "市场表征" / "一级行业" / "二级行业" / "风格指数"
                   (or aliases: "market" / "l1" / "l2" / "style")
        page_size: Upper bound per API call. Default 150 covers 二级行业 (124 rows).

    Returns:
        List of dicts shaped like fetch_realtime_one() output so downstream
        code needs no changes:
            code, name, latest, prev_close, change, change_pct,
            open, high, low, amount (亿元), volume (亿股), date, time.

        Empty list if the upstream API fails.
    """
    if USE_WESTOCK:
        return list(get_quotes(_source_codes(indextype)).values())
    api_indextype = _INDEXTYPE_ALIASES.get(indextype, indextype)
    try:
        resp = sw_get(
            "/institute-sw/api/index_publish/current/",
            params={
                "page": "1",
                "page_size": str(page_size),
                "indextype": api_indextype,
                "sortField": "",
                "rule": "",
            },
            timeout=15,
        )
    except Exception as e:
        print(f"[sw_common] fetch_snapshot_batch({indextype}): {type(e).__name__}: {e}",
              file=sys.stderr)
        return []

    raw = resp.get("data", {}).get("results") or []
    results = []
    for r in raw:
        try:
            prev = float(r.get("l3") or 0)
            latest = float(r.get("l8") or 0)
            chg = latest - prev
            results.append({
                "code": r.get("swindexcode", ""),
                "name": r.get("swindexname", ""),
                "latest": latest,
                "prev_close": prev,
                "change": round(chg, 2),
                "change_pct": round(chg / prev * 100, 2) if prev else 0,
                "open": float(r.get("l4") or 0),
                "high": float(r.get("l6") or 0),
                "low": float(r.get("l7") or 0),
                # current/ API returns 百万元 / 百万股, convert to 亿元 / 亿股
                "amount": round(float(r.get("l5") or 0) / 100, 2),
                "volume": round(float(r.get("l11") or 0) / 100, 2),
                "time": "",
                "date": "",
            })
        except (ValueError, TypeError) as e:
            print(f"[sw_common] fetch_snapshot_batch: skip malformed row {r}: {e}",
                  file=sys.stderr)
    return results


def fetch_fundamentals_batch(indextype: str, page_size: int = 150, codes=None) -> list[dict]:
    """Fetch fundamental metrics (PE / PB / 股息率 / 换手率 / 流通市值) in ONE request.

    Uses /institute-sw/api/index_analysis/day_week_month_report/?type=DAY —
    the batch aggregated index metrics endpoint. Agent did not previously
    use this API; returns the *valuation* data that used to be missing.

    Args:
        indextype: "市场表征" / "一级行业" / "二级行业" / "风格指数"
                   (or aliases: "market" / "l1" / "l2" / "style")

    Returns:
        List of dicts with:
            code, name, date (bargaindate), close, change_pct (markup),
            pe, pb, dp (股息率 %), turnover (换手率 %),
            mean_price (均价 元), amount_ratio (成交额占比 %),
            circ_mcap (流通市值 亿元), avg_circ_mcap (平均流通市值 亿元),
            volume (成交量 亿股).

        Empty list if upstream API fails.
    """
    if USE_WESTOCK:
        return _westock_fundamentals(indextype, codes)
    api_indextype = _INDEXTYPE_ALIASES.get(indextype, indextype)
    try:
        resp = sw_get(
            "/institute-sw/api/index_analysis/day_week_month_report/",
            params={
                "type": "DAY",
                "index_type": api_indextype,
                "page": "1",
                "page_size": str(page_size),
            },
            timeout=15,
        )
    except Exception as e:
        print(f"[sw_common] fetch_fundamentals_batch({indextype}): {type(e).__name__}: {e}",
              file=sys.stderr)
        return []

    raw = resp.get("data", {}).get("results") or []
    results = []
    for r in raw:
        results.append({
            "code": r.get("swindexcode", ""),
            "name": r.get("swindexname", ""),
            "date": (r.get("bargaindate") or "")[:10],
            "close": _float(r.get("closeindex")),
            "change_pct": _float(r.get("markup")),
            "volume": _float(r.get("bargainamount")),  # 亿股
            "pe": _float(r.get("pe")),
            "pb": _float(r.get("pb")),
            "dp": _float(r.get("dp")),                       # 股息率 %
            "turnover": _float(r.get("turnoverrate")),       # 换手率 %
            "mean_price": _float(r.get("meanprice")),
            "amount_ratio": _float(r.get("bargainsumrate")),  # 成交额占比 %
            "circ_mcap": _float(r.get("negotiablessharesum1")),     # 流通市值 亿元
            "avg_circ_mcap": _float(r.get("negotiablessharesum2")),
        })
    return results


# ── Weekly / Monthly period helpers (for sw_period_rank) ─────────────────────

def fetch_period_dates(period: str) -> list[str]:
    """Fetch the list of available week-end / month-end dates from the
    /index_analysis/week_month_datetime/ endpoint.

    Returns: ["2026-04-10", "2026-04-03", ...] sorted descending (most recent first).
    Empty list on API failure.
    """
    if USE_WESTOCK:
        return _westock_period_dates(period)
    assert period in ("WEEK", "MONTH"), f"period must be WEEK or MONTH, got {period}"
    try:
        resp = sw_get(
            "/institute-sw/api/index_analysis/week_month_datetime/",
            params={"type": period}, timeout=15,
        )
    except Exception as e:
        print(f"[sw_common] fetch_period_dates({period}): {type(e).__name__}: {e}",
              file=sys.stderr)
        return []

    raw = resp.get("data") or []
    dates = [(r.get("bargaindate") or "")[:10] for r in raw if r.get("bargaindate")]
    # Already sorted desc typically; ensure stable order
    dates.sort(reverse=True)
    return dates


def fetch_period_snapshot(period: str, bargaindate: str | None,
                          index_type: str = "一级行业",
                          page_size: int = 150, codes=None) -> list[dict]:
    """Fetch week-end or month-end cross-section data for all indices in a category.

    Uses /index_analysis/index_analysis_reports/?type=WEEK|MONTH — the same
    fields as day_week_month_report but aggregated to the week/month boundary.

    Args:
        period:      "WEEK" or "MONTH"
        bargaindate: Target week/month-end date (YYYY-MM-DD). If None, API returns latest.
        index_type:  "市场表征" / "一级行业" / "二级行业" / "风格指数"
        page_size:   Row cap

    Returns: Same shape as fetch_fundamentals_batch() output.
    """
    if USE_WESTOCK:
        return _westock_period_snapshot(period, bargaindate, index_type, codes)
    assert period in ("WEEK", "MONTH")
    api_indextype = _INDEXTYPE_ALIASES.get(index_type, index_type)
    params = {
        "type": period,
        "index_type": api_indextype,
        "page": "1",
        "page_size": str(page_size),
    }
    if bargaindate:
        params["bargaindate"] = bargaindate

    try:
        resp = sw_get(
            "/institute-sw/api/index_analysis/index_analysis_reports/",
            params=params, timeout=15,
        )
    except Exception as e:
        print(f"[sw_common] fetch_period_snapshot({period},{bargaindate}): "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        return []

    raw = resp.get("data", {}).get("results") or []
    results = []
    for r in raw:
        results.append({
            "code": r.get("swindexcode", ""),
            "name": r.get("swindexname", ""),
            "date": (r.get("bargaindate") or "")[:10],
            "close": _float(r.get("closeindex")),
            "change_pct": _float(r.get("markup")),
            "volume": _float(r.get("bargainamount")),
            "pe": _float(r.get("pe")),
            "pb": _float(r.get("pb")),
            "dp": _float(r.get("dp")),
            "turnover": _float(r.get("turnoverrate")),
            "mean_price": _float(r.get("meanprice")),
            "amount_ratio": _float(r.get("bargainsumrate")),
            "circ_mcap": _float(r.get("negotiablessharesum1")),
            "avg_circ_mcap": _float(r.get("negotiablessharesum2")),
        })
    return results


def fetch_recommendation_list() -> list[dict]:
    """Fetch the homepage recommendation list (8 indices with today's timeline).

    Uses /insWechatSw/swIndex/indexRecommendationList — the landing-page API.
    Returns flattened snapshot list for quick display (greeting card use case).

    Returns: [{code, name, type, latest, prev_close, change_pct, trading_date}]
    """
    if USE_WESTOCK:
        return list(get_quotes(list(INDUSTRY_L1)[:8]).values())
    try:
        resp = sw_post("/insWechatSw/swIndex/indexRecommendationList", body={}, timeout=15)
    except Exception as e:
        print(f"[sw_common] fetch_recommendation_list: {type(e).__name__}: {e}",
              file=sys.stderr)
        return []

    items = resp.get("data") or []
    results = []
    for it in items:
        data = it.get("data") or []
        if not data:
            continue
        last = data[-1]
        try:
            prev = float(last.get("l3") or 0)
            latest = float(last.get("l8") or 0)
            chg_pct = round((latest - prev) / prev * 100, 2) if prev else 0
            results.append({
                "code": it.get("code", ""),
                "name": it.get("name", ""),
                "type": it.get("type"),  # 1=普通指数 2=基金指数
                "latest": latest,
                "prev_close": prev,
                "change_pct": chg_pct,
                "trading_date": last.get("trading_date", ""),
            })
        except (ValueError, TypeError):
            continue
    return results


def fetch_kline_one(code: str, period: str = "DAY", days: int = 90):
    if USE_WESTOCK:
        return get_kline(code, period, days)
    return sw_get("/institute-sw/api/index_publish/trend/", params={"swindexcode":code,"period":period}).get("data", [])[-days:]


def fetch_risk_return_one(code: str) -> dict | None:
    """Fetch risk/return data for one index."""
    if USE_WESTOCK:
        return get_risk_return(code)
    try:
        resp = sw_post(
            "/insWechatSw/swIndex/getIndexRiskReturn",
            body={"swIndexCode": code},
        )
        data = resp.get("data")
        if not data:
            print(f"[sw_common] fetch_risk_return_one({code}): API returned empty data", file=sys.stderr)
            return None
        rec = data[0] if isinstance(data, list) else data
        return {
            "m1_return": _float(rec.get("m1_interval_return_rate")),
            "m3_return": _float(rec.get("m3_interval_return_rate")),
            "ytd_return": _float(rec.get("ytd_interval_return_rate")),
            "y1_return": _float(rec.get("y1_annual_return_rate")),
            "y3_return": _float(rec.get("y3_annual_return_rate")),
            "y5_return": _float(rec.get("y5_annual_return_rate")),
            "y1_vol": _float(rec.get("y1_annual_volatility")),
            "y3_vol": _float(rec.get("y3_annual_volatility")),
            "y5_vol": _float(rec.get("y5_annual_volatility")),
        }
    except Exception as e:
        print(f"[sw_common] fetch_risk_return_one({code}): {type(e).__name__}: {e}", file=sys.stderr)
        return None


def fetch_risk_return_batch(codes_dict: dict, template: str, identifier: str,
                            title: str, msg: str = "正在获取收益风险数据") -> list:
    results = []
    total = len(codes_dict)
    for i, (code, name) in enumerate(codes_dict.items()):
        if i % 3 == 0:
            emit_progress(template, identifier, title, i, total, msg)
        info = fetch_risk_return_one(code)
        if info:
            info["code"] = code
            info["name"] = name
            results.append(info)
    emit_progress(template, identifier, title, total, total, msg)
    return results


def fetch_kline_batch(codes_dict: dict, template: str, identifier: str,
                      title: str, period: str = "DAY", days: int = 30,
                      msg: str = "正在获取K线数据") -> dict:
    """Fetch K-line for multiple codes with progress. Returns {code: kline_list}."""
    results = {}
    total = len(codes_dict)
    for i, (name, code) in enumerate(codes_dict.items()):
        if i % 3 == 0:
            emit_progress(template, identifier, title, i, total, msg)
        data = fetch_kline_one(code, period, days)
        if data:
            results[code] = data
    emit_progress(template, identifier, title, total, total, msg)
    return results


def parallel_fetch(fetch_fn, codes_dict, max_workers=8,
                   on_batch=None, batch_size=6):
    """并行执行 fetch_fn(code) 并收集结果。

    Args:
        fetch_fn: 接受 code 参数，返回 dict|None 的函数
        codes_dict: {code: name} 映射
        max_workers: 并行线程数
        on_batch: 可选回调 on_batch(results_so_far, total)，
                  每收集 batch_size 个结果时调用
        batch_size: 每收集多少个结果触发一次 on_batch

    Returns: 全部结果列表
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    results = []
    total = len(codes_dict)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for code, name in codes_dict.items():
            fut = pool.submit(fetch_fn, code)
            futures[fut] = (code, name)

        for fut in as_completed(futures):
            code, name = futures[fut]
            try:
                info = fut.result()
            except Exception:
                if USE_WESTOCK:
                    raise
                info = None
            if info:
                info["code"] = code
                info["name"] = name
                results.append(info)
                if on_batch and len(results) % batch_size == 0:
                    on_batch(list(results), total)

    if on_batch and len(results) % batch_size != 0:
        on_batch(list(results), total)

    return results


def parallel_fetch_kline(codes_dict, period="DAY", days=61, max_workers=8):
    if USE_WESTOCK:
        return get_klines(codes_dict, period, days)
    return {c:fetch_kline_one(c, period, days) for c in codes_dict}


def _normalize_date(raw: str) -> str:
    """Convert 'YYYY-MM-DD ...' or 'YYYYMMDD' to 'YYYYMMDD'."""
    return raw.replace("-", "")[:8]


def find_trading_day(kline_data: list, target_date: str) -> tuple:
    """Find the nearest trading day <= target_date in kline data.
    Returns (index, actual_date_str in YYYYMMDD). Raises ValueError if out of range."""
    if not kline_data:
        raise ValueError("K线数据为空")
    target = _normalize_date(target_date)
    earliest = _normalize_date(kline_data[0].get("bargaindate", ""))
    if target < earliest:
        raise ValueError(
            f"K线数据仅覆盖 {earliest} 至今（约250个交易日），"
            f"{target} 超出可查范围"
        )
    for i in range(len(kline_data) - 1, -1, -1):
        d = _normalize_date(kline_data[i].get("bargaindate", ""))
        if d <= target:
            return i, d
    raise ValueError(f"未找到 {target} 附近的交易数据")


def fetch_component_stocks(code: str, page_size: int = 1000) -> list:
    """Fetch component stocks for an index."""
    if USE_WESTOCK:
        return get_component(code)
    try:
        effective_page_size = page_size
        resp = sw_post(
            "/insWechatSw/swIndex/componentStockPageList",
            body={"indexCode": code, "pageNo": 1, "pageSize": effective_page_size},
        )
        data = resp.get("data", {})
        if isinstance(data, dict):
            return dedupe_component_records(data.get("list", []) or data.get("records", []))
        return dedupe_component_records(data) if isinstance(data, list) else []
    except Exception as e:
        print(f"[sw_common] fetch_component_stocks({code}): {e}", file=sys.stderr)
        return []


def _component_record_code(record: dict) -> str:
    return str(
        record.get("stockCode") or record.get("stockcode")
        or record.get("securityCode") or record.get("securitycode")
        or record.get("fundCode") or record.get("fundcode")
        or ""
    ).strip()


def _component_record_date_key(record: dict) -> str:
    raw = (
        record.get("beginningDate") or record.get("beginningdate")
        or record.get("beginDate") or record.get("begin_date")
        or record.get("date") or ""
    )
    return "".join(ch for ch in str(raw) if ch.isdigit())


def _component_record_weight(record: dict) -> float:
    raw = record.get("newWeight") or record.get("weight") or 0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0


def dedupe_component_records(records: list[dict]) -> list[dict]:
    """Deduplicate component API rows by security code, keeping the latest date."""
    deduped: dict[str, dict] = {}
    passthrough = []
    for idx, record in enumerate(records or []):
        code = _component_record_code(record)
        if not code:
            passthrough.append(record)
            continue
        current = deduped.get(code)
        if current is None:
            deduped[code] = record
            continue
        current_key = _component_record_date_key(current)
        next_key = _component_record_date_key(record)
        if (next_key, _component_record_weight(record), idx) > (
            current_key, _component_record_weight(current), -1
        ):
            deduped[code] = record
    return list(deduped.values()) + passthrough


def fetch_industry_distribution(code: str) -> list:
    """Fetch industry distribution for an index."""
    if USE_WESTOCK:
        raise UnsupportedCapabilityError("成分权重/行业标签缺失，无法计算真实行业分布")
    try:
        resp = sw_post(
            "/insWechatSw/swIndex/getIndexIndustryDistribution",
            body={"swIndexCode": code},
        )
        data = resp.get("data", [])
        return data[1:] if len(data) > 1 else data
    except Exception:
        return []


# ── LLM analysis ─────────────────────────────────────────────────────────────

def _analysis_llm_timeout() -> int:
    try:
        value = int(os.environ.get("SW_ANALYSIS_LLM_TIMEOUT", "12"))
    except ValueError:
        value = 12
    return max(5, min(value, 30))


def _get_llm_call():
    """Load the LLM client, or return None when absent (portable fallback)."""
    import importlib.util

    candidates = []
    env = os.environ.get("SW_LLM_CLIENT")
    if env and os.path.isfile(env):
        candidates.append(env)
    local = os.path.join(SCRIPT_DIR, "llm_client.py")
    if os.path.isfile(local):
        candidates.append(local)
    candidates.append("/agents/_shared/llm/client.py")  # 原平台路径

    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            spec = importlib.util.spec_from_file_location("llm_client", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod.call_llm
        except Exception:
            continue
    return None


def call_analysis_llm(data_summary: str, analysis_type: str) -> str:
    """Call LLM to generate analysis text. Returns empty string on failure."""
    try:
        call_llm = _get_llm_call()
        if call_llm is None:
            return ""
        system = (
            f"你是一名专业证券分析师，基于以下{analysis_type}数据撰写简短分析结论。"
            "要求：2-4句话，客观描述数据特征和趋势，点明关键信号，"
            "不做预测，不给投资建议。使用中文。"
        )
        result = call_llm(
            [{"role": "system", "content": system},
             {"role": "user", "content": data_summary}],
            temperature=0.3,
            max_tokens=512,
            timeout=_analysis_llm_timeout(),
            script_name=f"sw_{analysis_type}",
        )
        return result.strip()
    except Exception:
        return ""


# ── Normalization helpers ────────────────────────────────────────────────────

def normalize_pct(prices: list, base: float) -> list:
    """Convert prices to % change from base."""
    if not base:
        return [0] * len(prices)
    return [round((p - base) / base * 100, 4) for p in prices]


def _float(val) -> float | None:
    if val is None:
        return None
    try:
        return round(float(val), 4)
    except (ValueError, TypeError):
        return None


# ── Group presets ─────────────────────────────────────────────────────────────

GROUP_PRESETS = {
    "style_broad": {
        "801271": "周期", "801272": "先进制造", "801273": "消费",
        "801274": "医药医疗", "801275": "科技TMT", "801276": "金融地产",
    },
    "jc": {
        "802608": "新质生产力优选", "802610": "数字基础设施",
        "802611": "水力发电", "802612": "先进农业",
    },
}

GROUP_LABELS = {
    "style_broad": "大类风格轮动全景",
    "jc": "金创指数群组对比",
}


def fetch_kline_for_group(codes_dict: dict, period: str = "DAY", days: int = 90):
    if USE_WESTOCK:
        return get_klines(codes_dict, period, days)
    result = {}
    for c in codes_dict:
        if is_fund(c):
            raw = sw_post("/insWechatSw/fundIndex/getFundKChartData", body={"swIndexCode":c,"type":period})
        elif is_style_broad(c) or is_jc(c):
            raw = sw_post("/insWechatSw/dflgOrJcIndex/getDLFGKChartData", body={"swIndexCode":c,"type":period,"indexType":1 if is_style_broad(c) else 2})
        else:
            raw = sw_get("/institute-sw/api/index_publish/trend/",params={"swindexcode":c,"period":period})
        result[c] = raw.get("data", [])[-days:]
    return result


def fetch_component_stocks_auto(code: str, page_size: int = 2000) -> list:
    """Fetch component stocks, auto-selecting API by index type.

    Uses page_size up to 2000 to reduce truncation risk for large indices.
    Logs a warning to stderr if the returned count equals page_size (possible truncation).
    """
    if USE_WESTOCK:
        return get_component(code)
    try:
        effective_page_size = page_size
        if is_style_broad(code) or is_jc(code):
            resp = sw_post(
                "/insWechatSw/dflgOrJcIndex/componentDLFGPageList",
                body={
                    "swIndexCode": code,
                    "pageNo": 1, "pageSize": effective_page_size,
                    "indexType": 1 if is_style_broad(code) else 2,
                },
            )
        elif is_fund(code):
            resp = sw_post(
                "/insWechatSw/fundIndex/componentFundPageList",
                body={"swIndexCode": code, "pageNo": 1, "pageSize": effective_page_size},
            )
        else:
            resp = sw_post(
                "/insWechatSw/swIndex/componentStockPageList",
                body={"indexCode": code, "pageNo": 1, "pageSize": effective_page_size},
            )
        data = resp.get("data", {})
        if isinstance(data, dict):
            records = data.get("list", []) or data.get("records", [])
            api_total = data.get("total") or data.get("totalCount")
            if api_total and int(api_total) > len(records):
                print(f"[sw_common] fetch_component_stocks_auto({code}): "
                      f"API total={api_total}, returned={len(records)} (truncated)",
                      file=sys.stderr)
            return dedupe_component_records(records)
        return dedupe_component_records(data) if isinstance(data, list) else []
    except Exception as e:
        print(f"[sw_common] fetch_component_stocks_auto({code}): {type(e).__name__}: {e}",
              file=sys.stderr)
        return []



def _source_codes(indextype):
    key = _INDEXTYPE_ALIASES.get(indextype, indextype)
    if key == "一级行业":
        return INDUSTRY_L1
    if key == "市场表征":
        return MARKET_INDICES
    if key == "风格指数":
        return STYLE_INDICES
    raise UnsupportedCapabilityError(f"{indextype} 批量分类尚未验证；请用明确代码查询")


def _westock_fundamentals(indextype, codes=None):
    codes = codes or _source_codes(indextype)
    quotes = get_quotes(codes)
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=3) as pool:
        vals = list(pool.map(lambda c: get_valuation(c)[-1], codes))
    for v in vals:
        q = quotes[v['code']]
        v.update(close=q['latest'], change_pct=q['change_pct'], turnover=None,
                 volume=q['volume'], mean_price=None, amount_ratio=None,
                 circ_mcap=None, avg_circ_mcap=None, quote_date=q['date'])
    return vals


def _westock_period_dates(period):
    bars = get_kline('801010', limit=500)
    groups = {}
    from datetime import date
    for b in bars[:-1]:
        d = date.fromisoformat(b['bargaindate'])
        # Only finished calendar periods, so live partial weeks/months aren't mislabeled.
        latest = date.fromisoformat(bars[-1]['bargaindate'])
        key = d.isocalendar()[:2] if period == 'WEEK' else (d.year,d.month)
        cur = latest.isocalendar()[:2] if period == 'WEEK' else (latest.year,latest.month)
        if key != cur:
            groups[key] = b['bargaindate']
    return sorted(groups.values(), reverse=True)


def _westock_period_snapshot(period, bargaindate, index_type, codes=None):
    codes = codes or _source_codes(index_type)
    if not isinstance(codes, dict):
        codes = {c:INDUSTRY_NAME_BY_CODE.get(c,c) for c in codes}
    target = bargaindate or _westock_period_dates(period)[0]
    bars = get_klines(codes, limit=500)
    from datetime import date
    d = date.fromisoformat(target)
    key = d.isocalendar()[:2] if period == 'WEEK' else (d.year,d.month)
    result = []
    for c,series in bars.items():
        eligible = [b for b in series if b['bargaindate'] <= target]
        current = eligible[-1] if eligible else None
        previous = [b for b in eligible if (date.fromisoformat(b['bargaindate']).isocalendar()[:2] if period == 'WEEK' else (date.fromisoformat(b['bargaindate']).year,date.fromisoformat(b['bargaindate']).month)) != key]
        if not current or not previous:
            raise IncompleteDataError(f'{c}: 缺少完整周/月基准')
        result.append(dict(code=c,name=codes[c],date=current['bargaindate'],close=current['closeindex'],
                           change_pct=(current['closeindex']/previous[-1]['closeindex']-1)*100,
                           pe=None,pb=None,dp=None,turnover=None,volume=current['bargainamount']))
    return result
