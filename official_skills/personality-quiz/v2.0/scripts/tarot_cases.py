#!/usr/bin/env python3
"""中文塔罗情境案例的确定性检索器。

案例只帮助把已经确认的基础牌义映射到用户问题，不改变牌义本身。当前实现不依赖
外部向量服务，便于在 Skill 本地复现和审计；后续可在保持同一硬过滤与返回结构的
前提下替换语义召回层。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from tarot_deck import CONTENT_VERSION, TRADITION_NAME, card_face, DECK_SIZE


CASES_PATH = Path(__file__).resolve().parents[1] / "references" / "interpretation-cases.zh-CN.json"
ALLOWED_REVIEW_STATUS = {"团队初审", "专家复核"}

TOPIC_TERMS: dict[str, set[str]] = {
    "事业": {"事业", "工作", "职业", "岗位", "升职", "转岗", "项目", "创业", "同事", "团队", "领导"},
    "关系": {"关系", "感情", "恋爱", "伴侣", "对象", "暧昧", "前任", "婚姻", "喜欢"},
    "学习": {"学习", "考试", "课程", "技能", "练习", "作业", "升学", "复习"},
    "家庭": {"家庭", "家人", "父母", "孩子", "照顾", "亲属", "家里"},
    "资源": {"资源", "金钱", "财务", "存款", "借钱", "收入", "支出", "时间", "精力"},
    "自我成长": {"成长", "自己", "迷茫", "习惯", "情绪", "改变", "方向", "内耗", "恢复"},
    "选择": {"选择", "决定", "纠结", "取舍", "比较", "方案", "怎么办"},
}

TOPIC_ALIASES: dict[str, str] = {
    "事业": "事业",
    "工作": "事业",
    "职业": "事业",
    "爱情": "关系",
    "感情": "关系",
    "恋爱": "关系",
    "关系": "关系",
    "学业": "学习",
    "学习": "学习",
    "考试": "学习",
    "家庭": "家庭",
    "财运": "资源",
    "财富": "资源",
    "金钱": "资源",
    "资源": "资源",
    "成长": "自我成长",
    "自我成长": "自我成长",
    "选择": "选择",
}

HIGH_IMPACT_TERMS: dict[str, set[str]] = {
    "医疗健康": {"诊断", "癌症", "怀孕", "生育", "药物", "手术", "病情", "治疗"},
    "法律": {"起诉", "判刑", "官司", "违法", "犯罪", "法律"},
    "金融投资": {"股票", "基金", "投资", "博彩", "赌博", "彩票", "借贷"},
    "人身安全": {"自杀", "伤害", "暴力", "失踪", "死亡", "危险"},
    "录取录用": {"录取", "录用", "offer", "签证", "会不会通过"},
}

ORIENTATION_MAP = {
    "正位": "正位",
    "upright": "正位",
    "逆位": "逆位",
    "reversed": "逆位",
}


def load_corpus(path: Path = CASES_PATH) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("tradition") != TRADITION_NAME:
        raise ValueError("案例库体系与当前牌库不一致")
    if payload.get("contentVersion") != CONTENT_VERSION:
        raise ValueError("案例库内容版本与当前牌库不一致")
    if not isinstance(payload.get("cases"), list):
        raise ValueError("案例库缺少案例列表")
    return payload


def compact(text: str) -> str:
    return re.sub(r"[^0-9A-Za-z\u3400-\u9fff]+", "", str(text or "").lower())


def ngrams(text: str, size: int = 2) -> set[str]:
    normalized = compact(text)
    return {normalized[index:index + size] for index in range(max(0, len(normalized) - size + 1))}


def similarity(left: str, right: str) -> float:
    left_grams = ngrams(left)
    right_grams = ngrams(right)
    if not left_grams or not right_grams:
        return 0.0
    return 2 * len(left_grams & right_grams) / (len(left_grams) + len(right_grams))


def infer_topics(question: str, explicit_topic: str = "") -> set[str]:
    explicit = TOPIC_ALIASES.get(compact(explicit_topic))
    found = {explicit} if explicit else set()
    normalized = compact(question)
    for topic, terms in TOPIC_TERMS.items():
        if any(compact(term) in normalized for term in terms):
            found.add(topic)
    return found


def detect_high_impact(question: str) -> list[str]:
    normalized = compact(question)
    return [label for label, terms in HIGH_IMPACT_TERMS.items() if any(compact(term) in normalized for term in terms)]


def parse_card(spec: str) -> dict[str, str]:
    """解析 `牌名或稳定标识|朝向|位次|逆位机制`；后面三项均可省略。"""
    parts = [part.strip() for part in re.split(r"[|｜]", spec)]
    if not parts or not parts[0]:
        raise ValueError("牌面参数缺少牌名或稳定标识")
    known = {
        value
        for index in range(DECK_SIZE)
        for value in (card_face(index)["cardId"], card_face(index)["nameZh"])
    }
    if parts[0] not in known:
        raise ValueError(f"无法识别牌面：{parts[0]}")
    return {
        "identity": parts[0],
        "orientation": ORIENTATION_MAP.get(parts[1], parts[1]) if len(parts) > 1 else "",
        "position": parts[2] if len(parts) > 2 else "",
        "reversalMode": parts[3] if len(parts) > 3 else "",
    }


def card_matches(query_card: dict[str, str], case_card: dict[str, Any]) -> bool:
    return query_card["identity"] in {case_card.get("cardId"), case_card.get("name")}


def keyword_relevance(question: str, case: dict[str, Any]) -> tuple[float, list[str]]:
    question_data = case["question"]
    terms = list(question_data.get("keywords", [])) + list(question_data.get("subtopics", []))
    normalized = compact(question)
    hits = [term for term in terms if compact(term) and compact(term) in normalized]
    hit_ratio = len(hits) / max(1, min(5, len(terms)))
    pattern_score = similarity(question, question_data.get("normalizedPattern", ""))
    return min(1.0, 0.65 * hit_ratio + 0.35 * pattern_score), hits


def score_case(
    case: dict[str, Any],
    question: str,
    topics: set[str],
    query_cards: list[dict[str, str]],
    spread_id: str,
) -> tuple[float, list[str], dict[str, float]]:
    rationale: list[str] = []
    components: dict[str, float] = {}

    semantic, keyword_hits = keyword_relevance(question, case)
    components["问题语义"] = 24 * semantic
    if keyword_hits:
        rationale.append("问题词命中：" + "、".join(keyword_hits[:4]))

    case_cards = case.get("cards", [])
    matched_pairs = [
        (query_card, case_card)
        for query_card in query_cards
        for case_card in case_cards
        if card_matches(query_card, case_card)
    ]
    if query_cards:
        card_overlap = len({pair[0]["identity"] for pair in matched_pairs}) / len(query_cards)
        components["牌面重合"] = 22 * card_overlap
        if matched_pairs:
            rationale.append("牌面命中：" + "、".join(dict.fromkeys(pair[1]["name"] for pair in matched_pairs)))

        positioned = [pair for pair in matched_pairs if pair[0]["position"]]
        position_match = sum(pair[0]["position"] == pair[1].get("position") for pair in positioned)
        components["位次一致"] = 14 * (position_match / len(positioned) if positioned else 0.0)
        if positioned and position_match:
            rationale.append("位次一致")

        oriented = [pair for pair in matched_pairs if pair[0]["orientation"]]
        orientation_match = sum(pair[0]["orientation"] == pair[1].get("orientation") for pair in oriented)
        orientation_score = orientation_match / len(oriented) if oriented else 0.0
        reversal_pairs = [pair for pair in matched_pairs if pair[0]["reversalMode"]]
        if reversal_pairs:
            reversal_match = sum(pair[0]["reversalMode"] == pair[1].get("reversalMode") for pair in reversal_pairs)
            orientation_score = 0.7 * orientation_score + 0.3 * reversal_match / len(reversal_pairs)
        components["朝向机制"] = 10 * orientation_score
        if oriented and orientation_match:
            rationale.append("朝向一致")
    else:
        components["牌面重合"] = 0.0
        components["位次一致"] = 0.0
        components["朝向机制"] = 0.0

    case_topic = case["question"].get("topic")
    topic_match = 1.0 if case_topic in topics else 0.0
    components["主题一致"] = 10 * topic_match
    if topic_match:
        rationale.append(f"主题一致：{case_topic}")

    # 当前命令行不要求用户描述牌间关系；多牌完全命中时，以案例自己的关系结构提供弱加分。
    relation_score = 1.0 if len(matched_pairs) >= 2 and case.get("relations") else 0.0
    components["关系模式"] = 8 * relation_score
    if relation_score:
        rationale.append("多牌关系可参考：" + "、".join(case["relations"]))

    spread_match = 1.0 if spread_id and spread_id == case.get("spreadId") else 0.0
    components["牌阵一致"] = 5 * spread_match
    if spread_match:
        rationale.append("牌阵一致")

    quality = case.get("quality", {})
    specificity = float(quality.get("specificity", 0.0))
    barnum_risk = float(quality.get("barnumRisk", 1.0))
    quality_score = max(0.0, min(1.0, (specificity + (1 - barnum_risk)) / 2))
    components["内容质量"] = 7 * quality_score

    # 没有传牌面时，把问题语义与主题分扩展到百分制，避免仅因输入信息较少使分数难读。
    raw_score = sum(components.values())
    available_weight = 41.0 + (5.0 if spread_id else 0.0)
    if query_cards:
        available_weight += 22.0
        if any(card["position"] for card in query_cards):
            available_weight += 14.0
        if any(card["orientation"] for card in query_cards):
            available_weight += 10.0
        if len(query_cards) >= 2:
            available_weight += 8.0
    score = min(100.0, 100 * raw_score / max(1.0, available_weight))
    return score, rationale, components


def rank_cases(
    question: str,
    topic: str = "",
    cards: Iterable[dict[str, str]] = (),
    spread_id: str = "",
    top_k: int = 3,
) -> dict[str, Any]:
    corpus = load_corpus()
    query_cards = list(cards)
    topics = infer_topics(question, topic)
    eligible = [
        case
        for case in corpus["cases"]
        if case.get("quality", {}).get("reviewStatus") in ALLOWED_REVIEW_STATUS
        and case.get("source", {}).get("license") == "内部使用"
    ]
    ranked = []
    for case in eligible:
        score, rationale, components = score_case(case, question, topics, query_cards, spread_id)
        ranked.append(
            {
                "caseId": case["caseId"],
                "score": round(score, 2),
                "rationale": rationale or ["仅按内容质量进入回退候选"],
                "matchedComponents": {key: round(value, 2) for key, value in components.items() if value > 0},
                "case": case,
            }
        )
    ranked.sort(key=lambda item: (-item["score"], item["caseId"]))
    flags = detect_high_impact(question)
    return {
        "query": {
            "question": question,
            "topics": sorted(topics),
            "spreadId": spread_id,
            "cards": query_cards,
        },
        "policy": {
            "tradition": TRADITION_NAME,
            "contentVersion": CONTENT_VERSION,
            "eligibleCases": len(eligible),
            "highImpactFlags": flags,
            "notice": "案例仅供候选解释排序；高影响问题不得据此作预测或行动决定。" if flags else "案例仅供候选解释排序，不改变基础牌义。",
        },
        "results": ranked[: max(1, min(top_k, 8))],
    }


def compact_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Project ranked cases to the fields needed for interpretation.

    The full corpus metadata remains available through ``--full`` for auditing,
    while the normal Agent route avoids loading source and quality fields that
    have already been enforced by the deterministic eligibility filter.
    """
    results = []
    for item in payload["results"]:
        case = item["case"]
        results.append(
            {
                "caseId": item["caseId"],
                "score": item["score"],
                "rationale": item["rationale"],
                "topic": case["question"].get("topic", ""),
                "pattern": case["question"].get("normalizedPattern", ""),
                "cards": [
                    {
                        key: card[key]
                        for key in ("name", "orientation", "reversalMode", "position")
                        if card.get(key)
                    }
                    for card in case.get("cards", [])
                ],
                "candidateInterpretations": case.get("candidateInterpretations", []),
                "safeActions": case.get("safeActions", []),
                "safetyTags": case.get("safetyTags", []),
            }
        )
    return {"query": payload["query"], "policy": payload["policy"], "results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="检索中文塔罗情境案例")
    parser.add_argument("--question", required=True, help="用户原问题")
    parser.add_argument("--topic", default="", help="可选主题，例如事业、爱情、学业、财运")
    parser.add_argument("--spread", default="", help="可选稳定牌阵标识")
    parser.add_argument("--card", action="append", default=[], help="牌名或稳定标识|朝向|位次|逆位机制")
    parser.add_argument("--top-k", type=int, default=3, help="返回一至八条，默认三条")
    parser.add_argument("--full", action="store_true", help="审计时返回完整案例记录")
    args = parser.parse_args()
    cards = [parse_card(spec) for spec in args.card]
    payload = rank_cases(args.question, args.topic, cards, args.spread, args.top_k)
    if not args.full:
        payload = compact_payload(payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
