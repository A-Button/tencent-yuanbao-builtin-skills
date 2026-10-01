"""Reused, bounded data validation helpers from the online skill; no UI or delivery logic."""
from __future__ import annotations
import base64, hashlib, json, os, tempfile
from pathlib import Path
from typing import Any
from webp_validation import WebPValidationError, decode_webp_size
TRAITS = ("extraversion", "agreeableness", "conscientiousness", "neuroticism", "imagination")
EXPECTED_TYPE_CODES={a+b+c+d for a in "EI" for b in "NS" for c in "TF" for d in "JP"}
class BuildError(ValueError):
    pass

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
