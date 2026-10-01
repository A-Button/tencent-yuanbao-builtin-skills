#!/usr/bin/env python3
"""四个场景脚本共用的取参、校验与文案装配。

本包**不落盘**：盯盘状态的真源是 make-things 的 ``Thing.goal``，卡片只渲染
Agent 本轮传进来的那一份快照。所以这里没有存储层、没有锁，只有纯函数。

卡面上每一个要显示的字符串都在这里算完。A2UI 没有表达式：``Text.style.color``
是固定 enum、不吃 path 绑定，组件树里也写不出「涨了就红」。所以涨跌方向拆成
``is_up`` / ``is_down`` / ``is_flat`` 三位布尔，由卡片用 ``Visibility`` 在三个
预先染好色的分支之间二选一。
"""

from __future__ import annotations

import json
import sys

# 代码前缀 → 交易所。裸六位数字在 westock 那边本来就会被拒，这里一并拦掉：
# 猜前缀等于静默查了另一只票。
MARKETS = {"sh": "SH", "sz": "SZ", "bj": "BJ", "hk": "HK", "us": "US"}

# 腾讯自选股小程序个股页。示例（沪市华钰矿业）：
# https://wzq.gtimg.com/mm/detail?market=1&type=1&scode=601020
#
# **market 与 type 取同一个值、成对出现**：
# `0` 深交所 / `1` 上交所 / `2` 港股 / `3` 美股 / `bj` 北交所。
# 北交所那一档是字面量 `bj` 而不是数字，别顺手归一成整数。
#
# 早先把 type 写死成 0、美股写成 4：深市碰巧对，港美股全跳到别的票上——URL 照样 200，
# 没有任何信号。scode 是去掉 sh/sz/… 前缀的裸代码。
WZQ_CODE = {"SZ": "0", "SH": "1", "HK": "2", "US": "3", "BJ": "bj"}
WZQ_DETAIL = "https://wzq.gtimg.com/mm/detail?market={code}&type={code}&scode={scode}"

# 涨跌配色按市场惯例走，不搞一刀切：沪深京港「涨红跌绿」，美股「绿涨红跌」。
# 本卡一次只画一只票，不存在多市场混排，所以跟随各自惯例是安全的；真正危险的是
# 让一个看惯美股的人把绿色读成上涨。为此美股那张会在提示行标出口径。
GREEN_MEANS_UP = {"US"}
COLOUR_HINT = "美股口径：绿涨红跌"

GRADE_LABELS = {"verified": "已验证", "inferred": "归因推断", "unknown": "暂无归因"}

ADVICE_CHOICES = ("持有", "加仓", "观望", "减仓", "回避")
ADVICE_REASON_MAX_CHARS = 30

# 一条资讯两个标签，同时画，不互相顶掉。
# 类型：公告 / 研报 / 事件 / 新闻。情绪：利好 / 利空 / 中立。
NEWS_KIND_LABELS = {"notice": "公告", "report": "研报", "event": "事件", "news": "新闻"}
NEWS_KIND_TONES = {"notice": "warn", "report": "info", "event": "info", "news": "mute"}
# 利好/利空也跟随市场口径：美股那边「利好」该是绿的，否则同一张卡里
# 价格绿、标签红，读起来自相矛盾。中性和中立都是「没方向」，卡上写成中立。
STANCE_DIRECTION = {"利好": "up", "利空": "down"}
STANCE_LABELS = {"利好": "利好", "利空": "利空", "中性": "中立", "中立": "中立"}

# as_of 的粒度决定卡面要不要补后缀。休市时把昨收标成实时比不显示更糟——
# 用户会拿它做决定。
AS_OF_SUFFIX = {"realtime": "", "minute": "", "close": " 收盘"}


class CardError(RuntimeError):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _first_sentences(text: str, limit: int = 3) -> str:
    """建议卡理由最多三句。模型爱把技术面资金面基本面全塞进来，卡面会撑爆。"""
    text = text.strip()
    if not text:
        return text
    parts: list[str] = []
    buf: list[str] = []
    for ch in text:
        buf.append(ch)
        if ch in "。！？":
            sentence = "".join(buf).strip()
            buf = []
            if sentence:
                parts.append(sentence)
            if len(parts) >= limit:
                return "".join(parts)
    tail = "".join(buf).strip()
    if tail and len(parts) < limit:
        parts.append(tail)
    return "".join(parts) if parts else text


