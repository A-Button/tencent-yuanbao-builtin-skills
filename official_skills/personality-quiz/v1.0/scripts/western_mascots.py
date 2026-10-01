"""Load the fixed twelve-sign Yuanbao assets; embed only a verified Sun sign."""

from __future__ import annotations

import base64
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

from western_profile import SIGNS, normalize_sign


ASSET_DIR = Path(__file__).resolve().parents[1] / "assets" / "yuanbao-zodiac"
MANIFEST_PATH = ASSET_DIR / "manifest.json"
SLUGS = ("aries", "taurus", "gemini", "cancer", "leo", "virgo", "libra", "scorpio", "sagittarius", "capricorn", "aquarius", "pisces")
SIGN_FILES = dict(zip(SIGNS, (f"{slug}.png" for slug in SLUGS)))


def load_manifest(path: Path = MANIFEST_PATH) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != "1.0.0"
        or manifest.get("asset_kind") != "yuanbao_zodiac_mascots"
        or manifest.get("mime_type") != "image/png"
        or manifest.get("background") != "transparent"
        or manifest.get("order") != list(SIGNS)
        or set(manifest.get("signs", {})) != set(SIGNS)
    ):
        raise ValueError("星座元宝清单必须完整覆盖十二星座。")
    for sign, entry in manifest["signs"].items():
        if not isinstance(entry, dict) or entry.get("file") != SIGN_FILES[sign]:
            raise ValueError("星座元宝文件与固定映射不符。")
    return manifest


def asset_for_sun(item: dict[str, Any], manifest_path: Path = MANIFEST_PATH) -> dict[str, Any] | None:
    """Never infer a mascot from candidate signs, other planets, or user labels."""
    sign = normalize_sign(item.get("sign"))
    if item.get("key") != "sun" or item.get("status") != "available" or sign is None:
        return None
    manifest = load_manifest(manifest_path)
    entry = manifest["signs"][sign]
    asset_dir = manifest_path.parent.resolve()
    path = (asset_dir / entry["file"]).resolve()
    if path.parent != asset_dir:
        raise ValueError("星座元宝资源必须位于随包目录。")
    raw = path.read_bytes()
    if len(raw) < 33 or raw[:8] != b"\x89PNG\r\n\x1a\n" or raw[12:16] != b"IHDR":
        raise ValueError("星座元宝资源不是有效的 PNG。")
    # Reviewed pixel transparency is pinned by the manifest hash below; require
    # an actual 8-bit RGBA PNG too, never an RGB image painted like transparency.
    if raw[24:26] != b"\x08\x06":
        raise ValueError("星座元宝资源必须是带透明通道的 RGBA PNG。")
    size = struct.unpack(">II", raw[16:24])
    if (
        hashlib.sha256(raw).hexdigest() != entry.get("sha256")
        or size != (entry.get("width"), entry.get("height"))
        or size[0] != size[1]
        or not 320 <= size[0] <= 2048
    ):
        raise ValueError("星座元宝资源哈希或尺寸不符。")
    return {
        "sign": sign,
        "src": "data:image/png;base64," + base64.b64encode(raw).decode("ascii"),
        "width": size[0], "height": size[1],
    }
