#!/usr/bin/env python3
"""Verify that a generated personality assessment is safe to hand to an interactive viewer."""

from __future__ import annotations

import argparse
import base64
import binascii
import json
import re
import sys
from pathlib import Path

from webp_validation import WebPValidationError, decode_webp_size


class VerifyError(ValueError):
    pass


EXPECTED_TYPE_CODES = {
    f"{energy}{information}{decision}{lifestyle}"
    for energy in "EI"
    for information in "NS"
    for decision in "TF"
    for lifestyle in "JP"
}
YUANBAO_PREFIX = "data:image/webp;base64,"
PROFILE_FIELDS = ("career", "emotion", "study", "talent")
PROFILE_FORBIDDEN_SUBJECT_TERMS = ("我", "本人", "被测者", "受测者", "命主", "用户", "该类型的人")


def verify_yuanbao_mascots(payload: dict[str, object]) -> None:
    mascots = payload.get("yuanbao_mascots")
    if not isinstance(mascots, dict) or set(mascots) != EXPECTED_TYPE_CODES:
        raise VerifyError("页面元宝角色资源不完整")
    for code, entry in mascots.items():
        if not isinstance(entry, dict):
            raise VerifyError(f"页面元宝角色条目无效：{code}")
        src = entry.get("src")
        alt = entry.get("alt")
        if (
            not isinstance(src, str)
            or not src.startswith(YUANBAO_PREFIX)
            or not isinstance(alt, str)
            or not alt.strip()
            or entry.get("width") != 320
            or entry.get("height") != 320
            or not isinstance(entry.get("visual_offset_y"), int)
            or not -80 <= entry["visual_offset_y"] <= 80
        ):
            raise VerifyError(f"页面元宝角色元数据无效：{code}")
        try:
            content = base64.b64decode(src[len(YUANBAO_PREFIX) :], validate=True)
        except (ValueError, binascii.Error) as exc:
            raise VerifyError(f"页面元宝角色编码无效：{code}") from exc
        try:
            decoded_size = decode_webp_size(content)
        except WebPValidationError as exc:
            raise VerifyError(f"页面元宝角色图片无效：{code}") from exc
        if decoded_size != (320, 320):
            raise VerifyError(f"页面元宝角色尺寸无效：{code}")


def verify_type_profiles(payload: dict[str, object]) -> None:
    catalog = payload.get("type_profiles")
    if not isinstance(catalog, dict):
        raise VerifyError("页面类型场景档案无效")
    profiles = catalog.get("types")
    if (
        not isinstance(profiles, dict)
        or set(profiles) != EXPECTED_TYPE_CODES
    ):
        raise VerifyError("页面类型场景档案不完整")
    for code, profile in profiles.items():
        if not isinstance(profile, dict):
            raise VerifyError(f"页面类型场景条目无效：{code}")
        if any(
            not isinstance(profile.get(field), str)
            or not 24 <= len(profile[field].strip()) <= 220
            or not profile[field].strip().startswith("你")
            or any(term in profile[field] for term in PROFILE_FORBIDDEN_SUBJECT_TERMS)
            or "<" in profile[field]
            or ">" in profile[field]
            for field in PROFILE_FIELDS
        ):
            raise VerifyError(f"页面类型场景正文无效：{code}")
        representatives = profile.get("representatives")
        if not isinstance(representatives, list) or len(representatives) != 3:
            raise VerifyError(f"页面类型参考人物无效：{code}")
        names: set[str] = set()
        for entry in representatives:
            if not isinstance(entry, dict):
                raise VerifyError(f"页面类型参考人物信息无效：{code}")
            name = entry.get("name")
            role = entry.get("role")
            if (
                not isinstance(name, str)
                or not isinstance(role, str)
                or not 1 <= len(name.strip()) <= 80
                or not 2 <= len(role.strip()) <= 100
                or any(character in name or character in role for character in "<>")
                or name.strip() in names
            ):
                raise VerifyError(f"页面类型参考人物信息无效：{code}")
            names.add(name.strip())
        if len(names) != 3:
            raise VerifyError(f"页面类型参考人物信息无效：{code}")
