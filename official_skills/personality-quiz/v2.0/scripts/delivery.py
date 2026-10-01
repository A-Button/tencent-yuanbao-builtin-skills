#!/usr/bin/env python3
"""Resolve where a finished page must be written so the host can deliver it.

The host only picks up artifacts that live in its sandbox workspace, and it
forbids writing anywhere else. A page left in the system temp directory is
built, verified and then unreachable, so every user-facing artifact resolves
its destination here instead of creating its own private directory.

Hosts without a workspace (local CLI, desktop clients that read absolute paths)
fall back to the private run directory, which is why callers still handle a
returned cleanup command.
"""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path


WORKSPACE_ENV = "AGENT_WORKSPACE"
DEFAULT_WORKSPACE = Path("/data/workspace")
# Delivered files are read by the host, not just by this process.
DELIVERED_MODE = 0o644
MAX_NAME_ATTEMPTS = 999
# Default attachment policy for other HTML artifacts; Tarot opts out explicitly.
HOST_ATTACH_MAX_BYTES = 2 * 1024 * 1024

DELIVERY_INSTRUCTION = (
    "先看 delivery.ok。为 true 时：写简短说明，把 media_info 原样贴到正文之后，"
    "再按 verify_command 用同一份回复草稿做交付校验，通过后才能发出。"
    "为 false 时只转述 delivery.message，不能说页面已经生成、已附上或让用户去打开。"
)


def resolve_workspace() -> Path | None:
    """Return the host workspace when this host has a usable one."""
    candidates: list[Path] = []
    override = os.environ.get(WORKSPACE_ENV, "").strip()
    if override:
        candidates.append(Path(override))
    candidates.append(DEFAULT_WORKSPACE)
    for candidate in candidates:
        try:
            expanded = candidate.expanduser()
            if expanded.is_dir() and os.access(expanded, os.W_OK):
                return expanded.resolve()
        except OSError:
            continue
    return None


def available_path(directory: Path, stem: str, suffix: str = ".html") -> Path:
    """Pick a free name so a second artifact never overwrites a delivered one."""
    for index in range(1, MAX_NAME_ATTEMPTS + 1):
        name = f"{stem}{suffix}" if index == 1 else f"{stem}-{index}{suffix}"
        candidate = directory / name
        if not candidate.exists() and not candidate.is_symlink():
            return candidate
    raise OSError(f"工作区里 {stem}{suffix} 的可用名称已耗尽")


def media_info_tag(path: str | Path, description: str) -> str:
    """Return the exact host tag the model must paste after the reply body."""
    payload = json.dumps(
        [{"type": "file", "description": description, "path": str(path)}],
        ensure_ascii=False,
        separators=(", ", ": "),
    )
    return f"<media_info>{payload}</media_info>"


def inspect_html_delivery(
    path: str | Path, description: str, *, max_bytes: int | None = HOST_ATTACH_MAX_BYTES
) -> dict[str, object]:
    """Check whether the host can actually attach this HTML in the chat."""
    target = Path(path)
    tag = media_info_tag(target, description)
    inspection: dict[str, object] = {
        "ok": False,
        "path": str(target),
        "description": description,
        "media_info": tag,
        "bytes": None,
        "max_bytes": max_bytes,
        "code": None,
        "message": None,
    }
    if target.is_symlink() or not target.is_file():
        inspection["code"] = "E_DELIVERY_MISSING"
        inspection["message"] = "工作区里没有可交付的 HTML 文件"
        return inspection
    size = target.stat().st_size
    inspection["bytes"] = size
    inspection["path"] = str(target.resolve())
    inspection["media_info"] = media_info_tag(target.resolve(), description)
    if target.suffix.lower() != ".html":
        inspection["code"] = "E_DELIVERY_TYPE"
        inspection["message"] = "交付文件必须是 .html"
        return inspection
    if size <= 0:
        inspection["code"] = "E_DELIVERY_EMPTY"
        inspection["message"] = "HTML 为空，不能交付"
        return inspection
    if max_bytes is not None and size > max_bytes:
        inspection["code"] = "E_HOST_SIZE_CAP"
        inspection["message"] = (
            f"产物 {size} 字节超过当前交付上限 {max_bytes} 字节，"
            "贴 media_info 也会被跳过，不能说页面已附上"
        )
        return inspection
    inspection["ok"] = True
    inspection["code"] = None
    inspection["message"] = (
        "文件可被宿主收取。必须把 media_info 原样贴进回复，并用 verify_command 校验草稿后再发出。"
    )
    return inspection


def reply_contains_media_info(reply: str, media_info: str) -> bool:
    """True only when the exact host tag appears in the outgoing reply."""
    return bool(media_info) and media_info in (reply or "")


def attach_delivery(
    result: dict[str, object],
    html_path: str | Path,
    description: str,
    *,
    success_action: str,
    max_bytes: int | None = HOST_ATTACH_MAX_BYTES,
) -> dict[str, object]:
    """Annotate a pipeline result with a host-attachable delivery gate."""
    inspection = inspect_html_delivery(html_path, description, max_bytes=max_bytes)
    quoted_html = shlex.quote(str(inspection["path"]))
    result["media_info"] = inspection["media_info"]
    result["delivery"] = inspection
    result["verify_command"] = (
        "python3 scripts/verify_html_delivery.py --html "
        + quoted_html
        + " --description "
        + shlex.quote(description)
        + (" --no-size-cap" if max_bytes is None else "")
        + " --reply-file <本轮回复草稿>"
    )
    if inspection["ok"]:
        result["next_action"] = success_action
        result["delivery_instruction"] = DELIVERY_INSTRUCTION
    else:
        result["next_action"] = "delivery_blocked"
        result["delivery_instruction"] = (
            "delivery.ok 为 false，不能说页面已生成或已附上。"
            + str(inspection["message"])
        )
    return result


def publish_exclusive(source: Path, target: Path) -> Path:
    """Byte-copy a finished artifact onto an unused path.

    Sandbox workspaces are often virtiofs, which does not implement hard links.
    Exclusive create plus a regular write is the host-safe publish, same as the
    pdf skill writing into the working directory.
    """
    payload = source.read_bytes()
    created = False
    try:
        with target.open("xb") as handle:
            created = True
            handle.write(payload)
        os.chmod(target, DELIVERED_MODE)
    except FileExistsError:
        raise
    except Exception:
        if created:
            try:
                target.unlink()
            except OSError:
                pass
        raise
    return target


def publish(source: Path, directory: Path, stem: str, suffix: str = ".html") -> Path:
    """Copy a finished artifact into the workspace under a readable name and mode."""
    for index in range(1, MAX_NAME_ATTEMPTS + 1):
        name = f"{stem}{suffix}" if index == 1 else f"{stem}-{index}{suffix}"
        target = directory / name
        try:
            return publish_exclusive(source, target)
        except FileExistsError:
            continue
    raise OSError(f"工作区里 {stem}{suffix} 的可用名称已耗尽")
