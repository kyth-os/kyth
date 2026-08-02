"""Failure reporting and deterministic cleanup for installer transactions."""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .context import InstallerContext
from .system import _as_root

RunCommand = Callable[..., Any]


def cleanup_registered_mounts(context: InstallerContext, *, run: RunCommand) -> None:
    """Unmount every mount owned by this attempt, deepest/most-recent first."""
    for mountpoint in reversed(context.cleanup_mounts.copy()):
        run(_as_root(["umount", "-Rl", mountpoint]), check=False, capture_output=True)
        context.release_mount(mountpoint)


def write_failure_summary(
    path: Path,
    *,
    context: InstallerContext,
    message: str,
) -> None:
    """Atomically persist a support-friendly summary without request secrets."""
    plan = context.plan
    payload = {
        "schema_version": 1,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": context.phase.value,
        "lifecycle": context.lifecycle.value,
        "install_mode": plan.mode if plan is not None else context.state.get("install_mode", ""),
        "disk": plan.disk if plan is not None else context.state.get("disk", ""),
        "target_partition": plan.target_partition if plan is not None else context.state.get("target_partition", ""),
        "message": message,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(
        str(temporary),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
    os.replace(temporary, path)
