"""Best-effort persistence of installer diagnostics onto the target disk."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


FALLBACK_TARGET_MOUNTS = (
    "/var/tmp/kyth-alongside-target",
    "/var/tmp/kyth-install-root",
)


def target_mount_candidates(context) -> list[str]:
    """Return registered and legacy target mounts without duplicates."""
    try:
        candidates = list(getattr(context, "cleanup_mounts", []) or [])
    except Exception:
        candidates = []
    for mountpoint in FALLBACK_TARGET_MOUNTS:
        if mountpoint not in candidates:
            candidates.append(mountpoint)
    return candidates


def mounted_target(mountpoint: str, *, run_command) -> bool:
    """Return whether a candidate is a directory backed by a mount."""
    if not mountpoint or not os.path.isdir(mountpoint):
        return False
    try:
        result = run_command(["findmnt", "-n", mountpoint], capture_output=True, timeout=3)
    except Exception:
        return True
    return result.returncode == 0


def persist_artifacts(log, context, sources, *, run_command, as_root) -> None:
    """Copy safe volatile diagnostics to the first usable target mount."""
    for mountpoint in target_mount_candidates(context):
        try:
            if not mounted_target(mountpoint, run_command=run_command):
                continue
            destination = Path(mountpoint) / "var/log/kyth-installer"
            try:
                run_command(as_root(["mkdir", "-p", str(destination)]), check=False)
                for source in sources:
                    if source.is_file() and not source.is_symlink():
                        run_command(
                            as_root(["cp", "-a", str(source), str(destination / source.name)]),
                            check=False,
                        )
                log(f"Installer artifacts persisted to {destination} on the target disk.")
                return
            except Exception as exc:
                log(f"Warning: could not persist artifacts to {mountpoint}: {exc}")
        except Exception:
            continue


def persist_failure_message(log, context, message: str, *, persist, run_command, as_root) -> None:
    """Persist shared artifacts plus a human-readable failure message."""
    persist(log, context)
    for mountpoint in target_mount_candidates(context):
        try:
            if not mounted_target(mountpoint, run_command=run_command):
                continue
            destination = Path(mountpoint) / "var/log/kyth-installer"
            try:
                failure = destination / "install-failure.txt"
                run_command(
                    as_root(["/usr/bin/tee", str(failure)]),
                    input=f"{message}\n\nSee also: {destination}/failure.json\n",
                    text=True, stdout=subprocess.DEVNULL, check=False,
                )
                return
            except Exception:
                pass
        except Exception:
            continue
