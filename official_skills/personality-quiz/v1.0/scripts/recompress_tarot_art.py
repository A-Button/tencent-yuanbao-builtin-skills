#!/usr/bin/env python3
"""Recompress inlined Tarot WebP art so the shell fits the host 2MiB attach cap.

Run against the original full-resolution tarot-draw-shell.html. Re-running on an
already-shrunk file will decode the lossy images and encode them again.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image

from delivery import HOST_ATTACH_MAX_BYTES


ROOT = Path(__file__).resolve().parents[1]
ASSET_PATH = ROOT / "assets" / "tarot-draw-shell.html"
ART_PATTERN = re.compile(
    r"(window\.__TAROT_ART__\s*=\s*)(\{.*?\})(;\s*</script>)",
    re.DOTALL,
)
DATA_URL_PREFIX = "data:image/webp;base64,"
DEFAULT_MAX_SIDE = 360
DEFAULT_QUALITY = 60


class RecompressError(ValueError):
    pass


def decode_data_url(src: str) -> bytes:
    if not isinstance(src, str) or not src.startswith(DATA_URL_PREFIX):
        raise RecompressError("牌图不是内联 WebP data URL")
    try:
        return base64.b64decode(src[len(DATA_URL_PREFIX) :], validate=True)
    except (ValueError, OSError) as exc:
        raise RecompressError("牌图 data URL 无法解码") from exc


def recompress_webp(payload: bytes, max_side: int, quality: int) -> bytes:
    with Image.open(BytesIO(payload)) as image:
        rgb = image.convert("RGB")
        width, height = rgb.size
        longest = max(width, height)
        if longest > max_side:
            scale = max_side / longest
            rgb = rgb.resize(
                (max(1, round(width * scale)), max(1, round(height * scale))),
                Image.Resampling.LANCZOS,
            )
        buffer = BytesIO()
        rgb.save(buffer, format="WEBP", quality=quality, method=6)
        return buffer.getvalue()


def recompress_art(
    art: dict[str, object],
    max_side: int,
    quality: int,
) -> tuple[dict[str, object], dict[str, int]]:
    if len(art) != 78:
        raise RecompressError(f"牌图数量不是 78：{len(art)}")
    rebuilt: dict[str, object] = {}
    binary_sizes: list[int] = []
    for key, entry in art.items():
        if not isinstance(entry, dict) or not isinstance(entry.get("src"), str):
            raise RecompressError(f"牌图条目无效：{key}")
        compressed = recompress_webp(decode_data_url(entry["src"]), max_side, quality)
        binary_sizes.append(len(compressed))
        rebuilt[key] = {
            **entry,
            "src": DATA_URL_PREFIX + base64.b64encode(compressed).decode("ascii"),
        }
    stats = {
        "cards": 78,
        "binary_sum": sum(binary_sizes),
        "binary_min": min(binary_sizes),
        "binary_avg": sum(binary_sizes) // 78,
        "binary_max": max(binary_sizes),
    }
    return rebuilt, stats


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(content)
        os.replace(temporary, path)
        os.chmod(path, 0o644)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def transform(document: str, max_side: int, quality: int) -> tuple[str, dict[str, int]]:
    match = ART_PATTERN.search(document)
    if not match or document.count("window.__TAROT_ART__ =") != 1:
        raise RecompressError("找不到唯一的 __TAROT_ART__ 块")
    try:
        art = json.loads(match.group(2))
    except json.JSONDecodeError as exc:
        raise RecompressError("__TAROT_ART__ 不是合法 JSON") from exc
    if not isinstance(art, dict):
        raise RecompressError("__TAROT_ART__ 必须是对象")
    rebuilt, stats = recompress_art(art, max_side, quality)
    encoded = json.dumps(rebuilt, ensure_ascii=True, separators=(",", ":"))
    updated = document[: match.start(2)] + encoded + document[match.end(2) :]
    stats["html_bytes"] = len(updated.encode("utf-8"))
    stats["host_cap"] = HOST_ATTACH_MAX_BYTES
    return updated, stats


def main() -> int:
    parser = argparse.ArgumentParser(description="Recompress inlined Tarot WebP art.")
    parser.add_argument("--input", type=Path, default=ASSET_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--max-side", type=int, default=DEFAULT_MAX_SIDE)
    parser.add_argument("--quality", type=int, default=DEFAULT_QUALITY)
    args = parser.parse_args()
    if args.max_side < 64 or args.quality < 1 or args.quality > 100:
        raise RecompressError("max-side / quality 超出可用范围")
    document = args.input.read_text(encoding="utf-8")
    updated, stats = transform(document, args.max_side, args.quality)
    if stats["html_bytes"] > HOST_ATTACH_MAX_BYTES:
        raise RecompressError(
            f"压缩后仍有 {stats['html_bytes']} 字节，超过宿主上限 {HOST_ATTACH_MAX_BYTES}"
        )
    output = args.output or args.input
    atomic_write(output, updated)
    print(json.dumps({"ok": True, "output": str(output), **stats}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