def _clip_text(text: str, limit: int) -> str:
    """按 Unicode 字符数截断，省略号也计入上限。"""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[:limit - 1].rstrip("，,；;。！？ ") + "…"


def _text(args: dict, name: str) -> str:
    """取一个非空白的必填文本。

    字段是否存在由 app.yaml 的 ``required`` 在 CLI 侧拦下；但 CLI 的校验器不支持
    ``pattern``，``minLength: 1`` 拦不住纯空格，所以「去掉空白后不能为空」留在这里。
    """
    value = args.get(name)
    if not isinstance(value, str) or not value.strip():
        raise CardError("INVALID_ARGUMENT", f"缺少参数：{name}")
    return value.strip()


def _number(args: dict, name: str) -> float | None:
    value = args.get(name)
    return float(value) if isinstance(value, (int, float)) else None


def _decimals(value: float) -> int:
    """按数值自身的最短表示推小数位，让涨跌额和现价对齐到同一精度。

    港股常见三位小数（9.006），A 股两位（1685.20）。入参是 JSON 数字，尾零已经
    在序列化时丢了，所以只能从值本身推——这比一律定死两位更贴近数据源的口径。
    """
    text = repr(float(value))
    if "e" in text or "E" in text:
        return 2
    fraction = text.partition(".")[2].rstrip("0")
    return min(max(len(fraction), 2), 4)


def _fixed(value: float, decimals: int) -> str:
    return f"{value:.{decimals}f}"


def _signed(value: float, decimals: int) -> str:
    return f"{value:+.{decimals}f}"


def parse_symbol(args: dict) -> dict:
    """代码归一 + 拼出「裸代码·交易所」。

    交易所只出现在代码那一行，不再额外挂一个小标——名称后面跟个 badge 会把视线
    从价格上拽走，而代码行本来就带着同一个信息。
    """
    code = _text(args, "code").lower()
    for prefix, market in MARKETS.items():
        if code.startswith(prefix) and len(code) > len(prefix):
            bare = code[len(prefix):]
            # 美股代码是字母，港股/A 股是数字；统一大写只影响前者。
            scode = bare.upper()
            return {
                "code": code,
                "market": market,
                "scode": scode,
                "code_text": f"{scode}·{market}",
            }
    raise CardError(
        "INVALID_ARGUMENT",
        f"代码要带市场前缀（sh/sz/bj/hk/us），拿到的是：{code}",
    )


def zxg_detail_url(symbol: dict) -> str:
    """「查看详情」打开的自选股小程序个股页。

    ``MARKETS`` 和 ``WZQ_CODE`` 是两张表，将来加市场时可能只改了一张；没登记的返回
    空串，让「查看详情」整个不摆，而不是猜一个把用户点到别的票上。
    """
    code = WZQ_CODE.get(symbol["market"])
    if code is None:
        return ""
    return WZQ_DETAIL.format(code=code, scode=symbol["scode"])


def alert_word(direction: str) -> str:
    return "止盈" if direction == "above" else "止损"


def cross_word(direction: str) -> str:
    return "涨破" if direction == "above" else "跌破"


