"""Single-flight lock for NVIDIA ``akmods --force`` builds.

Hub "Build module" and ``kyth-hw-setup`` both compile into ``/var/lib/akmods``.
Concurrent ``akmods --force`` can corrupt that tree. Every build path must
hold this lock for the duration of the compile.
"""
from __future__ import annotations

import errno
import fcntl
import logging
import os
import time
from pathlib import Path

_logger = logging.getLogger(__name__)

DEFAULT_LOCK_PATH = Path("/run/kyth-akmods.lock")
DEFAULT_TIMEOUT_SEC = 900.0


def lock_path() -> Path:
    override = os.environ.get("KYTH_AKMODS_LOCK", "").strip()
    return Path(override) if override else DEFAULT_LOCK_PATH


def acquire_akmods_lock(
    path: Path | None = None,
    timeout: float = DEFAULT_TIMEOUT_SEC,
) -> int:
    """Return an fd holding ``LOCK_EX``. Caller must ``release_akmods_lock``.

    Raises ``RuntimeError`` if another builder still holds the lock after
    *timeout* seconds.
    """
    target = path if path is not None else lock_path()
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(target), os.O_RDWR | os.O_CREAT, 0o644)
    except OSError as exc:
        raise RuntimeError(f"could not open NVIDIA akmods lock {target}: {exc}") from exc
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return fd
        except OSError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EACCES):
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise
            if time.monotonic() >= deadline:
                try:
                    os.close(fd)
                except OSError:
                    pass
                raise RuntimeError(
                    "another NVIDIA module build is already running; wait for it to finish"
                ) from exc
            time.sleep(0.2)


def release_akmods_lock(fd: int | None) -> None:
    if fd is None:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass


def akmods_build_in_progress(path: Path | None = None) -> bool:
    """True when another process holds the exclusive akmods lock."""
    target = path if path is not None else lock_path()
    try:
        fd = os.open(str(target), os.O_RDWR)
    except OSError:
        return False
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(fd, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
