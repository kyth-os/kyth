"""Atomic JSON durability primitive — single source of truth for KythOS.

All on-disk JSON state (boot_health, probe cache, installer journal) must
use this: mkstemp → fchmod → dump → flush → fsync → rename → fsync parent
plus optional invariants() check. Replaces 3 divergent copies.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable


def atomic_write_json(
    path: str | Path,
    data: Any,
    *,
    mode: int = 0o644,
    invariants: Callable[[], list[str]] | None = None,
) -> None:
    """Atomically write *data* as JSON to *path* with durability.

    - Fails closed if *invariants* returns non-empty list.
    - Uses mkstemp in parent dir, fchmod, flush+fsync, rename, fsync parent.
    - Cleans up temp file on failure.
    """
    if invariants is not None:
        errs = invariants()
        if errs:
            raise ValueError(f"refusing to write {path} with invariant violations: {errs}")
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{dest.name}.", dir=dest.parent, text=True)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, dest)
        # fsync parent so rename survives power-loss
        try:
            dir_fd = os.open(dest.parent, os.O_DIRECTORY)
            try:
                os.fsync(dir_fd)
            finally:
                os.close(dir_fd)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json_or_default(path: str | Path, default: Any) -> Any:
    """Read JSON from *path* or return *default* on any error (torn write)."""
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return default