def base_card(args: dict) -> dict:
    """四个场景共用的那半张卡：名称、代码、时刻、现价、涨跌。"""
    symbol = parse_symbol(args)
    name = _text(args, "name")
    as_of = _text(args, "as_of")
    kind = args.get("as_of_kind")
    if kind not in AS_OF_SUFFIX:
        raise CardError("INVALID_ARGUMENT", f"as_of_kind 只能是 realtime / minute / close，拿到的是：{kind}")

    price = _number(args, "price")
    if price is None:
        raise CardError("INVALID_ARGUMENT", "缺少参数：price")
    decimals = _decimals(price)

    change = _number(args, "change")
    change_pct = _number(args, "change_pct")
    parts = []
    if change is not None:
        parts.append(_signed(change, decimals))
    if change_pct is not None:
        parts.append(f"{_signed(change_pct, 2)}%")

    # 方向（is_up / is_down / is_flat）是业务语义，颜色（is_red / is_green）是显示口径，
    # 两者在美股是反的，所以必须分开算——把它们混成一组，换市场时就得改判定逻辑。
    # **缺字段不算平盘**：方向三位全 false，卡片那一行整个不画，否则会留一个空位，
    # 看起来像取到了 0。
    is_up = change_pct is not None and change_pct > 0
    is_down = change_pct is not None and change_pct < 0
    is_flat = bool(parts) and not is_up and not is_down
    green_up = symbol["market"] in GREEN_MEANS_UP
    is_red = is_down if green_up else is_up
    is_green = is_up if green_up else is_down

    currency = (args.get("currency") or "").strip()
    return {
        "kicker": "智能盯盘",
        "code": symbol["code"],
        "name": name,
        "code_text": symbol["code_text"],
        "as_of_text": as_of + AS_OF_SUFFIX[kind],
        "price_text": _fixed(price, decimals),
        # 涨跌额与涨跌幅并排，中间留空，不套括号——括号会让两个数看起来主次不同，
        # 而它们说的是同一件事的两种量纲。
        "change_text": "  ".join(parts),
        "has_change": bool(parts),
        "is_up": is_up,
        "is_down": is_down,
        "is_flat": is_flat,
        "is_red": is_red,
        "is_green": is_green,
        # 价格也跟着涨跌染色（设计稿里 9.006 是红的）。它必须恰好命中一个分支，
        # 所以没有方向时走这一位，而不是复用只在「有数据且为 0」时才真的 is_flat。
        "is_plain_price": not is_red and not is_green,
        # 只有真染上色了才需要解释口径；一片中性时摆这句话只是噪音。
        "_colour_hint": COLOUR_HINT if green_up and (is_red or is_green) else "",
        "has_currency": bool(currency),
        "currency_text": currency,
        "detail_url": zxg_detail_url(symbol),
        "_decimals": decimals,
        "_price": price,
    }


def with_actions(card: dict, secondary_label: str, secondary_action: str) -> dict:
    """主按钮「帮我分析」回传对话；「查看详情」用 openUrl 打开自选股小程序。

    两种按钮都是 ``action.functionCall``：追问用 ``sendQuery``，跳转用 ``openUrl``。
    不要用 ``action.event``（渲染端不认，按钮点了没反应），也不要用 ``open_workspace``
    （那是转场到本包 H5 资源）。``secondary_action`` 只用来选次按钮形态，不进 dataModel。
    """
    name = card["name"]
    card["secondary_label"] = secondary_label
    jump = secondary_action == "detail"
    # 拼不出个股页的市场整个次按钮不摆：留一个点了没反应的「查看详情」，
    # 或者让它改口去回会话改提醒，都比没有更迷惑。
    card["has_detail_url"] = jump and bool(card.get("detail_url"))
    card["has_secondary_prompt"] = not jump
    card["secondary_prompt"] = "" if jump else f"改一下{name}的到价提醒"
    card["primary_label"] = "帮我分析"
    card["primary_prompt"] = f"帮我分析{name}现在该怎么操作"
    return card


def note(card: dict, args: dict, text: str) -> dict:
    """提示行。Agent 传了 `note` 就用它，否则用本包按入参算出来的那句。

    这一行不是装饰：卡上其余部分都是「此刻是多少」，只有它回答「离我关心的那条
    线还有多远」。所以宁可算一句真的，也不要摆一句套话。

    美股的配色口径也挂在这里，且**不受 `note` 覆盖影响**——它解释的是卡面颜色
    怎么读，Agent 换一句文案不该把它顶掉。
    """
    override = (args.get("note") or "").strip()
    parts = [part for part in (override or text, card["_colour_hint"]) if part]
    resolved = " · ".join(parts)
    card["has_note"] = bool(resolved)
    card["note_text"] = resolved
    return card


def threshold_note(card: dict, direction: str, alert_price: float) -> str:
    """触发条件 + 现价离它还有多远。距离是算出来的，不是抄入参。"""
    threshold = _fixed(alert_price, _decimals(alert_price))
    base = f"触发条件：{cross_word(direction)} {threshold}"
    if alert_price <= 0:
        return base
    gap = (card["_price"] - alert_price) / alert_price * 100
    crossed = gap <= 0 if direction == "below" else gap >= 0
    word = "现价已" + ("低于" if direction == "below" else "高于") if crossed else "距触发还有"
    return f"{base} · {word} {abs(gap):.2f}%"


