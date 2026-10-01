#!/usr/bin/env python3
"""User-scoped persistence for the job-hunting skill.

The host mounts ``/data/user`` per authenticated user.  This module deliberately
does not accept a user id: isolation comes from that mount, not from a model-
supplied field.

Commands:
    state_store.py paths
    state_store.py read
    state_store.py write --input-file FILE --expected-revision N
    state_store.py freeze-resume --source FILE [--normalized FILE]

``state.json`` is the business-fact ledger.  Resume bytes live beside it under
``materials/resumes``; only paths and structured findings belong in the ledger.
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 5
SUPPORTED_SCHEMA_VERSIONS = {4, 5}


class StoreError(RuntimeError):
    pass


class RevisionConflict(StoreError):
    pass


def data_dir() -> Path:
    """Return the host-provided, per-user persistent directory."""
    return Path(os.environ.get("JOB_HUNTING_DATA_DIR", "/data/user/job-hunting"))


def state_path() -> Path:
    return data_dir() / "state.json"


def backup_path() -> Path:
    return data_dir() / "state.json.bak"


def materials_dir() -> Path:
    return data_dir() / "materials"


def resumes_dir() -> Path:
    return materials_dir() / "resumes"


def now_iso() -> str:
    return datetime.now().astimezone().replace(microsecond=0).isoformat()


def empty_state() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "revision": 0,
        "updated_at": None,
        "thing_id": None,
        "task": {"intent": {}, "timeline": None, "created_at": None},
        "profile": {
            "active_resume_id": None,
            "resume_path": None,
            "diagnosis": None,
            "resume_versions": [],
        },
        "interviews": [],
    }


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StoreError(f"cannot read {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise StoreError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise StoreError(f"state root must be an object: {path}")
    return value


def _validate_state(state: dict[str, Any]) -> None:
    version = state.get("schema_version")
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise StoreError(f"unsupported schema_version: {version!r}")
    revision = state.get("revision")
    if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
        raise StoreError("revision must be a non-negative integer")
    for key in ("task", "profile"):
        if not isinstance(state.get(key), dict):
            raise StoreError(f"{key} must be an object")
    if not isinstance(state.get("interviews"), list):
        raise StoreError("interviews must be an array")
    versions = state["profile"].get("resume_versions", [])
    if not isinstance(versions, list):
        raise StoreError("profile.resume_versions must be an array")
    ids = [item.get("id") for item in versions if isinstance(item, dict)]
    if len(ids) != len(versions) or any(not isinstance(item, str) or not item for item in ids):
        raise StoreError("each resume version must have a non-empty string id")
    if len(set(ids)) != len(ids):
        raise StoreError("resume version ids must be unique")
    active_id = state["profile"].get("active_resume_id")
    if active_id is not None and active_id not in ids:
        raise StoreError("profile.active_resume_id must reference profile.resume_versions")
    if version == SCHEMA_VERSION:
        root = data_dir().resolve()
        for label, raw_path in (
            ("profile.resume_path", state["profile"].get("resume_path")),
            *(
                (f"profile.resume_versions[{index}].{field}", item.get(field))
                for index, item in enumerate(versions)
                for field in ("path", "source_path")
                if isinstance(item, dict)
            ),
        ):
            if raw_path is None:
                continue
            if not isinstance(raw_path, str) or not raw_path:
                raise StoreError(f"{label} must be a non-empty path or null")
            try:
                Path(raw_path).resolve().relative_to(root)
            except ValueError as exc:
                raise StoreError(f"{label} must stay under {root}") from exc


def load_state() -> dict[str, Any]:
    path = state_path()
    if not path.exists():
        return empty_state()
    try:
        state = _load_json(path)
        _validate_state(state)
        return state
    except StoreError as primary_error:
        backup = backup_path()
        if backup.exists():
            try:
                state = _load_json(backup)
                _validate_state(state)
                print(
                    json.dumps(
                        {"warning": str(primary_error), "recovered_from": str(backup)},
                        ensure_ascii=False,
                    ),
                    file=sys.stderr,
                )
                return state
            except StoreError:
                pass
        raise primary_error


def _atomic_write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.parent / f".{path.name}.{os.getpid()}.{secrets.token_hex(3)}.tmp"
    try:
        staging.write_bytes(payload)
        os.replace(staging, path)
    except OSError:
        staging.unlink(missing_ok=True)
        raise


def _atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = destination.parent / (
        f".{destination.name}.{os.getpid()}.{secrets.token_hex(3)}.tmp"
    )
    try:
        shutil.copyfile(source, staging)
        os.replace(staging, destination)
    except OSError:
        staging.unlink(missing_ok=True)
        raise


def save_state(candidate: dict[str, Any], expected_revision: int) -> dict[str, Any]:
    current = load_state()
    actual_revision = current["revision"]
    if actual_revision != expected_revision:
        raise RevisionConflict(
            f"revision conflict: expected {expected_revision}, current {actual_revision}"
        )

    updated = dict(candidate)
    updated["schema_version"] = SCHEMA_VERSION
    updated["revision"] = actual_revision + 1
    updated["updated_at"] = now_iso()
    updated.setdefault("thing_id", None)
    updated.setdefault("task", {"intent": {}, "timeline": None, "created_at": None})
    updated.setdefault(
        "profile",
        {
            "active_resume_id": None,
            "resume_path": None,
            "diagnosis": None,
            "resume_versions": [],
        },
    )
    updated["profile"].setdefault("active_resume_id", None)
    updated["profile"].setdefault("resume_path", None)
    updated["profile"].setdefault("diagnosis", None)
    updated["profile"].setdefault("resume_versions", [])
    updated.setdefault("interviews", [])
    _validate_state(updated)

    target = state_path()
    if target.exists():
        # Never replace a known-good backup with a corrupt primary recovered by
        # load_state().  Only validated primary bytes are eligible as backup.
        try:
            previous = _load_json(target)
            _validate_state(previous)
        except StoreError:
            previous = None
        if previous is not None:
            _atomic_copy(target, backup_path())
    payload = (json.dumps(updated, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    _atomic_write_bytes(target, payload)
    return updated


def freeze_resume(source: Path, normalized: Path | None = None) -> dict[str, Any]:
    if not source.is_file():
        raise StoreError(f"resume source does not exist: {source}")
    if normalized is not None and not normalized.is_file():
        raise StoreError(f"normalized resume does not exist: {normalized}")

    stamp = datetime.now().astimezone().strftime("%Y%m%d")
    resume_id = f"r_{stamp}_{secrets.token_hex(4)}"
    destination = resumes_dir() / resume_id
    suffix = source.suffix.lower() or ".bin"
    source_path = destination / f"source{suffix}"
    _atomic_copy(source, source_path)

    normalized_path: Path | None = None
    if normalized is not None:
        normalized_path = destination / "normalized.md"
        try:
            _atomic_copy(normalized, normalized_path)
        except OSError:
            source_path.unlink(missing_ok=True)
            raise

    return {
        "resume_id": resume_id,
        "source_path": str(source_path),
        "resume_path": str(normalized_path or source_path),
        "created_at": now_iso(),
    }


def _read_input(path: str) -> dict[str, Any]:
    if path == "-":
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise StoreError("input state must be an object")
        return value
    return _load_json(Path(path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("paths")
    subparsers.add_parser("read")

    write_parser = subparsers.add_parser("write")
    write_parser.add_argument("--input-file", required=True)
    write_parser.add_argument("--expected-revision", required=True, type=int)

    freeze_parser = subparsers.add_parser("freeze-resume")
    freeze_parser.add_argument("--source", required=True)
    freeze_parser.add_argument("--normalized")

    args = parser.parse_args()
    try:
        if args.command == "paths":
            result = {
                "data_dir": str(data_dir()),
                "state_path": str(state_path()),
                "materials_dir": str(materials_dir()),
            }
        elif args.command == "read":
            result = load_state()
        elif args.command == "write":
            result = save_state(_read_input(args.input_file), args.expected_revision)
        else:
            result = freeze_resume(
                Path(args.source), Path(args.normalized) if args.normalized else None
            )
    except RevisionConflict as exc:
        print(json.dumps({"error": "revision_conflict", "message": str(exc)}), file=sys.stderr)
        return 3
    except (StoreError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": "store_error", "message": str(exc)}), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
