#!/usr/bin/env python3
"""Build a self-contained, offline personality assessment HTML file."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from webp_validation import WebPValidationError, decode_webp_size


ROOT = Path(__file__).resolve().parents[1]
ASSET_PATH = ROOT / "assets" / "personality-assessment-shell.template"
SCORING_CORE_PATH = ROOT / "assets" / "personality-scoring-core.js"
TYPE_LABEL_PATH = ROOT / "scripts" / "mbti_type_labels.json"
TYPE_PROFILE_PATH = ROOT / "scripts" / "mbti_type_profiles.json"
YUANBAO_ASSET_DIR = ROOT / "assets" / "yuanbao-personalities"
YUANBAO_MANIFEST_PATH = YUANBAO_ASSET_DIR / "manifest.json"
PAYLOAD_TOKEN = "/*{{ASSESSMENT_PAYLOAD}}*/ null"
SCORING_CORE_TOKEN = "/*{{SCORING_CORE}}*/"
INSTRUMENTS = {
    "quick": {
        "version_id": "quick",
        "transfer_id": "mini_ipip_20_v1",
        "id": "mini_ipip_20",
        "bank": ROOT / "scripts" / "mini_ipip_items.json",
        "expected_name": "Mini-IPIP-20",
        "expected_version": "donnellan-2006",
        "items": 20,
        "items_per_trait": 4,
        "duration": "约4分钟",
    },
    "deep": {
        "version_id": "deep",
        "transfer_id": "ipip_50_v1",
        "id": "ipip_big_five_50",
        "bank": ROOT / "scripts" / "ipip_big_five_50_items.json",
        "expected_name": "IPIP-50-Big-Five-Factor-Markers",
        "expected_version": "goldberg-1992-ipip-50",
        "items": 50,
        "items_per_trait": 10,
        "duration": "约8—10分钟",
    },
}
TRAITS = (
    "extraversion",
    "agreeableness",
    "conscientiousness",
    "neuroticism",
    "imagination",
)
EXPECTED_TYPE_CODES = {
    f"{energy}{information}{decision}{lifestyle}"
    for energy in "EI"
    for information in "NS"
    for decision in "TF"
    for lifestyle in "JP"
}
PROFILE_FIELDS = ("career", "emotion", "study", "talent")
PROFILE_FORBIDDEN_SUBJECT_TERMS = ("我", "本人", "被测者", "受测者", "命主", "用户", "该类型的人")


class BuildError(ValueError):
    pass


def reject_duplicate_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BuildError(f"类型场景档案包含重复字段：{key}")
        result[key] = value
    return result


def load_bank(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BuildError(f"找不到题库：{path}") from exc
    except json.JSONDecodeError as exc:
        raise BuildError(f"题库 JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列") from exc
    if not isinstance(payload, dict):
        raise BuildError("题库顶层必须是对象")
    return payload


def load_type_labels(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BuildError(f"找不到类型称呼表：{path}") from exc
    except json.JSONDecodeError as exc:
        raise BuildError(f"类型称呼表 JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列") from exc
    labels = payload.get("types") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "1.0.0"
        or payload.get("label_kind") != "popular_nonofficial_zh_cn"
        or not isinstance(labels, dict)
        or set(labels) != EXPECTED_TYPE_CODES
        or any(not isinstance(value, str) or not value.strip() for value in labels.values())
    ):
        raise BuildError("类型称呼表必须完整包含 16 个四字母类型")
    return {code: labels[code].strip() for code in sorted(labels)}


def load_type_profiles(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_json_object,
        )
    except FileNotFoundError as exc:
        raise BuildError(f"找不到类型场景档案：{path}") from exc
    except json.JSONDecodeError as exc:
        raise BuildError(f"类型场景档案 JSON 解析失败：第 {exc.lineno} 行第 {exc.colno} 列") from exc
    profiles = payload.get("types") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "2.0.0"
        or payload.get("content_kind") != "direct_second_person_type_context_zh_cn"
        or not isinstance(profiles, dict)
        or set(profiles) != EXPECTED_TYPE_CODES
    ):
        raise BuildError("类型场景档案必须完整包含 16 个四字母类型")

    normalized: dict[str, dict[str, Any]] = {}
    for code in sorted(profiles):
        entry = profiles[code]
        if not isinstance(entry, dict):
            raise BuildError(f"类型场景条目无效：{code}")
        topics: dict[str, str] = {}
        for field in PROFILE_FIELDS:
            value = entry.get(field)
            if (
                not isinstance(value, str)
                or not 24 <= len(value.strip()) <= 220
                or not value.strip().startswith("你")
                or any(term in value for term in PROFILE_FORBIDDEN_SUBJECT_TERMS)
                or "<" in value
                or ">" in value
            ):
                raise BuildError(f"类型场景正文无效：{code}.{field}")
            topics[field] = value.strip()
        representatives = entry.get("representatives")
        if not isinstance(representatives, list) or len(representatives) != 3:
            raise BuildError(f"类型参考人物必须恰好为 3 位：{code}")
        normalized_representatives: list[dict[str, str]] = []
        names: set[str] = set()
        for representative in representatives:
            if not isinstance(representative, dict):
                raise BuildError(f"类型参考人物条目无效：{code}")
            name = representative.get("name")
            role = representative.get("role")
            if (
                not isinstance(name, str)
                or not isinstance(role, str)
                or not 1 <= len(name.strip()) <= 80
                or not 2 <= len(role.strip()) <= 100
                or any(character in name or character in role for character in "<>")
                or name.strip() in names
            ):
                raise BuildError(f"类型参考人物信息无效：{code}")
            names.add(name.strip())
            normalized_representatives.append({"name": name.strip(), "role": role.strip()})
        normalized[code] = {
            **topics,
            "representatives": normalized_representatives,
        }
    return {"types": normalized}


def load_yuanbao_mascots(
    manifest_path: Path,
    asset_dir: Path,
    type_labels: dict[str, str],
) -> dict[str, dict[str, Any]]:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BuildError(f"找不到元宝角色清单：{manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise BuildError(f"元宝角色清单解析失败：第 {exc.lineno} 行第 {exc.colno} 列") from exc

    assets = manifest.get("types") if isinstance(manifest, dict) else None
    order = manifest.get("order") if isinstance(manifest, dict) else None
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != "1.1.0"
        or manifest.get("asset_kind") != "yuanbao_personality_mascots"
        or manifest.get("mime_type") != "image/webp"
        or not isinstance(assets, dict)
        or set(assets) != EXPECTED_TYPE_CODES
        or not isinstance(order, list)
        or len(order) != 16
        or set(order) != EXPECTED_TYPE_CODES
    ):
        raise BuildError("元宝角色清单必须完整包含 16 个四字母类型")

    embedded: dict[str, dict[str, Any]] = {}
    for code in order:
        entry = assets.get(code)
        if not isinstance(entry, dict):
            raise BuildError(f"元宝角色条目无效：{code}")
        filename = entry.get("file")
        alt = entry.get("alt")
        expected_alt = f"{code} {type_labels[code]}对应的元宝形象"
        if (
            not isinstance(filename, str)
            or not filename
            or Path(filename).name != filename
            or not filename.endswith(".webp")
            or alt != expected_alt
            or entry.get("width") != 320
            or entry.get("height") != 320
            or not isinstance(entry.get("visual_offset_y"), int)
            or not -80 <= entry["visual_offset_y"] <= 80
        ):
            raise BuildError(f"元宝角色元数据无效：{code}")
        path = asset_dir / filename
        if path.is_symlink() or not path.is_file():
            raise BuildError(f"元宝角色文件无效：{path}")
        content = path.read_bytes()
        digest = hashlib.sha256(content).hexdigest()
        try:
            decoded_size = decode_webp_size(content)
        except WebPValidationError as exc:
            raise BuildError(f"元宝角色文件无法解码：{code}") from exc
        if entry.get("sha256") != digest or decoded_size != (320, 320):
            raise BuildError(f"元宝角色文件校验失败：{code}")
        embedded[code] = {
            "src": f"data:image/webp;base64,{base64.b64encode(content).decode('ascii')}",
            "alt": alt,
            "width": 320,
            "height": 320,
            "visual_offset_y": entry["visual_offset_y"],
        }
    return embedded


def validate_bank(bank: dict[str, Any], config: dict[str, Any]) -> None:
    instrument = bank.get("instrument")
    items = bank.get("items")
    scale = bank.get("response_scale")
    if not isinstance(instrument, dict) or not isinstance(items, list):
        raise BuildError("题库缺少 instrument 或 items")
    if instrument.get("name") != config["expected_name"] or instrument.get("version") != config["expected_version"]:
        raise BuildError("题库名称或版本与所选测评不一致")
    if len(items) != config["items"]:
        raise BuildError(f"题库题数必须为 {config['items']}")
    if [item.get("id") for item in items if isinstance(item, dict)] != list(
        range(1, config["items"] + 1)
    ):
        raise BuildError("题库 id 必须从 1 连续递增")
    trait_counts = {trait: 0 for trait in TRAITS}
    for item in items:
        if not isinstance(item, dict):
            raise BuildError("题库题目必须是对象")
        trait = item.get("trait")
        if trait not in trait_counts:
            raise BuildError(f"未知人格维度：{trait}")
        if not isinstance(item.get("reverse"), bool):
            raise BuildError(f"题目 {item.get('id')} 缺少有效 reverse")
        if not isinstance(item.get("zh_cn_draft"), str) or not item["zh_cn_draft"].strip():
            raise BuildError(f"题目 {item.get('id')} 缺少中文文本")
        if "你" not in item["zh_cn_draft"] or "我" in item["zh_cn_draft"]:
            raise BuildError(f"题目 {item.get('id')} 必须直接使用第二人称")
        trait_counts[trait] += 1
    if any(count != config["items_per_trait"] for count in trait_counts.values()):
        raise BuildError("五项人格维度的题目数量不平衡")
    if not isinstance(scale, dict) or not isinstance(scale.get("zh-CN"), dict):
        raise BuildError("题库缺少中文作答量尺")
    zh_scale = scale["zh-CN"]
    if set(zh_scale) != {"1", "2", "3", "4", "5"} or any(
        not isinstance(zh_scale[key], str) or not zh_scale[key].strip()
        for key in ("1", "2", "3", "4", "5")
    ):
        raise BuildError("中文作答量尺必须恰好包含1—5的非空标签")
    if instrument.get("license_status") != "public-domain":
        raise BuildError("当前 HTML 只允许公有领域题库")


def build_payload(
    bank: dict[str, Any],
    config: dict[str, Any],
    type_labels: dict[str, str],
    type_profiles: dict[str, Any],
    yuanbao_mascots: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "1.0.0",
        "assessment_version": "html-personality-15",
        "version_id": config["version_id"],
        "transfer_id": config["transfer_id"],
        "item_count": config["items"],
        "items_per_trait": config["items_per_trait"],
        "duration": config["duration"],
        "response_scale": bank["response_scale"]["zh-CN"],
        "type_labels": type_labels,
        "type_profiles": type_profiles,
        "yuanbao_mascots": yuanbao_mascots,
        "items": [
            {
                "id": item["id"],
                "trait": item["trait"],
                "reverse": item["reverse"],
                "text": item["zh_cn_draft"],
            }
            for item in bank["items"]
        ],
    }


def safe_script_json(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return encoded.replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def atomic_write(path: Path, content: str) -> None:
    if path.exists():
        raise BuildError(f"输出文件已存在：{path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_document(document: str) -> None:
    forbidden = (
        "{{DOCUMENT_TITLE}}",
        "{{BUILD_MARKER}}",
        "{{VERSION_CHIP}}",
        "{{DURATION_CHIP}}",
        SCORING_CORE_TOKEN,
        PAYLOAD_TOKEN,
        'id="typeIdentity"',
        'id="welcomeScreen"',
        'id="startButton"',
        "返回说明",
        "16Personalities",
        "查看公开参考资料",
        "profile-source-link",
    )
    if any(token in document for token in forbidden):
        raise BuildError("生成页面仍包含内部模板标记")
    required = (
        'data-assessment-build="ready"',
        'Object.defineProperty(root, "PersonalityScoringV1"',
        '"PERSONALITY_RESULT_V1"',
        "const DATA = {",
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
        "data:image/webp;base64,",
        'dataset.assessmentReady = "true"',
    )
    if any(marker not in document for marker in required):
        raise BuildError("生成页面缺少交互就绪标记")
    if document.count('id="questionScreen"') != 1:
        raise BuildError("生成页面必须恰好包含一个答题入口")
    if document.count("startAssessment();") != 2:
        raise BuildError("生成页面必须包含初始化与重新测试两处答题启动调用")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a self-contained personality assessment HTML.")
    parser.add_argument(
        "--version",
        choices=tuple(INSTRUMENTS),
        default="quick",
        help="quick=20题轻量版；deep=50题深度版",
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        config = INSTRUMENTS[args.version]
        bank_path = config["bank"]
        bank = load_bank(bank_path)
        validate_bank(bank, config)
        type_labels = load_type_labels(TYPE_LABEL_PATH)
        type_profiles = load_type_profiles(TYPE_PROFILE_PATH)
        yuanbao_mascots = load_yuanbao_mascots(
            YUANBAO_MANIFEST_PATH,
            YUANBAO_ASSET_DIR,
            type_labels,
        )
        payload = build_payload(bank, config, type_labels, type_profiles, yuanbao_mascots)
        template = ASSET_PATH.read_text(encoding="utf-8")
        if template.count(PAYLOAD_TOKEN) != 1:
            raise BuildError("HTML 模板必须恰好包含一个 ASSESSMENT_PAYLOAD 占位符")
        if template.count(SCORING_CORE_TOKEN) != 1:
            raise BuildError("HTML 模板必须恰好包含一个 SCORING_CORE 占位符")
        scoring_core = SCORING_CORE_PATH.read_text(encoding="utf-8")
        if not scoring_core.strip() or SCORING_CORE_TOKEN in scoring_core:
            raise BuildError("人格计分核心无效")
        replacements = {
            "{{DOCUMENT_TITLE}}": "MBTI 性格测试",
            "{{BUILD_MARKER}}": "ready",
            SCORING_CORE_TOKEN: scoring_core,
            PAYLOAD_TOKEN: safe_script_json(payload),
        }
        document = template
        for token, value in replacements.items():
            if document.count(token) != 1:
                raise BuildError(f"HTML 模板标记数量无效：{token}")
            document = document.replace(token, value)
        validate_document(document)
        atomic_write(args.output, document)
        print(
            json.dumps(
                {
                    "ok": True,
                    "output": str(args.output),
                    "version": args.version,
                    "items": config["items"],
                    "offline": True,
                },
                ensure_ascii=False,
            )
        )
        return 0
    except Exception as exc:
        print(
            json.dumps(
                {"ok": False, "error": "E_PERSONALITY_ASSESSMENT_HTML", "message": str(exc)},
                ensure_ascii=False,
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