def anomaly_note(args: dict) -> str:
    parts = []
    volume_ratio = _number(args, "volume_ratio")
    if volume_ratio is not None:
        parts.append(f"量比 {_fixed(volume_ratio, 2)}")
    reason = (args.get("reason") or "").strip()
    if reason:
        parts.append(f"{GRADE_LABELS.get(args.get('grade'), '暂无归因')}：{reason}")
    else:
        # 取数成功但没有可归因内容，和「还没归因」是两回事，措辞不能含糊。
        parts.append("暂无明确消息面")
    return " · ".join(parts)


def require_items(args: dict, limit: int) -> list[dict]:
    items = args.get("items")
    if not isinstance(items, list) or not items:
        raise CardError("INVALID_ARGUMENT", "缺少参数：items")
    rows = [item for item in items if isinstance(item, dict)]
    if not rows:
        raise CardError("INVALID_ARGUMENT", "items 里没有一条可用记录。")
    return rows[:limit]


def advice_row(item: dict, index: int) -> dict:
    """建议列表的一行：跟单标的灰底面板同一套字段——时刻 / 名称 / 代码·交易所 / 现价涨跌。

    操作标签单独挂在名称后面，不再把代码和「观望」揉进一行标题里，否则时间、
    交易所、涨跌额都会被挤掉。每行自带颜色位：A2UI 列表项用相对路径，颜色
    又不能绑 path，所以红绿必须在这里算完。
    """
    symbol = parse_symbol(item)
    name = _text(item, "name")
    advice = _text(item, "advice")
    if advice not in ADVICE_CHOICES:
        raise CardError(
            "INVALID_ARGUMENT",
            f"advice 只能是 {' / '.join(ADVICE_CHOICES)}，拿到的是：{advice}",
        )

    price = _number(item, "price")
    if price is None:
        raise CardError("INVALID_ARGUMENT", f"第 {index + 1} 条缺少 price")
    decimals = _decimals(price)

    as_of = _text(item, "as_of")
    kind = item.get("as_of_kind")
    if kind not in AS_OF_SUFFIX:
        raise CardError(
            "INVALID_ARGUMENT",
            f"第 {index + 1} 条 as_of_kind 只能是 realtime / minute / close，拿到的是：{kind}",
        )
    as_of_text = as_of + AS_OF_SUFFIX[kind]

    change = _number(item, "change")
    change_pct = _number(item, "change_pct")
    parts = []
    if change is not None:
        parts.append(_signed(change, decimals))
    if change_pct is not None:
        parts.append(f"{_signed(change_pct, 2)}%")

    is_up = change_pct is not None and change_pct > 0
    is_down = change_pct is not None and change_pct < 0
    is_flat = bool(parts) and not is_up and not is_down
    green_up = symbol["market"] in GREEN_MEANS_UP
    is_red = is_down if green_up else is_up
    is_green = is_up if green_up else is_down

    reason = _clip_text(
        _first_sentences((item.get("reason") or "").strip()),
        ADVICE_REASON_MAX_CHARS,
    )
    return {
        "name": name,
        "advice": advice,
        "code": symbol["code"],
        "code_text": symbol["code_text"],
        "as_of_text": as_of_text,
        "has_as_of": bool(as_of_text),
        "price_text": _fixed(price, decimals),
        "change_text": "  ".join(parts),
        "has_change": bool(parts),
        "is_red": is_red,
        "is_green": is_green,
        "is_flat": is_flat,
        "is_plain_price": not is_red and not is_green,
        "has_reason": bool(reason),
        "reason_text": reason,
        "detail_url": zxg_detail_url(symbol),
        "analyze_prompt": f"帮我分析{name}现在该怎么操作",
        "_market": symbol["market"],
    }


