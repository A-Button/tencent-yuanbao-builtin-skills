#!/usr/bin/env python3
"""Gate HTML delivery: the file must be attachable and the reply must paste media_info."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import delivery


def load_reply(args: argparse.Namespace) -> str | None:
    if args.reply is not None and args.reply_file is not None:
        raise ValueError("--reply 与 --reply-file 不能同时使用")
    if args.reply is not None:
        return args.reply
    if args.reply_file is not None:
        return Path(args.reply_file).read_text(encoding="utf-8")
    return None


def verify(
    html: Path, description: str, reply: str | None,
    max_bytes: int | None = delivery.HOST_ATTACH_MAX_BYTES,
) -> dict[str, object]:
    inspection = delivery.inspect_html_delivery(html, description, max_bytes=max_bytes)
    payload: dict[str, object] = {
        "ok": False,
        "delivery": inspection,
        "media_info": inspection["media_info"],
        "reply_ok": None,
        "message": inspection["message"],
    }
    if not inspection["ok"]:
        payload["error"] = inspection["code"]
        return payload
    if reply is None:
        payload["ok"] = True
        payload["message"] = (
            "文件可交付。把 media_info 贴进回复草稿后，再带 --reply-file 跑一次本命令。"
        )
        return payload
    reply_ok = delivery.reply_contains_media_info(reply, str(inspection["media_info"]))
    payload["reply_ok"] = reply_ok
    if not reply_ok:
        payload["error"] = "E_DELIVERY_TAG_MISSING"
        payload["message"] = (
            "回复草稿里没有原样粘贴 media_info。没有这个标签宿主不会附上 HTML，"
            "不能说页面已生成或已附上。"
        )
        return payload
    payload["ok"] = True
    payload["message"] = "交付校验通过，可以把同一份草稿作为回复发出。"
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify an HTML artifact can be attached, and optionally that a reply pastes media_info."
    )
    parser.add_argument("--html", required=True, type=Path)
    parser.add_argument("--description", default="可打开的页面")
    parser.add_argument("--reply")
    parser.add_argument("--reply-file", type=Path)
    parser.add_argument("--no-size-cap", action="store_true", help="Use only for artifacts whose policy has no 2 MiB cap")
    args = parser.parse_args()
    try:
        reply = load_reply(args)
        payload = verify(
            args.html, args.description, reply,
            max_bytes=None if args.no_size_cap else delivery.HOST_ATTACH_MAX_BYTES,
        )
    except (OSError, ValueError) as exc:
        payload = {
            "ok": False,
            "error": "E_DELIVERY_VERIFY",
            "message": str(exc),
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload.get("ok") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
