"""System-mutation helpers — facade after privilege/mount split."""
from __future__ import annotations

import glob
import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .runner import run_command
from .executor import ExecutorCommand, PrivilegedExecutor
from .secure_boot import MokPlan, classify_import, plan_mok as _python_plan_mok
from kyth_shared import accounts as _accounts

# Canonical modules
from .system_privilege import (  # pylint: disable=unused-import  # noqa: F401
    _as_root,
    _require_no_symlink,  # pylint: disable=unused-import
    _safe_umount,  # pylint: disable=unused-import
    _settle,  # pylint: disable=unused-import
    format_install_error,  # pylint: disable=unused-import
    format_os_error,
    require_root,  # pylint: disable=unused-import
)
from .system_mount import (  # pylint: disable=unused-import
    _lsblk_target_mounts,
    mount_filesystem,
    unmount_filesystem,
    unmount_target_disk,
)  # noqa: F401

_logger = logging.getLogger(__name__)


def _plan_mok(**kwargs) -> MokPlan:
    """Use the native decision model when the privileged helper is present."""
    if not shutil.which("kyth-installer-exec"):
        return _python_plan_mok(**kwargs)
    result = run_command(
        _as_root(["kyth-installer-exec", "--operation", "secure-boot-plan"]),
        input=json.dumps(kwargs, separators=(",", ":")),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    try:
        response = json.loads(result.stdout or "{}")
        fields = {
            "state": response["state"],
            "action": response["action"],
            "requires_password": response["requires_password"],
            "requires_reboot_confirmation": response["requires_reboot_confirmation"],
            "message": response["message"],
        }
        if not all(isinstance(value, str) for key, value in fields.items() if key in {"state", "action", "message"}):
            raise ValueError("Secure Boot plan contained invalid text fields")
        if not all(isinstance(fields[key], bool) for key in ("requires_password", "requires_reboot_confirmation")):
            raise ValueError("Secure Boot plan contained invalid boolean fields")
        return MokPlan(**fields)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"native Secure Boot plan was invalid: {exc}") from exc

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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
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
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        raise RuntimeError(f"Could not repair system accounts under {deploy_root}: {exc}") from exc


def _try_stage_mok_enrollment(log, kernel: str = "fedora", mok_password: str = "") -> str:
    """Stage Kyth Secure Boot MOK enrollment via mokutil.

    Returns one of: skipped, enrolled, pending, staged, failed.
    """
    force_stage = os.environ.get("KYTH_STAGE_MOK", "0").lower() in ("1", "true", "yes", "on")
    plan_mok = _plan_mok
    executor = PrivilegedExecutor(run_command=run_command, as_root=_as_root)

    def run_mok(argv: list[str], description: str, **kwargs):
        return executor.run(
            ExecutorCommand.from_argv(argv, description, timeout=kwargs.pop("timeout", 30)),
            **kwargs,
        )

    if kernel != "cachy" and not force_stage:
        decision = plan_mok(kernel=kernel, force_stage=force_stage)
        log(f"Secure Boot: {decision.message}")
        return decision.state

    cert_der = Path("/usr/share/kyth/secureboot/kyth-secureboot.der")
    if not cert_der.exists():
        decision = plan_mok(
            kernel=kernel, force_stage=force_stage, certificate_present=False,
        )
        log(f"Secure Boot: {decision.message}")
        return decision.state

    mokutil = shutil.which("mokutil")
    if not mokutil:
        decision = plan_mok(
            kernel=kernel, force_stage=force_stage, certificate_present=True,
        )
        log(f"Secure Boot: {decision.message}")
        return decision.state

    try:
        result = run_mok(
            [mokutil, "--sb-state"],
            "check Secure Boot state",
            capture_output=True, text=True, timeout=5,
        )
        if "SecureBoot enabled" not in result.stdout:
            decision = plan_mok(
                kernel=kernel, force_stage=force_stage,
                certificate_present=True, mokutil_present=True,
                secure_boot="disabled",
            )
            log(f"Secure Boot: {decision.message}")
            log("Secure Boot: if you enable it later, run 'ujust enroll-secureboot'")
            return decision.state
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        log(f"Secure Boot: could not check state ({exc}) — skipping enrollment staging")
        return "skipped"

    try:
        enrolled = run_mok(
            [mokutil, "--list-enrolled"],
            "list enrolled KythOS Secure Boot keys",
            capture_output=True, text=True, timeout=5,
        )
        if "KythOS Secure Boot" in enrolled.stdout:
            decision = plan_mok(
                kernel=kernel, force_stage=force_stage,
                certificate_present=True, mokutil_present=True,
                secure_boot="enabled", enrolled="yes",
            )
            log(f"Secure Boot: {decision.message}")
            return decision.state
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        log(f"Secure Boot: could not check enrolled keys ({exc}) — continuing")

    try:
        pending = run_mok(
            [mokutil, "--list-new"],
            "list pending KythOS Secure Boot keys",
            capture_output=True, text=True, timeout=5,
        )
        if "KythOS Secure Boot" in pending.stdout:
            decision = plan_mok(
                kernel=kernel, force_stage=force_stage,
                certificate_present=True, mokutil_present=True,
                secure_boot="enabled", enrolled="no", pending="yes",
            )
            log(f"Secure Boot: {decision.message}")
            return decision.state
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        log(f"Secure Boot: could not check staged keys ({exc}) — continuing")

    try:
        result = run_mok(
            [mokutil, "--import", str(cert_der), "--stdin-passwd"],
            "stage KythOS Secure Boot key enrollment",
            input=f"{mok_password}\n", text=True, capture_output=True, timeout=15,
        )
        if classify_import(result.returncode) == "staged":
            log("Secure Boot: enrollment staged — confirm it on first boot before the KythOS performance kernel starts")
            return "staged"
        log(f"Secure Boot: mokutil import failed (exit {result.returncode}): {result.stderr.strip()}")
        return "failed"
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
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
