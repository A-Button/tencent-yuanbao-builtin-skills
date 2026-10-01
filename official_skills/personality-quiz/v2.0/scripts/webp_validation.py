"""Strict WebP decoding for build-time and delivery-time asset checks."""

from __future__ import annotations

from io import BytesIO


class WebPValidationError(ValueError):
    pass


def decode_webp_size(content: bytes) -> tuple[int, int]:
    """Decode a complete WebP payload and return its pixel dimensions."""

    if (
        not isinstance(content, bytes)
        or len(content) < 20
        or content[:4] != b"RIFF"
        or content[8:12] != b"WEBP"
        or int.from_bytes(content[4:8], "little") + 8 != len(content)
    ):
        raise WebPValidationError("WebP 容器不完整")

    try:
        from PIL import Image, UnidentifiedImageError
    except ImportError as exc:  # pragma: no cover - depends on the host runtime
        raise WebPValidationError("缺少用于校验 WebP 的 Pillow 运行库") from exc

    try:
        with Image.open(BytesIO(content)) as image:
            if image.format != "WEBP":
                raise WebPValidationError("图片格式不是 WebP")
            expected_size = image.size
            image.verify()
        with Image.open(BytesIO(content)) as image:
            if image.format != "WEBP" or image.size != expected_size:
                raise WebPValidationError("WebP 元数据不一致")
            image.load()
            return image.size
    except WebPValidationError:
        raise
    except (OSError, SyntaxError, UnidentifiedImageError, ValueError) as exc:
        raise WebPValidationError("WebP 无法完整解码") from exc
