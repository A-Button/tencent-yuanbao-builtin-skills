#!/usr/bin/env python3
"""Validate one selected candidate and build client-only data. No I/O or publication."""

from __future__ import annotations

import json
import re
import sys
from urllib.parse import urlsplit, urlunsplit


class InvalidCandidate(ValueError):
    pass


def build_card_data(raw: dict) -> dict:
    if not isinstance(raw, dict) or set(raw) != {"basic_info"}:
        raise InvalidCandidate("invalid_fields")
    basic = raw["basic_info"]
    if not isinstance(basic, dict) or not {"username", "nickname"} <= set(basic):
        raise InvalidCandidate("missing_identity")
    if set(basic) - {"username", "nickname", "head_img_url"}:
        raise InvalidCandidate("invalid_fields")
    username, name = basic["username"], basic["nickname"]
    if not isinstance(username, str) or not re.fullmatch(r"gh_[A-Za-z0-9_]{1,64}", username):
        raise InvalidCandidate("invalid_username")
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name) > 100
        or any(ord(c) < 32 or ord(c) == 127 for c in name)
    ):
        raise InvalidCandidate("invalid_name")
    cover = basic.get("head_img_url", "")
    if not isinstance(cover, str):
        raise InvalidCandidate("invalid_icon")
    if cover:
        if len(cover) > 2048 or any(c.isspace() for c in cover):
            raise InvalidCandidate("invalid_icon")
        u = urlsplit(cover)
        if (
            u.scheme not in {"https", "http"}
            or u.netloc != "wx.qlogo.cn"
            or u.fragment
            or not u.path.startswith("/")
        ):
            raise InvalidCandidate("invalid_icon")
        cover = urlunsplit(("https", u.netloc, u.path, u.query, ""))
    return {"wxUserName": username, "wxPath": "", "name": name, "coverUrl": cover}


def _result(raw: dict) -> dict:
    try:
        card = build_card_data(raw)
    except InvalidCandidate as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": True, **card}


def main() -> int:
    raw_text = sys.argv[1] if len(sys.argv) > 1 else "{}"
    try:
        raw = json.loads(raw_text)
    except json.JSONDecodeError:
        print(
            json.dumps(
                {"ok": False, "error": "bad_json", "message": "入参必须是 JSON 对象"},
                ensure_ascii=False,
            )
        )
        return 2
    if not isinstance(raw, dict):
        print(
            json.dumps(
                {"ok": False, "error": "bad_json", "message": "入参必须是 JSON 对象"},
                ensure_ascii=False,
            )
        )
        return 2
    data = _result(raw)
    print(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    return 0 if data.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
