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


def _fsync_directory(path: Path) -> None:
    """Persist *path*'s directory entries.

    Must be called *after* the rename it is meant to make durable: fsyncing the
    parent beforehand flushes a directory state that does not yet contain the
    new name, so a power loss can still lose the replace.
    """
    try:
        dfd = os.open(str(path), os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except OSError:
        pass


def _atomic_write_json(path: Path, payload: dict) -> None:
    """Write *payload* so a power loss leaves either the old file or the new."""
    temporary = path.with_suffix(path.suffix + ".tmp")
    fd = os.open(
        str(temporary),
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
        0o600,
    )
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


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
    _atomic_write_json(path, payload)


def write_transaction_state(
    path: Path,
    *,
    context: InstallerContext,
    status: str,
    message: str = "",
) -> None:
    """Persist the non-secret transaction state for recovery and support."""
    plan = context.plan
    payload = {
        "schema_version": 1,
        "transaction_id": context.transaction_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "phase": context.phase.value,
        "lifecycle": context.lifecycle.value,
        "install_mode": plan.mode if plan is not None else context.state.get("install_mode", ""),
        "disk": plan.disk if plan is not None else context.state.get("disk", ""),
        "target_partition": (
            plan.target_partition if plan is not None else context.state.get("target_partition", "")
        ),
        "source": {
            "kind": plan.source_kind if plan is not None else "unresolved",
            "digest": plan.source_digest if plan is not None else "",
            "verified": plan.source_verified if plan is not None else False,
            "target_ref": plan.target_ref if plan is not None else "",
        },
        "checks": list(context.assurance_checks),
        "partition_steps": list(context.partition_steps),
        "message": message,
    }
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.parent.is_symlink() or not path.parent.is_dir():
        raise RuntimeError(f"Unsafe transaction report directory: {path.parent}")
    if path.parent.stat().st_uid != os.geteuid():
        raise RuntimeError(f"Transaction report directory is not owned by this installer: {path.parent}")
    path.parent.chmod(0o700)
    _atomic_write_json(path, payload)


def read_transaction_state(path: Path) -> dict:
    """Read the support-safe transaction state, returning an empty record."""
    try:
        if path.is_symlink() or not path.is_file():
            return {}
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}
