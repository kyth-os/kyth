"""System-mutation helpers for kyth-installer: privilege escalation, account
database repair, MOK/Secure Boot enrollment, timezone listing, and unmounting
a target disk before a wipe install.
"""

import glob
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional
from .runner import run_command, run_as_root as _as_root
from kyth_shared import accounts as _accounts

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


def list_timezones() -> list[str]:
    try:
        result = run_command(
            ["timedatectl", "list-timezones"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        out = result.stdout
        zones = [ln.strip() for ln in out.splitlines() if ln.strip()]
        if zones:
            return zones
    except Exception:
        _logger.debug("list_timezones: timedatectl probe failed", exc_info=True)
    # timedatectl unavailable or returned nothing — read zone.tab directly.
    for tab in ("/usr/share/zoneinfo/zone1970.tab", "/usr/share/zoneinfo/zone.tab"):
        try:
            zones = ["UTC"]
            with open(tab) as f:
                for raw_line in f:
                    line = raw_line.strip()
                    if line and not line.startswith("#"):
                        parts = line.split()
                        if len(parts) >= 3:
                            zones.append(parts[2])
            if zones:
                return sorted(set(zones))
        except Exception:
            _logger.debug("list_timezones: reading %s failed", tab, exc_info=True)
    return ["UTC"]


def _list_localectl_values(kind: str, fallback: list[str]) -> list[str]:
    try:
        result = run_command(
            ["localectl", f"list-{kind}", "--no-pager"],
            capture_output=True, text=True, check=True, timeout=10,
        )
        values = sorted({line.strip() for line in result.stdout.splitlines() if line.strip()})
        if values:
            return values
    except Exception:
        _logger.debug("localectl list-%s failed", kind, exc_info=True)
    return fallback


def list_locales() -> list[str]:
    return _list_localectl_values("locales", ["en_US.UTF-8"])


def list_keymaps() -> list[str]:
    return _list_localectl_values("keymaps", ["us"])


def find_deploy_etc(root_mount: str) -> Optional[str]:
    candidates = glob.glob(f"{root_mount}/ostree/deploy/default/deploy/*/etc")
    if not candidates:
        return None
    return sorted(candidates)[-1]


# The actual account-database repair algorithm lives in kyth_shared.accounts
# so every installer entry point runs identical logic instead of an
# independently-drifting reimplementation.
# These wrappers keep this module's historical call signatures — used
# directly by tests and by install.py — by injecting a run() that carries
# this package's own _as_root escalation and OSError formatting.
def _run(argv: list[str], **kwargs) -> subprocess.CompletedProcess:
    return run_command(_as_root(argv), **kwargs)


def _read_lines(path: Path) -> list[str]:
    """Read a target-tree file via elevated cat (never host open())."""
    try:
        return _accounts._read_lines(path, _run)
    except Exception as exc:
        raise type(exc)(
            f"{format_os_error(exc, path=path) if isinstance(exc, OSError) else exc}"
        ) from exc


def _write_lines(path: Path, lines: list[str], mode: int) -> None:
    """Write a target-tree file via elevated mkdir/tee/chmod (shell-installer parity).

    passwd uses the literal "x" placeholder; shadow records contain hashes.
    Always go through _as_root so account databases never depend on the Python
    process being able to open the mounted deploy tree itself.
    """
    try:
        _accounts._write_lines(path, lines, mode, _run)
    except OSError as exc:
        raise OSError(format_os_error(exc, path=str(path))) from exc
    except Exception as exc:
        # run_command raises RuntimeError with command detail; annotate path.
        raise RuntimeError(f"Could not write {path}: {exc}") from exc


def _path_exists(path: Path) -> bool:
    return _accounts._path_exists(path, _run)


def _chmod_path(path: Path, mode: int) -> None:
    try:
        _accounts._chmod_path(path, mode, _run)
    except OSError as exc:
        raise OSError(format_os_error(exc, path=str(path))) from exc


def ensure_system_accounts(deploy_root: str, log) -> None:
    try:
        _accounts.ensure_system_accounts(deploy_root, log, run=_run)
    except OSError as exc:
        raise OSError(format_os_error(exc, path=deploy_root)) from exc
    except Exception as exc:
        raise RuntimeError(f"Could not repair system accounts under {deploy_root}: {exc}") from exc


def _lsblk_target_mounts(disk: str) -> list[tuple[str, str]]:
    """Return (device, mountpoint) pairs for mounted devices under disk."""
    result = run_command(
        ["lsblk", "--json", "--paths", "--output", "NAME,TYPE,MOUNTPOINTS", disk],
        capture_output=True, text=True, check=True,
    )
    out = result.stdout
    mounts: list[tuple[str, str]] = []

    def walk(dev: dict) -> None:
        name = dev.get("name") or ""
        for mount in dev.get("mountpoints") or []:
            if mount:
                mounts.append((name, mount))
        for child in dev.get("children") or []:
            walk(child)

    for dev in json.loads(out).get("blockdevices", []):
        walk(dev)
    mounts.sort(key=lambda item: item[1].count("/"), reverse=True)
    return mounts


# Mountpoints that must never receive a lazy unmount — they are part of the
# running system and detaching them would destabilize the OS.
_CRITICAL_MOUNTS = frozenset({"/", "/boot", "/boot/efi", "/efi", "/home", "/var"})


def unmount_target_disk(disk: str, log) -> None:
    """Unmount any live-session mounts that would block wiping disk."""
    log(f"Unmounting any existing mounts on {disk} ...")
    for mount in ("/mnt", "/sysroot", "/target"):
        run_command(_as_root(["umount", "-R", mount]), check=False)

    try:
        mounts = _lsblk_target_mounts(disk)
    except Exception as exc:
        raise RuntimeError(
            f"Could not inspect mounts on target disk {disk}; no storage changes were made. "
            f"Retry after checking lsblk/udev. Detail: {exc}"
        ) from exc

    for dev, mount in mounts:
        log(f"Unmounting {dev} from {mount}")
        result = run_command(
            _as_root(["umount", "-R", mount]),
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            log(f"Normal unmount failed for {mount}: {err}")
            if mount in _CRITICAL_MOUNTS:
                log(f"Skipping lazy unmount of running system mount: {mount}")
            else:
                _safe_umount(run_command, mount)

    try:
        remaining = _lsblk_target_mounts(disk)
    except Exception as exc:
        raise RuntimeError(
            f"Could not verify that target disk {disk} is fully unmounted; "
            f"refusing to continue. Detail: {exc}"
        ) from exc
    if remaining:
        details = ", ".join(f"{dev} at {mount}" for dev, mount in remaining)
        raise RuntimeError(
            f"Target disk {disk} still has mounted partitions: {details}. "
            "Close any file manager or terminal using those paths and retry."
        )


def _try_stage_mok_enrollment(log, kernel: str = "fedora", mok_password: str = "") -> str:
    """Stage Kyth Secure Boot MOK enrollment via mokutil.

    Returns one of: skipped, enrolled, pending, staged, failed.
    """
    force_stage = os.environ.get("KYTH_STAGE_MOK", "0").lower() in ("1", "true", "yes", "on")
    if kernel != "cachy" and not force_stage:
        log("Secure Boot: standard KythOS kernel selected — custom-kernel MOK enrollment not staged")
        return "skipped"

    cert_der = Path("/usr/share/kyth/secureboot/kyth-secureboot.der")
    if not cert_der.exists():
        log("Secure Boot: cert not found in live image — skipping enrollment staging")
        return "skipped"

    mokutil = shutil.which("mokutil")
    if not mokutil:
        log("Secure Boot: mokutil not found — skipping enrollment staging")
        return "skipped"

    try:
        result = run_command(
            _as_root([mokutil, "--sb-state"]),
            capture_output=True, text=True, timeout=5,
        )
        if "SecureBoot enabled" not in result.stdout:
            log("Secure Boot: not currently enabled — enrollment staging skipped")
            log("Secure Boot: if you enable it later, run 'ujust enroll-secureboot'")
            return "skipped"
    except Exception as exc:
        log(f"Secure Boot: could not check state ({exc}) — skipping enrollment staging")
        return "skipped"

    try:
        enrolled = run_command(
            _as_root([mokutil, "--list-enrolled"]),
            capture_output=True, text=True, timeout=5,
        )
        if "KythOS Secure Boot" in enrolled.stdout:
            log("Secure Boot: KythOS key already enrolled")
            return "enrolled"
    except Exception as exc:
        log(f"Secure Boot: could not check enrolled keys ({exc}) — continuing")

    try:
        pending = run_command(
            _as_root([mokutil, "--list-new"]),
            capture_output=True, text=True, timeout=5,
        )
        if "KythOS Secure Boot" in pending.stdout:
            log("Secure Boot: enrollment already staged — confirm it on next boot")
            return "pending"
    except Exception as exc:
        log(f"Secure Boot: could not check staged keys ({exc}) — continuing")

    try:
        result = run_command(
            _as_root([mokutil, "--import", str(cert_der), "--stdin-passwd"]),
            input=f"{mok_password}\n", text=True, capture_output=True, timeout=15,
        )
        if result.returncode == 0:
            log("Secure Boot: enrollment staged — confirm it on first boot before the KythOS performance kernel starts")
            return "staged"
        log(f"Secure Boot: mokutil import failed (exit {result.returncode}): {result.stderr.strip()}")
        return "failed"
    except Exception as exc:
        log(f"Secure Boot: enrollment staging failed: {exc}")
        return "failed"


def _hash_password(password: str) -> str:
    # openssl passwd -stdin emits nothing (exit 0) for empty input, which
    # would surface as a confusing "invalid SHA-512 crypt value" error.
    if not password:
        raise RuntimeError("Password cannot be empty. Return to the Configure step and re-enter it.")
    result = run_command(
        ["openssl", "passwd", "-6", "-stdin"],
        input=password,
        text=True,
        capture_output=True,
        check=True,
        timeout=15,
    )
    password_hash = result.stdout.strip()
    if not password_hash.startswith("$6$"):
        raise RuntimeError("Password hashing returned an invalid SHA-512 crypt value")
    return password_hash
