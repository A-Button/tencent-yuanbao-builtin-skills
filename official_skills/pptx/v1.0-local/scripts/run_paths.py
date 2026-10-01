#!/usr/bin/env python3
"""Shared physical-path resolution for PPT run directories.

The model-facing convention (see SKILL.md) is that each task sets
``RUN=/data/workspace/ppt_runs/<run_id>`` and passes that string as the
``run_dir`` positional argument to prepare_deck.py / apply_plan.py /
finalize_run.py. Keep that literal RUN directory as the persistent home for
small files (deck*.json, content_plan.json, *_report.json, model-authored
inputs such as content_lines.tsv/images.json/layout_ops.json).

Only the unpacked OOXML tree lives under WORK_ROOT. It can be large and noisy
because it includes all XML parts and ppt/media assets, so it benefits from the
faster ephemeral /tmp filesystem and can be regenerated from the template if a
sandbox is destroyed.

The single final deliverable is named ``<run_id>.pptx``. Callers may supply
the user's workspace as ``output_dir``; otherwise it lives under DELIVERY_ROOT.

WORK_ROOT / DELIVERY_ROOT can be overridden via env vars for existing callers
and for tests outside the real sandbox, where ``/data`` does not exist.
"""

from __future__ import annotations

import os
from pathlib import Path

WORK_ROOT = Path(os.environ.get("PPT_WORK_ROOT", "/tmp/ppt_runs"))
DELIVERY_ROOT = Path(os.environ.get("PPT_DELIVERY_ROOT", "/data/workspace"))


def run_id_of(raw_run_dir: str) -> str:
    """Extract a stable run_id from whatever run_dir string was passed in."""
    return Path(raw_run_dir).name or "default"


def unpacked_dir(raw_run_dir: str) -> Path:
    """Physical location for the unpacked PPTX tree of this run."""
    d = WORK_ROOT / run_id_of(raw_run_dir) / "unpacked"
    d.parent.mkdir(parents=True, exist_ok=True)
    return d


def final_pptx_path(raw_run_dir: str, output_dir: str | Path | None = None) -> Path:
    """Physical location of the single final deliverable for this run.

    ``output_dir`` lets the caller select the user's current workspace. The
    environment-backed default remains for existing callers.
    """
    root = Path(output_dir) if output_dir is not None else DELIVERY_ROOT
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{run_id_of(raw_run_dir)}.pptx"
