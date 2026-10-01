#!/usr/bin/env python3
"""异动判定：给 Trigger 的 judge 周期取数用，不带 UI，不上屏。

**为什么是一个工具而不是让 judge 跑 bash。** judge 的 `tool_call` 写
`{"tool_name": "check_anomaly"}`，平台按名字分发；写 `bash westock quote` 则要赌
Judge 那套精简环境里装了 westock 这个二进制，装没装无从确认，没装就是静默永不命中。

**为什么判定写在这儿而不是写进 condition。** 条件有三条（交易时段、量比、涨跌幅），
让判定模型去读行情表再自己做算术和时间比较，比读一个 `triggered` 布尔脆得多。
这儿算完，condition 只剩一句「回包 triggered 为 true 时命中」。

口径按 `westock quote` 那套，别换基准：

- `change_pct` 是**当日累计涨跌幅**，分母是昨收（`prev_close`），不是开盘价。
  昨收整天不变，所以这个值一旦越线就整天越线——同一次异动会在后续每次检查里
  重复命中。这是判据本身的性质，不是 bug，去重要在回调那一轮做。
- `volume_ratio` 是当日每分钟均量 ÷ 过去 5 日每分钟均量，同样是当日累计口径。

取数失败返回 `phase:error`（带 code），不伪装成 `triggered:false`——日结要靠它区分
「没异动」和「取不到数」。但 judge 那侧按不命中处理、安静收口（condition 写「回包
triggered 为 true 时命中；其余一切情况都不命中」），每小时一跳的规则不在会话里报错。

**异动和到价各建一条规则，靠 `mode` 区分。** 异动命中后当天停用、次日恢复；到价是
一次性的，命中就结束。两者共用一条规则就共用一个开关：异动停用会把到价一起停到收盘后，
到价收口会把异动也停掉，日结恢复又把已完成的到价重新打开。

- `mode: "anomaly"`：只判异动，忽略到价参数。
- `mode: "alert"`：只判到价，不看涨跌幅和量比，行情缺涨跌幅也照判。
- 不传 `mode`：合并时期建的旧规则还在线上跑，异动照判、给了 `alert_price` 再加判到价。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _quote_src import MARKET_TZ, QuoteError, fetch  # noqa: E402

DEFAULT_VOLUME_RATIO = 2.0
DEFAULT_CHANGE_PCT = 5.0
MODES = ("anomaly", "alert")

# 各市场的连续竞价时段（本地时间），午休那段排除在外。
SESSIONS = {
    "CN": (((9, 30), (11, 30)), ((13, 0), (15, 0))),
    "HK": (((9, 30), (12, 0)), ((13, 0), (16, 0))),
    "US": (((9, 30), (16, 0)),),
}


def _in_session(market: str) -> tuple[bool, str]:
    now = datetime.now(MARKET_TZ[market])
    if now.weekday() >= 5:
        return False, f"{now:%m-%d} 是周末，非交易日"
    minutes = now.hour * 60 + now.minute
    for (sh, sm), (eh, em) in SESSIONS[market]:
        if sh * 60 + sm <= minutes <= eh * 60 + em:
            return True, ""
    return False, f"{now:%H:%M} 不在 {market} 连续竞价时段内"


def check(args: dict) -> dict:
    symbol = str(args.get("symbol") or "").strip()
    if not symbol:
        return {"phase": "error", "code": "MISSING_SYMBOL",
                "message": "symbol 必填，且要带市场前缀。"}

    mode = args.get("mode")
    if mode is not None and mode not in MODES:
        return {"phase": "error", "code": "BAD_MODE",
                "message": "mode 只认 anomaly / alert；不传则异动照判、给了 alert_price 再加判到价。"}
    judge_anomaly = mode != "alert"
    judge_alert = mode != "anomaly"

    vr_min = float(args.get("volume_ratio_min") or DEFAULT_VOLUME_RATIO)
    pct_min = float(args.get("change_pct_min") or DEFAULT_CHANGE_PCT)

    alert_price = args.get("alert_price") if judge_alert else None
    alert_direction = str(args.get("alert_direction") or "").strip() if judge_alert else ""
    if mode == "alert" and alert_price is None:
        return {"phase": "error", "code": "MISSING_ALERT_PRICE",
                "message": "mode 为 alert 时必须给 alert_price 和 alert_direction。"}
    if alert_price is not None and alert_direction not in ("above", "below"):
        return {"phase": "error", "code": "BAD_ALERT_DIRECTION",
                "message": "给了 alert_price 就必须给 alert_direction（above / below）。"}

    try:
        quote = fetch(symbol)
    except QuoteError as exc:
        return {"phase": "error", "code": exc.code, "message": exc.message}

    open_now, closed_reason = _in_session(quote["market"])
    if not open_now:
        return {"phase": "ok", "triggered": False, "hit_kind": [], "quote": quote,
                "reason": f"未命中：{closed_reason}"}

    reasons, kinds, unmet = [], [], []
    degraded = None
    if judge_anomaly:
        change_pct = quote.get("change_pct")
        if change_pct is None:
            return {"phase": "error", "code": "NO_CHANGE_PCT",
                    "message": f"行情源没返回 {symbol} 的涨跌幅，无法判定。"}

        volume_ratio = quote.get("volume_ratio")
        # 量比是 A 股口径，港美股常缺。缺就降级成只看涨跌幅，并在 reason 里说清楚，
        # 不要拿 0 顶替——0 会让「≥2」永远不成立，表现为静默不提醒。
        degraded = volume_ratio is None
        hit_pct = abs(change_pct) >= pct_min
        hit_vr = True if degraded else volume_ratio >= vr_min
        if hit_pct and hit_vr:
            direction = "涨" if change_pct > 0 else "跌"
            vr_text = "量比暂不可判" if degraded else f"量比 {volume_ratio:.2f}"
            kinds.append("anomaly")
            reasons.append(f"{quote['name']} {direction} {abs(change_pct):.2f}%"
                           f"（阈值 {pct_min:g}%），{vr_text}"
                           + ("" if degraded else f"（阈值 {vr_min:g}）") + "，异动命中")
        else:
            if not hit_pct:
                unmet.append(f"涨跌幅 {abs(change_pct):.2f}% < {pct_min:g}%")
            if not hit_vr:
                unmet.append(f"量比 {volume_ratio:.2f} < {vr_min:g}")

    if alert_price is not None:
        price, target = quote["price"], float(alert_price)
        word = "涨破" if alert_direction == "above" else "跌破"
        if (alert_direction == "above" and price >= target) or \
           (alert_direction == "below" and price <= target):
            kinds.append("alert")
            reasons.append(f"{quote['name']} 现价 {price} {word} {target:g}")
        else:
            unmet.append(f"现价 {price} 未{word} {target:g}")

    thresholds = {"volume_ratio_min": vr_min if judge_anomaly else None,
                  "change_pct_min": pct_min if judge_anomaly else None,
                  "alert_price": alert_price,
                  "alert_direction": alert_direction or None}
    if kinds:
        return {"phase": "ok", "triggered": True, "hit_kind": kinds,
                "reason": "；".join(reasons) + "。",
                "degraded_no_volume_ratio": degraded, "quote": quote,
                "thresholds": thresholds}
    return {"phase": "ok", "triggered": False, "hit_kind": [],
            "reason": "未命中：" + "，".join(unmet),
            "degraded_no_volume_ratio": degraded, "quote": quote,
            "thresholds": thresholds}


def main() -> int:
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        args = json.loads(raw)
    except json.JSONDecodeError:
        args = None
    if not isinstance(args, dict):
        result = {"phase": "error", "code": "INVALID_JSON",
                  "message": "请求参数必须是 JSON 对象。"}
    else:
        result = check(args)
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
