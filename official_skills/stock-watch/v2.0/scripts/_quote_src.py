"""判定用的自带取数：腾讯公开行情接口，只用标准库。

Judge（Trigger 周期取数）跑在一套精简环境里，**不能假定 `westock` 这个二进制在**——
它是本包 scripts/westock/setup.sh 装进 PATH 的，而 Judge 拿到的是判定 Agent 自己的
skill 列表，不继承建规则那一轮加载过的东西。命令不在就 exit 127，判定永远答「否」，
规则界面却一直显示已开启：一次都不提醒，也不报错。

所以这一层不依赖任何 CLI，直接读 ``https://qt.gtimg.cn/q=<symbol>``（GBK，``~`` 分隔）。
它只服务判定，**不替代 westock**：交互分析、异动归因、回调正文仍一律走 westock。

字段下标（0 起，2026-09-22 对 sh601020 实测核对过）：

====  ============================
下标  含义
====  ============================
1     名称
3     最新价
4     昨收
30    行情时间 ``yyyyMMddHHmmss``
32    涨跌幅 %
49    量比
====  ============================

测试用 ``STOCK_WATCH_QUOTE_FIXTURES`` 指向一份 ``{"sh601020": {...}}`` 的 JSON，
命中时完全绕过网络。
"""

from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo

QUOTE_URL = "https://qt.gtimg.cn/q={symbol}"
TIMEOUT = 10
_UA = "Mozilla/5.0 (OneAgent stock-watch)"

MARKET_BY_PREFIX = {"sh": "CN", "sz": "CN", "bj": "CN", "hk": "HK", "us": "US"}
CURRENCY_BY_MARKET = {"CN": "CNY", "HK": "HKD", "US": "USD"}
# 港股与 A 股同属北京时间；美股单列，交易时段判定要用它本地的钟。
MARKET_TZ = {
    "CN": ZoneInfo("Asia/Shanghai"),
    "HK": ZoneInfo("Asia/Shanghai"),
    "US": ZoneInfo("America/New_York"),
}

_IDX_NAME, _IDX_PRICE, _IDX_PREV_CLOSE = 1, 3, 4
_IDX_TIME, _IDX_CHANGE_PCT, _IDX_VOLUME_RATIO = 30, 32, 49


class QuoteError(Exception):
    """取数失败。判定侧必须把它跟「条件未命中」分开报，不能吞成 false。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def market_of(symbol: str) -> str:
    market = MARKET_BY_PREFIX.get(symbol[:2].lower())
    if market is None:
        raise QuoteError("BAD_SYMBOL", f"代码 {symbol} 缺少市场前缀（sh/sz/bj/hk/us）。")
    return market


def _num(fields: list[str], idx: int) -> float | None:
    """缺字段返回 None，不返回 0——0 会被阈值比较当成真实值。"""
    if idx >= len(fields):
        return None
    raw = fields[idx].strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _parse_time(raw: str, market: str) -> str:
    raw = raw.strip()
    for fmt in ("%Y%m%d%H%M%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt).replace(
                tzinfo=MARKET_TZ[market]).isoformat()
        except ValueError:
            continue
    return ""


def _fixture(symbol: str) -> dict | None:
    path = os.environ.get("STOCK_WATCH_QUOTE_FIXTURES")
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh).get(symbol)


def fetch(symbol: str) -> dict:
    """取一只票的行情快照。取不到抛 QuoteError，绝不返回半截数据。"""
    symbol = symbol.strip()
    market = market_of(symbol)

    fixed = _fixture(symbol)
    if fixed is not None:
        return {"symbol": symbol, "market": market,
                "currency": CURRENCY_BY_MARKET[market], **fixed}

    req = urllib.request.Request(QUOTE_URL.format(symbol=symbol),
                                 headers={"User-Agent": _UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("gbk", errors="replace")
    except Exception as exc:  # 网络层什么都可能抛，统一成取数失败
        raise QuoteError("QUOTE_FAILED", f"行情源暂时拿不到：{type(exc).__name__}") from exc

    _, _, payload = body.partition('="')
    fields = payload.rstrip('";\n').split("~")
    price = _num(fields, _IDX_PRICE)
    if price is None:
        raise QuoteError("QUOTE_EMPTY", f"行情源没有返回 {symbol} 的价格。")

    return {
        "symbol": symbol,
        "market": market,
        "currency": CURRENCY_BY_MARKET[market],
        "name": fields[_IDX_NAME] if len(fields) > _IDX_NAME else "",
        "price": price,
        "prev_close": _num(fields, _IDX_PREV_CLOSE),
        "change_pct": _num(fields, _IDX_CHANGE_PCT),
        # 量比是 A 股口径字段，港美股常为空——省略好过填 0 冒充。
        "volume_ratio": _num(fields, _IDX_VOLUME_RATIO),
        "quote_time": _parse_time(fields[_IDX_TIME], market)
        if len(fields) > _IDX_TIME else "",
    }
