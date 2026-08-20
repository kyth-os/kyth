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
from pathlib import Path

from kyth_shared.commands import run

from kyth_shared.runtime_output import count_fwupd_updates


def firmware_refresh_commands() -> list[list[str]]:
    return [["fwupdmgr", "refresh", "--force"]]


def firmware_devices_command() -> list[str]:
    return ["fwupdmgr", "get-devices"]


def firmware_updates_command() -> list[str]:
    return ["fwupdmgr", "get-updates"]


def firmware_update_command() -> list[str]:
    return ["fwupdmgr", "update", "--assume-yes", "--no-reboot-check"]


def run_firmware_refresh(timeout: int = 60) -> tuple[bool, str]:
    """Refresh fwupd metadata. Returns (ok, output). Optional — failures are non-fatal."""
    try:
        r = run(
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path  # noqa: BLE001
        return False, str(exc)


def check_firmware_updates(timeout: int = 20) -> int:
    """Return count of pending fwupd device updates, 0 on error or none."""
    try:
        r = run(
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # noqa: BLE001
        return 0


def run_firmware_update(timeout: int = 600) -> tuple[bool, str]:
    """Stage available fwupd updates. Returns (ok, output)."""
    try:
        r = run(
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path  # noqa: BLE001
        return False, str(exc)


def get_firmware_devices(timeout: int = 15) -> tuple[int, str, int]:
    """Return (device_count, output, returncode). Optional — 0, '', 2 on missing."""
    try:
        r = run(
            firmware_devices_command(),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        out = (r.stdout or "").strip()
        if r.returncode != 0:
            return 0, out or r.stderr.strip(), r.returncode
        count = out.count("Device ID:")
        return count, out, 0
    except FileNotFoundError:
        return 0, "fwupdmgr not found", 2
    except subprocess.TimeoutExpired:
        return 0, f"fwupdmgr get-devices timed out after {timeout}s", 1
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path  # noqa: BLE001
        return 0, str(exc), 1


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


def stage_firmware_batch(
    refresh_timeout: int = 60,
    check_timeout: int = 20,
    update_timeout: int = 600,
    lock_path: str | None = None,
) -> tuple[bool, int, str]:
    """Batched refresh→check→update behind flock (60s). Prevents thundering herd."""
    import fcntl
    import os

    if lock_path is None:
        lock_path = os.environ.get("KYTH_FWUPD_LOCK", "/run/kyth-fwupd.lock")
    try:
        Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "a+", encoding="utf-8") as lf:
            try:
                fcntl.flock(lf.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                # Lock contended — another watcher/probe is already handling fwupd.
                # Return empty to avoid parallel fwupd DB contention (thundering herd).
                return False, 0, ""
            return stage_firmware_updates(
                refresh_timeout=refresh_timeout,
                check_timeout=check_timeout,
                update_timeout=update_timeout,
            )
    except (OSError, BlockingIOError):
        # Could not open/lock file (e.g. /run ro). Don't run unprotected batch
        # that would thunder-herd fwupd; just skip.
        return False, 0, ""
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # noqa: BLE001
        return False, 0, ""
