"""UpdateCoordinator — single-writer state machine for boot health + staged updates (arch #3).

Provides atomic read-modify-write with file lock so concurrent Hub pages
and `kyth-safe-upgrade` do not race on `/var/lib/kyth/boot-health.json`.
Pages should import *this* instead of calling `read_state`/`write_state` directly.
"""
from __future__ import annotations

import fcntl
from pathlib import Path
from typing import Callable, TypeVar

from .boot_health import BootHealthState, DEFAULT_STATE_PATH, read_state, write_state

T = TypeVar("T")


def _locked_write(path: Path, fn: Callable[[BootHealthState], BootHealthState]) -> BootHealthState:
    """Read, transform via *fn*, and atomically write back under exclusive lock."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Use a sibling lock file so we don't hold the JSON itself open across readers
    lock_path = path.with_suffix(path.suffix + ".lock")
    lock_path.touch(exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        except OSError:
            pass  # fallback to unlocked write on non-POSIX FS (tests)
        try:
            current = read_state(path)
            updated = fn(current)
            write_state(updated, path)
            return updated
        finally:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            except OSError:
                pass


class UpdateCoordinator:
    """Single-writer coordinator owned by one path (default `/var/lib/kyth/boot-health.json`)."""

    def __init__(self, path: Path | str = DEFAULT_STATE_PATH):
        self.path = Path(path)

    def read(self) -> BootHealthState:
        return read_state(self.path)

    def transaction(self, fn: Callable[[BootHealthState], BootHealthState]) -> BootHealthState:
        return _locked_write(self.path, fn)

    # Convenience wrappers used by safe_upgrade + Hub
    def mark_healthy(self, digest: str) -> BootHealthState:
        from .boot_health import mark_healthy

        return self.transaction(lambda s: mark_healthy(s, digest))

    def record_failure(self, digest: str, boot_id: str, reason: str, threshold: int = 3) -> BootHealthState:
        from .boot_health import record_failure

        return self.transaction(lambda s: record_failure(s, digest, boot_id, reason, threshold=threshold))

    def record_staged(self, digest: str, rollout_ring: str = "stable") -> BootHealthState:
        from .boot_health import record_staged

        return self.transaction(lambda s: record_staged(s, digest, rollout_ring=rollout_ring))

    def clear_quarantine(self, digest: str) -> BootHealthState:
        from .boot_health import clear_quarantine

        return self.transaction(lambda s: clear_quarantine(s, digest))