def verify(path: Path) -> dict[str, object]:
    if path.suffix.lower() != ".html":
        raise VerifyError("只能交付已生成的 .html 文件")
    try:
        document = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise VerifyError("找不到待交付页面") from exc
    if len(document.encode("utf-8")) > 2_000_000:
        raise VerifyError("待交付页面异常过大")
    forbidden = (
        "{{DOCUMENT_TITLE}}",
        "{{BUILD_MARKER}}",
        "{{VERSION_CHIP}}",
        "{{DURATION_CHIP}}",
        "{{ASSESSMENT_PAYLOAD}}",
        "{{SCORING_CORE}}",
        "PERSR1.",
        'id="typeIdentity"',
        'id="welcomeScreen"',
        'id="startButton"',
        "返回说明",
        "16Personalities",
        "查看公开参考资料",
        "profile-source-link",
    )
    if any(token in document for token in forbidden):
        raise VerifyError("这是内部模板，不是可交付页面")
    required = (
        '<main class="app" data-assessment-build="ready">',
        'id="runtimeNotice"',
        'id="questionScreen" class="screen">',
        'startAssessment();\n      document.documentElement.dataset.assessmentReady = "true";\n      byId("runtimeNotice").hidden = true;',
        'id="resultTitle" tabindex="-1">你的人格</h1>',
        '<div id="typeCode" class="type-code"></div>\n          <p id="resultSummary" class="result-summary" hidden></p>',
        'id="resultMascots" class="result-mascots" role="group"',
        "result-mascot-visual",
        "asset.visual_offset_y / 3.2",
        'id="typeProfileSection" class="type-profile-section"',
        "事业发展",
        "情感婚恋",
        "学业考试",
        "天赋挖掘",
        "类型参考人物",
        "X表示你同时具有两种倾向",
        'id="typeProfileTitle" class="sr-only">你的人格类型表现</h2>',
        "renderTypeProfiles",
        "profileCodes.length > 2",
        "selectMascotTypeCodes",
        "selectedMascots.length <= 2",
        'dataset.assessmentReady = "true"',
        'Object.defineProperty(root, "PersonalityScoringV1"',
        '"PERSONALITY_RESULT_V1"',
    )
    if any(marker not in document for marker in required):
        raise VerifyError("页面缺少交互就绪标记，请重新生成")
    if document.count('id="questionScreen"') != 1:
        raise VerifyError("页面答题入口数量无效")
    if document.count("startAssessment();") != 2:
        raise VerifyError("页面答题启动流程无效")
    match = re.search(r"const DATA = (\{.*?\});\n\s+const \{ TRAITS \}", document, re.DOTALL)
    if not match:
        raise VerifyError("页面缺少测评数据")
    try:
        payload = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        raise VerifyError("页面测评数据无效") from exc
    version = payload.get("version_id")
    transfer_id = payload.get("transfer_id")
    item_count = payload.get("item_count")
    expected = {"quick": 20, "deep": 50}
    if version not in expected or item_count != expected[version]:
        raise VerifyError("页面版本与题数不一致")
    if payload.get("assessment_version") != "html-personality-15":
        raise VerifyError("页面人格测评版本无效")
    if transfer_id != {"quick": "mini_ipip_20_v1", "deep": "ipip_50_v1"}[version]:
        raise VerifyError("页面复制结果版本无效")
    items = payload.get("items")
    if not isinstance(items, list) or len(items) != item_count:
        raise VerifyError("页面题目不完整")
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("text"), str)
        or "你" not in item["text"]
        or "我" in item["text"]
        for item in items
    ):
        raise VerifyError("页面题目必须直接使用第二人称")
    verify_yuanbao_mascots(payload)
    verify_type_profiles(payload)
    return {"ok": True, "path": str(path.resolve()), "version": version, "items": item_count}


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a generated personality assessment HTML.")
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(verify(args.path), ensure_ascii=False))
        return 0
    except VerifyError as exc:
        print(
            json.dumps(
                {"ok": False, "error": "E_ASSESSMENT_DELIVERY", "message": str(exc)},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
