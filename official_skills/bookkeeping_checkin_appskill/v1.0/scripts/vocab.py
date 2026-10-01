#!/usr/bin/env python3
"""记账业务词表：类型 / 分类 / 账户三套枚举，以及中文别名归一。

这是**唯一**的取值来源：card_schema 下发 options 给客户端、cli_contract 校验模型传参、
ledger_api 落库前归一，三处读的都是这里。改一处枚举，三处同时生效——否则会出现
「卡片能选但落库被拒」这种只在联调时才暴露的裂缝。

三层含义要分清：
  id            落库与协议里的机器码（英文），value.raw / value.semanticCode 用它
  label         卡面与编辑面板上的中文，value.displayText 用它
  aliases       只用于「从用户自然语言里认出这个选项」，不下发给客户端

分类依赖类型：收入和支出各有一组，客户端靠 category 字段的 dependsOnFieldId
在编辑面板里联动切换选项。所以 CATEGORIES 按类型分组存。
"""

from __future__ import annotations

# --- 类型 -------------------------------------------------------------------
# 一期只有收支两种，没有「转账」：转账要涉及两个账户，一期的单条流水结构表达不了。
TRANSACTION_TYPES: dict[str, str] = {
    "income": "收入",
    "expense": "支出",
}

TRANSACTION_TYPE_ALIASES: dict[str, str] = {
    "收入": "income", "进账": "income", "收到": "income", "赚": "income",
    "入账": "income", "到账": "income",
    "支出": "expense", "花费": "expense", "消费": "expense", "花了": "expense",
    "付": "expense", "支付": "expense", "买": "expense", "出账": "expense",
}

# --- 分类（按类型分组）------------------------------------------------------
# 顺序即卡片下拉里的展示顺序，"其他" 一律排最后（它同时是兜底项）。
CATEGORIES: dict[str, dict[str, str]] = {
    "income": {
        "salary": "工资",
        "bonus": "奖金",
        "investment_income": "理财收益",
        "part_time": "兼职",
        "red_packet": "红包",
        "other": "其他",
    },
    "expense": {
        "dining": "餐饮",
        "transportation": "交通",
        "shopping": "购物",
        "entertainment": "娱乐",
        "education": "教育",
        "medical": "医疗",
        "housing": "住房",
        "travel": "旅游",
        "investment": "投资",
        "other": "其他",
    },
}

# 判断不出来时的兜底分类（规则：无法判断时默认其他）。
FALLBACK_CATEGORY = "other"

CATEGORY_ALIASES: dict[str, str] = {
    # 收入
    "工资": "salary", "薪水": "salary", "月薪": "salary", "发工资": "salary",
    "奖金": "bonus", "年终奖": "bonus", "绩效": "bonus",
    "理财": "investment_income", "理财收益": "investment_income",
    "利息": "investment_income", "分红": "investment_income",
    "兼职": "part_time", "外快": "part_time", "副业": "part_time",
    "红包": "red_packet", "压岁钱": "red_packet",
    # 支出
    "餐饮": "dining", "吃饭": "dining", "午饭": "dining", "晚饭": "dining",
    "早饭": "dining", "早餐": "dining", "午餐": "dining", "晚餐": "dining",
    "外卖": "dining", "喝": "dining", "咖啡": "dining", "奶茶": "dining",
    "交通": "transportation", "打车": "transportation", "地铁": "transportation",
    "公交": "transportation", "加油": "transportation", "停车": "transportation",
    "高铁": "transportation", "机票": "transportation",
    "购物": "shopping", "买衣服": "shopping", "日用品": "shopping", "超市": "shopping",
    "娱乐": "entertainment", "电影": "entertainment", "游戏": "entertainment",
    "唱歌": "entertainment", "健身": "entertainment",
    "教育": "education", "培训": "education", "书": "education", "学费": "education",
    "医疗": "medical", "看病": "medical", "买药": "medical", "体检": "medical",
    "住房": "housing", "房租": "housing", "水电": "housing", "物业": "housing",
    "房贷": "housing",
    "旅游": "travel", "旅行": "travel", "酒店": "travel", "民宿": "travel",
    "投资": "investment", "买股票": "investment", "基金": "investment",
    # 两边同名
    "其他": "other",
}

