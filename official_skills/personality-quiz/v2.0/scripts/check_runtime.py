#!/usr/bin/env python3
"""Maintenance preflight: python3 scripts/check_runtime.py (does not install anything)."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def check_runtime() -> dict:
    checks = []

    def probe(name, action):
        try:
            detail = action()
            checks.append({"name": name, "ok": True, "detail": detail})
        except Exception as exc:
            checks.append({"name": name, "ok": False, "error": str(exc)})

    def python_version():
        if sys.version_info < (3, 9):
            raise RuntimeError("需要 Python 3.9 或更高版本")
        return sys.version.split()[0]

    def pillow_webp():
        from PIL import Image, __version__, features
        if not features.check("webp"):
            raise RuntimeError("Pillow 需要 WebP 解码支持")
        sample = Path(__file__).resolve().parents[1] / "assets/report-art/enfj.png"
        with Image.open(sample) as image:
            if image.format != "PNG" or image.size != (435, 414):
                raise RuntimeError("随包人格报告人物图格式或尺寸不匹配")
            image.load()
        return {"version": __version__, "webp": True, "report_art_png": True}

    def timezones():
        from zoneinfo import ZoneInfo
        zones = ("Asia/Shanghai", "America/New_York", "Europe/London")
        for name in zones:
            ZoneInfo(name)
        return list(zones)

    def engines():
        from vendor.lunar_python import Solar
        from vendor.astronomy import Time
        Solar.fromYmd(2000, 1, 1).getLunar()
        Time.Make(2000, 1, 1, 12, 0, 0)
        return ["lunar_python", "astronomy"]

    probe("python", python_version)
    probe("pillow_webp", pillow_webp)
    probe("iana_timezones", timezones)
    probe("bundled_engines", engines)
    probe("chart_followup_lock", lambda: __import__("fcntl").__name__)
    return {"ok": all(check["ok"] for check in checks), "checks": checks}


if __name__ == "__main__":
    result = check_runtime()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
