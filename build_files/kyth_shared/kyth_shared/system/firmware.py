"""Shared fwupd helpers — single source for refresh / get-updates / update.

Used by kyth-update-watcher (root timer), kyth-full-update (user+sudo), and
Hub's FirmwareCheckWorker / _firmware_probe. All helpers are optional:
missing binary, returncode 2, empty stdout, or TimeoutExpired return
( False / 0 ) and never raise, so bootc/flatpak work proceeds.

Mirrors the subprocess patterns previously duplicated in:
- build_files/kyth-update-watcher
- build_files/kyth-full-update
- build_files/kyth-welcome/kyth_welcome/services/workers/updates.py
- build_files/kyth-welcome/kyth_welcome/services/hardware/io.py
"""
from __future__ import annotations

import subprocess

from kyth_shared.runtime_output import count_fwupd_updates


def firmware_refresh_commands() -> list[list[str]]:
    return [["fwupdmgr", "refresh", "--force"]]


def firmware_updates_command() -> list[str]:
    return ["fwupdmgr", "get-updates"]


def firmware_update_command() -> list[str]:
    return ["fwupdmgr", "update", "--assume-yes", "--no-reboot-check"]


def run_firmware_refresh(timeout: int = 60) -> tuple[bool, str]:
    """Refresh fwupd metadata. Returns (ok, output). Optional — failures are non-fatal."""
    try:
        r = subprocess.run(
            firmware_refresh_commands()[0],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (r.stdout + r.stderr).strip()
        return r.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"fwupdmgr refresh timed out after {timeout}s"
    except FileNotFoundError:
        return False, "fwupdmgr not found"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def check_firmware_updates(timeout: int = 20) -> int:
    """Return count of pending fwupd device updates, 0 on error or none."""
    try:
        r = subprocess.run(
            firmware_updates_command(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if r.returncode == 2 or not r.stdout.strip():
            return 0
        if r.returncode != 0:
            return 0
        return count_fwupd_updates(r.stdout)
    except FileNotFoundError:
        return 0
    except Exception:  # noqa: BLE001
        return 0


def run_firmware_update(timeout: int = 600) -> tuple[bool, str]:
    """Stage available fwupd updates. Returns (ok, output)."""
    try:
        r = subprocess.run(
            firmware_update_command(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        output = (r.stdout + r.stderr).strip()
        return r.returncode == 0, output
    except subprocess.TimeoutExpired:
        return False, f"fwupdmgr update timed out after {timeout}s"
    except FileNotFoundError:
        return False, "fwupdmgr not found"
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)


def stage_firmware_updates(
    refresh_timeout: int = 60,
    check_timeout: int = 20,
    update_timeout: int = 600,
) -> tuple[bool, int, str]:
    """Refresh, count, and if needed stage firmware. Returns (updated, count, output)."""
    run_firmware_refresh(timeout=refresh_timeout)
    count = check_firmware_updates(timeout=check_timeout)
    if count <= 0:
        return False, 0, ""
    ok, out = run_firmware_update(timeout=update_timeout)
    return (ok, count, out)