# --- 账户 -------------------------------------------------------------------
ACCOUNTS: dict[str, str] = {
    "wechat": "微信支付",
    "alipay": "支付宝",
    "bank_card": "银行卡",
    "cash": "现金",
    "credit_card": "信用卡",
    "other": "其他",
}

FALLBACK_ACCOUNT = "other"

# 下发给客户端的 aliases：客户端在编辑面板里做模糊匹配用。
# 只放「与 label 不同字面」的叫法——和 label 一模一样的别名是纯噪音，
# 客户端本来就会拿 label 匹配。服务端侧的自然语言推断走下面的 ACCOUNT_ALIASES，
# 那份不下发，两者职责分开。
ACCOUNT_CLIENT_ALIASES: dict[str, list[str]] = {
    "wechat": ["微信"],
    "bank_card": ["储蓄卡", "借记卡"],
}

ACCOUNT_ALIASES: dict[str, str] = {
    "微信": "wechat", "微信支付": "wechat", "wx": "wechat", "零钱": "wechat",
    "支付宝": "alipay", "alipay": "alipay", "余额宝": "alipay",
    "银行卡": "bank_card", "储蓄卡": "bank_card", "借记卡": "bank_card",
    "刷卡": "bank_card",
    "现金": "cash", "付现": "cash", "现钞": "cash",
    "信用卡": "credit_card", "花呗": "credit_card", "白条": "credit_card",
    "其他": "other",
}

# --- 币种 -------------------------------------------------------------------
# 卡面下拉是常用中文名，允许用户自填。ISO 码只当别名认；表外币种原样保留，不拒绝。
CURRENCIES: dict[str, str] = {
    "人民币": "人民币",
    "美元": "美元",
    "欧元": "欧元",
    "日元": "日元",
    "英镑": "英镑",
    "港元": "港元",
    "澳元": "澳元",
    "加元": "加元",
    "瑞士法郎": "瑞士法郎",
    "新加坡元": "新加坡元",
}

DEFAULT_CURRENCY = "人民币"

CURRENCY_CLIENT_ALIASES: dict[str, list[str]] = {
    "人民币": ["CNY", "RMB"],
    "美元": ["USD"],
    "欧元": ["EUR"],
    "日元": ["JPY"],
    "英镑": ["GBP"],
    "港元": ["HKD"],
    "澳元": ["AUD"],
    "加元": ["CAD"],
    "瑞士法郎": ["CHF"],
    "新加坡元": ["SGD"],
}

CURRENCY_ALIASES: dict[str, str] = {
    "CNY": "人民币", "RMB": "人民币", "人民币": "人民币",
    "USD": "美元", "美元": "美元", "美金": "美元",
    "EUR": "欧元", "欧元": "欧元",
    "JPY": "日元", "日元": "日元",
    "GBP": "英镑", "英镑": "英镑",
    "HKD": "港元", "港元": "港元", "港币": "港元",
    "AUD": "澳元", "澳元": "澳元", "澳币": "澳元",
    "CAD": "加元", "加元": "加元", "加币": "加元",
    "CHF": "瑞士法郎", "瑞士法郎": "瑞士法郎",
    "SGD": "新加坡元", "新加坡元": "新加坡元", "新元": "新加坡元",
}

CURRENCY_SYMBOLS: dict[str, str] = {
    "人民币": "¥", "CNY": "¥",
    "美元": "$", "USD": "$",
    "欧元": "€", "EUR": "€",
    "日元": "¥", "JPY": "¥",
    "英镑": "£", "GBP": "£",
    "港元": "HK$", "港币": "HK$", "HKD": "HK$",
    "澳元": "A$", "AUD": "A$",
    "加元": "C$", "CAD": "C$",
    "瑞士法郎": "Fr", "CHF": "Fr",
    "新加坡元": "S$", "SGD": "S$",
}


