"""Privilege helpers — canonical after system 383 split."""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from .runner import run_command as _orig_run_command, run_as_root as _orig_as_root
from kyth_shared import accounts as _accounts

def _as_root(argv):  # type: ignore
    try:
        from . import system as _facade  # type: ignore
        fn = getattr(_facade, "_as_root", None)
        if fn is not None and getattr(fn, "__module__", "") != "kyth_installer.runner":
            return fn(argv)  # type: ignore
    except Exception:
        pass
    return _orig_as_root(argv)

def run_command(*args, **kwargs):  # type: ignore
    try:
        from . import system as _facade  # type: ignore
        fn = getattr(_facade, "run_command", None)
        if fn is not None and getattr(fn, "__module__", "") != "kyth_installer.runner":
            return fn(*args, **kwargs)  # type: ignore
    except Exception:
        pass
    return _orig_run_command(*args, **kwargs)

_logger = logging.getLogger(__name__)


def _require_no_symlink(path: str) -> None:
    """Refuse to mkdir/mount/write through a pre-existing symlink at `path`.

    The installer runs as root against fixed paths under the world-writable
    /tmp and /var/tmp (mount staging dirs, log file, partition-table backup).
    Without this check, a local user could pre-plant a symlink there (e.g.
    pointing at /etc) before the installer runs, and a root `mkdir -p` +
    `mount` (or file write) would silently follow it. Call this immediately
    before the first privileged operation touches the path — once mkdir/open
    has created a real, root-owned entry there, /tmp's sticky bit stops any
    other user from swapping it out from under us.
    """
    if os.path.islink(path):
        raise RuntimeError(
            f"Refusing to use {path}: it already exists as a symlink, which "
            "may indicate local tampering. Remove it and retry."
        )


def _safe_umount(run, path: str, *, check: bool = False) -> subprocess.CompletedProcess:
    """Lazily detach `path` via the caller's own run(), swallowing "not
    mounted" / "target busy" failures by default.

    Install-path unmounts previously duplicated `umount -l` with a slightly
    different check=/capture_output= combination at each call site (some
    captured output, one didn't, one used check=True) — centralize on one
    behavior instead. `run` is passed in rather than imported here so each
    caller's own run_command reference is what actually executes, keeping
    existing `run_command` mocks/patches on the caller's module effective.
    """
    return run(_as_root(["umount", "-l", path]), check=check, capture_output=True)


def _settle():
    run_command(_as_root(["partprobe"]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    run_command(["udevadm", "settle"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)


def require_root() -> None:
    """Refuse to continue unless the process is already privileged.

    The desktop launcher elevates via sudo/pkexec before starting the installer.
    Install mutations (bootc, mkfs, account databases) must not rely on a later
    best-effort `sudo -n` that may be missing a TTY or policy.
    """
    if os.geteuid() != 0:
        raise RuntimeError(
            "The KythOS installer must run as root.\n\n"
            "Launch it from the desktop Install KythOS tile, or run:\n"
            "  sudo kyth-installer\n\n"
            f"Current euid={os.geteuid()}."
        )


def format_os_error(exc: BaseException, *, path: str | Path | None = None) -> str:
    """Human-readable OSError/PermissionError with path and errno when available."""
    if not isinstance(exc, OSError):
        return str(exc)

    parts: list[str] = []
    msg = (exc.strerror or str(exc) or exc.__class__.__name__).strip()
    if msg:
        parts.append(msg)

    filename = path if path is not None else getattr(exc, "filename", None)
    if filename:
        parts.append(f"path={filename}")
    filename2 = getattr(exc, "filename2", None)
    if filename2:
        parts.append(f"path2={filename2}")

    err = getattr(exc, "errno", None)
    if err is not None:
        try:
            import errno as errno_mod
            name = errno_mod.errorcode.get(err, "UNKNOWN")
        except Exception:
            name = "UNKNOWN"
        parts.append(f"errno={err} ({name})")

    return "; ".join(parts) if parts else exc.__class__.__name__


def format_install_error(exc: BaseException) -> str:
    """SSE/log message for install failures, preserving OSError detail."""
    if isinstance(exc, OSError):
        detail = format_os_error(exc)
        return f"{exc.__class__.__name__}: {detail}"
    return str(exc) or exc.__class__.__name__