def news_row(item: dict, index: int) -> dict:
    """资讯列表的一行：归属标的 · 标题 / 彩色标签 / 「时间 · 来源 · 一句话解读」。

    归属标的是**逐条**的，不是整张卡一个：一次汇总里既有某只票的公告，也有
    「锂价止跌反弹」这种没有归属的行业新闻。利好/利空的配色也因此逐条判断——
    同一张卡里 A 股的利好红、美股的利好绿。
    """
    title = _text(item, "title")
    code = (item.get("code") or "").strip()
    market = parse_symbol(item)["market"] if code else ""
    green_up = market in GREEN_MEANS_UP
    name = (item.get("name") or "").strip()
    kind = item.get("kind")
    if kind not in NEWS_KIND_LABELS:
        raise CardError(
            "INVALID_ARGUMENT",
            f"第 {index + 1} 条的 kind 只能是 {' / '.join(NEWS_KIND_LABELS)}，拿到的是：{kind}",
        )
    stance = (item.get("stance") or "").strip()
    if stance and stance not in STANCE_LABELS:
        raise CardError(
            "INVALID_ARGUMENT",
            f"第 {index + 1} 条的 stance 只能是 利好 / 利空 / 中立，拿到的是：{stance}",
        )
    # 省略 stance 不编方向，情绪标签画「中立」。类型标签照常画，两枚一起出。
    stance_label = STANCE_LABELS.get(stance, "中立")
    direction = STANCE_DIRECTION.get(stance)
    if direction:
        up_tone, down_tone = ("green", "red") if green_up else ("red", "green")
        stance_tone = up_tone if direction == "up" else down_tone
    else:
        stance_tone = "mute"
    kind_label = NEWS_KIND_LABELS[kind]
    kind_tone = NEWS_KIND_TONES[kind]

    source = " · ".join(
        str(value).strip()
        for value in (item.get("published_at"), item.get("origin"))
        if str(value or "").strip()
    )
    takeaway = str(item.get("takeaway") or "").strip()
    # meta_text 留给还在线上的旧模板：时间、来源、解读合成一行。
    meta = " · ".join(part for part in (source, takeaway) if part)
    url = str(item.get("url") or "").strip()
    if url and not url.startswith(("http://", "https://")):
        raise CardError(
            "INVALID_ARGUMENT",
            f"第 {index + 1} 条的 url 必须是 http(s) 原文链接，拿到的是：{url}",
        )
    # 有方向时，旧模板那一枚标签画情绪；没方向才退回类型。
    # 新模板不读 tag_*，两枚标签走上面的 kind_* / stance_*。
    if direction:
        legacy_text = stance_label
        legacy_tone = stance_tone
    else:
        legacy_text = kind_label
        legacy_tone = kind_tone
    shown_title = f"{name} · {title}" if name else title
    # 两枚标签叠在标题第一行左侧。标题用全角空格让出标签宽度（两枚 caption
    # 芯片加中间 4dp，约 6 个 h5 全角字宽），换行从行首开始，不缩在标签右边。
    return {
        # 名称由本包拼在标题前，Agent 不用自己接字符串；没有归属标的就只出标题。
        "title": shown_title,
        "title_shown": "\u3000" * 6 + shown_title,
        "kind_text": kind_label,
        "kind_warn": kind_tone == "warn",
        "kind_info": kind_tone == "info",
        "kind_mute": kind_tone == "mute",
        "stance_text": stance_label,
        "stance_red": stance_tone == "red",
        "stance_green": stance_tone == "green",
        "stance_mute": stance_tone == "mute",
        # 线上还在用的旧资讯模板只认 tag_text / tag_red 这一套。
        # 脚本改成 kind_* / stance_* 之后这些字段没了，六个 Visibility 全假，标签整排消失。
        "tag_text": legacy_text,
        "tag_red": legacy_tone == "red",
        "tag_green": legacy_tone == "green",
        "tag_info": legacy_tone == "info",
        "tag_warn": legacy_tone == "warn",
        "tag_mute": legacy_tone == "mute",
        "has_meta": bool(meta),
        "meta_text": meta,
        "source_text": source,
        "has_source": bool(source),
        "takeaway_text": takeaway,
        "has_takeaway": bool(takeaway),
        "url": url,
        "has_url": bool(url),
        "no_url": not url,
        "_market": market,
    }


def run(build) -> int:
    """场景脚本的统一收尾：解析入参 → 装配卡面 → 打一行 JSON。

    ``build(args) -> dict`` 只管自己那个场景的标题、说明和按钮。出参整份挂到 A2UI
    的数据模型根路径，所以卡片里的绑定路径就是这里的键名。
    """
    raw = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        args = json.loads(raw)
        if not isinstance(args, dict):
            raise CardError("INVALID_ARGUMENT", "请求参数必须为对象。")
        result = build(args)
        result = {key: value for key, value in result.items() if not key.startswith("_")}
        result["phase"] = "ok"
    except (json.JSONDecodeError, CardError) as exc:
        code = getattr(exc, "code", "INVALID_JSON")
        result = {
            "phase": "error",
            "code": code,
            "message": getattr(exc, "message", "请求参数不是合法 JSON。"),
            "retryable": code != "INVALID_JSON",
        }
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    return 0
