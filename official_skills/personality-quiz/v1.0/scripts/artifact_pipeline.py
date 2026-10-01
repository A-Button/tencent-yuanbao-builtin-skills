#!/usr/bin/env python3
"""Build and verify one user-facing HTML artifact before publishing it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, Optional

import delivery


SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent

# Delivered artifacts are named for the user, not for the pipeline.
DELIVERY_STEMS = {
    "personality": "人格测评",
    "tarot": "塔罗牌桌",
    "share-card": "分享卡",
}
DELIVERY_DESCRIPTIONS = {
    "personality": "人格测评页，打开即可作答",
    "tarot": "塔罗牌桌，可直接洗牌抽牌",
    "share-card": "分享卡",
}


class ArtifactPipelineError(ValueError):
    def __init__(
        self,
        message: str,
        *,
        artifact: str,
        stage: str,
        details: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.artifact = artifact
        self.stage = stage
        self.details = details


def parse_child_output(result: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    raw = result.stdout.strip() or result.stderr.strip()
    if not raw:
        return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {"stdout": result.stdout.strip(), "stderr": result.stderr.strip()}
    return payload if isinstance(payload, dict) else {"result": payload}


def run_script(
    artifact: str,
    stage: str,
    script: str,
    *arguments: object,
) -> dict[str, Any]:
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / script), *(str(item) for item in arguments)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    payload = parse_child_output(result)
    if result.returncode != 0 or payload.get("ok") is not True:
        raise ArtifactPipelineError(
            f"{script} 未通过",
            artifact=artifact,
            stage=stage,
            details=payload,
        )
    return payload


def normalize_output(path: Path, *, artifact: str) -> Path:
    candidate = path.expanduser()
    if candidate.suffix.lower() != ".html":
        raise ArtifactPipelineError(
            "输出文件必须使用 .html 后缀",
            artifact=artifact,
            stage="prepare",
        )
    if candidate.is_symlink():
        raise ArtifactPipelineError(
            "拒绝把产物写入符号链接",
            artifact=artifact,
            stage="prepare",
        )
    candidate.parent.mkdir(parents=True, exist_ok=True)
    target = candidate.resolve()
    if target.exists() or target.is_symlink():
        raise ArtifactPipelineError(
            f"拒绝覆盖已有输出：{target}",
            artifact=artifact,
            stage="prepare",
        )
    return target


def publish_verified(staged: Path, target: Path, *, artifact: str) -> None:
    if not staged.is_file() or staged.is_symlink():
        raise ArtifactPipelineError(
            "校验器没有返回可发布的普通 HTML 文件",
            artifact=artifact,
            stage="publish",
        )
    try:
        # Exclusive copy, not a hard link: virtiofs workspaces raise ENOSYS on
        # os.link, which previously made the agent retry and patch the pipeline.
        delivery.publish_exclusive(staged, target)
    except FileExistsError as exc:
        raise ArtifactPipelineError(
            f"拒绝覆盖已有输出：{target}",
            artifact=artifact,
            stage="publish",
        ) from exc
    except OSError as exc:
        raise ArtifactPipelineError(
            f"已校验产物发布失败：{exc}",
            artifact=artifact,
            stage="publish",
        ) from exc


CommandFactory = Callable[[Path, Optional[Path]], Sequence[object]]


def build_verified_artifact(
    artifact: str,
    output: Path,
    build_command: CommandFactory,
    verify_command: CommandFactory,
    *,
    snapshot_input: Optional[Path] = None,
) -> dict[str, Any]:
    target = normalize_output(output, artifact=artifact)
    input_bytes: Optional[bytes] = None
    if snapshot_input is not None:
        source = snapshot_input.expanduser()
        if source.is_symlink() or not source.is_file():
            raise ArtifactPipelineError(
                f"输入不是可读取的普通文件：{source}",
                artifact=artifact,
                stage="prepare",
            )
        try:
            input_bytes = source.read_bytes()
        except OSError as exc:
            raise ArtifactPipelineError(
                f"无法读取输入：{source}",
                artifact=artifact,
                stage="prepare",
            ) from exc
    staging = Path(
        tempfile.mkdtemp(prefix=f".{target.name}.pipeline.", dir=target.parent)
    )
    os.chmod(staging, 0o700)
    staged_output = staging / target.name
    try:
        staged_input: Optional[Path] = None
        if input_bytes is not None:
            staged_input = staging / "input.json"
            with staged_input.open("xb") as handle:
                handle.write(input_bytes)
            os.chmod(staged_input, 0o600)

        build_args = tuple(build_command(staged_output, staged_input))
        if not build_args:
            raise ArtifactPipelineError(
                "缺少构建命令",
                artifact=artifact,
                stage="build",
            )
        run_script(artifact, "build", str(build_args[0]), *build_args[1:])

        verify_args = tuple(verify_command(staged_output, staged_input))
        if not verify_args:
            raise ArtifactPipelineError(
                "缺少校验命令",
                artifact=artifact,
                stage="verify",
            )
        verified = run_script(
            artifact,
            "verify",
            str(verify_args[0]),
            *verify_args[1:],
        )
        document_bytes = staged_output.read_bytes()
        if not document_bytes:
            raise ArtifactPipelineError(
                "校验后的 HTML 为空",
                artifact=artifact,
                stage="publish",
            )
        publish_verified(staged_output, target, artifact=artifact)

        metadata = {
            key: value
            for key, value in verified.items()
            if key not in {"ok", "path", "output", "question"}
        }
        return {
            "ok": True,
            "artifact": artifact,
            "output": str(target),
            "verified": True,
            "bytes": len(document_bytes),
            "sha256": hashlib.sha256(document_bytes).hexdigest(),
            **metadata,
        }
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def personality(args: argparse.Namespace) -> dict[str, Any]:
    return build_deliverable(
        "personality",
        args.output,
        lambda staged, _snapshot: (
            "build_personality_assessment_html.py",
            "--version",
            args.version,
            "--output",
            staged,
        ),
        lambda staged, _snapshot: ("verify_personality_assessment_html.py", staged),
    )


def tarot(args: argparse.Namespace) -> dict[str, Any]:
    return build_deliverable(
        "tarot",
        args.output,
        lambda staged, _snapshot: (
            "build_tarot_draw_html.py",
            "--question",
            args.question,
            "--output",
            staged,
        ),
        lambda staged, _snapshot: ("verify_tarot_draw_html.py", staged),
    )


def share_card(args: argparse.Namespace) -> dict[str, Any]:
    def require_snapshot(snapshot: Optional[Path]) -> Path:
        if snapshot is None:
            raise ArtifactPipelineError(
                "分享卡缺少输入快照",
                artifact="share-card",
                stage="prepare",
            )
        return snapshot

    return build_deliverable(
        "share-card",
        args.output,
        lambda staged, snapshot: (
            "render_share_card_html.py",
            require_snapshot(snapshot),
            "--output",
            staged,
        ),
        lambda staged, snapshot: (
            "verify_share_card_html.py",
            staged,
            "--input",
            require_snapshot(snapshot),
        ),
        snapshot_input=args.input,
    )


def build_deliverable(
    artifact: str,
    output: Optional[Path],
    build_command: CommandFactory,
    verify_command: CommandFactory,
    *,
    snapshot_input: Optional[Path] = None,
) -> dict[str, Any]:
    """Write the verified page where the host can deliver it, or clean up on failure."""
    import secure_run_dir

    run_dir = None
    if output is None:
        workspace = delivery.resolve_workspace()
        if workspace is not None:
            output = delivery.available_path(workspace, DELIVERY_STEMS[artifact])
        else:
            run_dir = secure_run_dir.create_run_dir()
            output = run_dir / f"{artifact}.html"
    try:
        result = build_verified_artifact(
            artifact, output, build_command, verify_command,
            snapshot_input=snapshot_input,
        )
    except Exception:
        if run_dir:
            secure_run_dir.cleanup_run_dir(run_dir)
        raise
    result["next_action"] = "display_html"
    delivery.attach_delivery(
        result,
        result["output"],
        DELIVERY_DESCRIPTIONS[artifact],
        success_action="display_html",
    )
    if run_dir:
        result["cleanup_command"] = (
            "python3 scripts/secure_run_dir.py cleanup --path " + shlex.quote(str(run_dir))
        )
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build, verify, and atomically publish one HTML artifact."
    )
    subparsers = parser.add_subparsers(dest="artifact", required=True)

    personality_parser = subparsers.add_parser(
        "personality", help="Build a verified personality assessment page."
    )
    personality_parser.add_argument(
        "--version", choices=("quick", "deep"), default="quick"
    )
    personality_parser.add_argument("--output", type=Path)
    personality_parser.set_defaults(handler=personality)

    tarot_parser = subparsers.add_parser(
        "tarot", help="Build a verified question-scoped Tarot page."
    )
    tarot_parser.add_argument("--question", required=True)
    tarot_parser.add_argument("--output", type=Path)
    tarot_parser.set_defaults(handler=tarot)

    share_parser = subparsers.add_parser(
        "share-card", help="Render and verify a share-card JSON input."
    )
    share_parser.add_argument("input", type=Path)
    share_parser.add_argument("--output", type=Path)
    share_parser.set_defaults(handler=share_card)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        print(json.dumps(args.handler(args), ensure_ascii=False))
        return 0
    except ArtifactPipelineError as exc:
        payload: dict[str, Any] = {
            "ok": False,
            "error": "E_ARTIFACT_PIPELINE",
            "artifact": exc.artifact,
            "stage": exc.stage,
            "message": str(exc),
        }
        if exc.details is not None:
            payload["details"] = exc.details
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 2
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "E_ARTIFACT_PIPELINE_RUNTIME",
                    "artifact": getattr(args, "artifact", "unknown"),
                    "stage": "runtime",
                    "message": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