def type_label(transaction_type: str) -> str:
    return TRANSACTION_TYPES.get(transaction_type, "")


def category_label(transaction_type: str, category: str) -> str:
    return CATEGORIES.get(transaction_type, {}).get(category, "")


def account_label(account: str) -> str:
    return ACCOUNTS.get(account, "")


def category_ids(transaction_type: str) -> tuple[str, ...]:
    return tuple(CATEGORIES.get(transaction_type, {}))


def normalize_transaction_type(text: str) -> str:
    """自然语言 / 机器码 -> 类型 id。认不出来返回空串（交给上层提示用户选）。"""
    raw = str(text or "").strip()
    if not raw:
        return ""
    if raw in TRANSACTION_TYPES:
        return raw
    lowered = raw.lower()
    if lowered in TRANSACTION_TYPES:
        return lowered
    if raw in TRANSACTION_TYPE_ALIASES:
        return TRANSACTION_TYPE_ALIASES[raw]
    for alias, tid in TRANSACTION_TYPE_ALIASES.items():
        if alias in raw:
            return tid
    return ""


def normalize_category(transaction_type: str, text: str) -> str:
    """-> 该类型下的分类 id。认不出来返回 other（规则：无法判断时默认其他）。

    注意分类是**类型内**唯一的：expense 的 dining 和 income 的 salary 不在同一个
    命名空间里，所以归一必须先知道类型。别名命中了但不属于当前类型（比如支出记账
    却说了"工资"）时不硬塞，退回 other。
    """
    valid = CATEGORIES.get(transaction_type, {})
    if not valid:
        return FALLBACK_CATEGORY
    raw = str(text or "").strip()
    if not raw:
        return FALLBACK_CATEGORY
    if raw in valid:
        return raw
    lowered = raw.lower()
    if lowered in valid:
        return lowered
    hit = CATEGORY_ALIASES.get(raw)
    if hit and hit in valid:
        return hit
    for label, cid in ((v, k) for k, v in valid.items()):
        if label and label in raw:
            return cid
    for alias, cid in CATEGORY_ALIASES.items():
        if alias in raw and cid in valid:
            return cid
    return FALLBACK_CATEGORY


def normalize_account(text: str) -> str:
    """-> 账户 id。认不出来返回 other（规则：无法判断时默认其他）。"""
    raw = str(text or "").strip()
    if not raw:
        return FALLBACK_ACCOUNT
    if raw in ACCOUNTS:
        return raw
    lowered = raw.lower()
    if lowered in ACCOUNTS:
        return lowered
    if raw in ACCOUNT_ALIASES:
        return ACCOUNT_ALIASES[raw]
    for alias, aid in ACCOUNT_ALIASES.items():
        if alias in raw:
            return aid
    return FALLBACK_ACCOUNT


def currency_label(currency: str) -> str:
    canon = normalize_currency(currency)
    return CURRENCIES.get(canon, canon)


def normalize_currency(text: str) -> str:
    """ISO 码 / 中文名 -> 词表中文名。空则默认人民币；表外币种原样保留，不拒绝。"""
    raw = str(text or "").strip()
    if not raw:
        return DEFAULT_CURRENCY
    if raw in CURRENCIES:
        return raw
    hit = CURRENCY_ALIASES.get(raw) or CURRENCY_ALIASES.get(raw.upper())
    if hit:
        return hit
    return raw


def currency_symbol(currency: str) -> str:
    return CURRENCY_SYMBOLS.get(normalize_currency(currency), "")


def format_money(amount: float | int | None, currency: str = DEFAULT_CURRENCY) -> str:
    """38.5 -> ¥38.50。金额一律两位小数，不做千分位（设计稿上没有）。"""
    if amount is None:
        return ""
    try:
        value = float(amount)
    except (TypeError, ValueError):
        return ""
    return f"{currency_symbol(currency)}{value:.2f}"
