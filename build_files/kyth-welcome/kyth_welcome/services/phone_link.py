"""KDE Connect phone actions and Dynamic Lock configuration.

Pure helpers (no Qt) used by the Windows migration / phone page.
"""
from __future__ import annotations

import os
import shutil

from .config import load_json_config, save_json_config
from .process import _run_command

_DYNAMIC_LOCK_CONFIG = os.path.expanduser("~/.config/kyth-dynamic-lock.json")


def load_dynamic_lock_config() -> dict:
    config = load_json_config(_DYNAMIC_LOCK_CONFIG, default={})
    return config if isinstance(config, dict) else {}


_load_dynamic_lock_config = load_dynamic_lock_config


def save_dynamic_lock_config(config: dict) -> None:
    save_json_config(_DYNAMIC_LOCK_CONFIG, config, mode=0o600)


_save_dynamic_lock_config = save_dynamic_lock_config


def kdeconnect_devices() -> list[dict]:
    if shutil.which("kdeconnect-cli") is None:
        return []
    _run_command(["kdeconnect-cli", "--refresh"], timeout=8)
    all_result = _run_command(
        ["kdeconnect-cli", "--list-devices", "--id-name-only"], timeout=12,
    )
    available_result = _run_command(
        ["kdeconnect-cli", "--list-available", "--id-only"], timeout=12,
    )
    if all_result is None or all_result.returncode != 0:
        return []
    available = set()
    if available_result is not None and available_result.returncode == 0:
        available = {
            line.strip() for line in available_result.stdout.splitlines() if line.strip()
        }
    devices = []
    for row in all_result.stdout.splitlines():
        parts = row.strip().split(maxsplit=1)
        if not parts:
            continue
        device_id = parts[0]
        devices.append({
            "id": device_id,
            "name": parts[1] if len(parts) > 1 else device_id,
            "reachable": device_id in available,
        })
    return sorted(devices, key=lambda item: item["name"].lower())


_kdeconnect_devices = kdeconnect_devices


def run_kdeconnect_action(device_id: str, action: str) -> tuple[bool, str]:
    result = _run_command(
        ["kdeconnect-cli", "--device", device_id, action], timeout=20,
    )
    if result is None:
        return False, "KDE Connect did not respond."
    detail = (result.stdout or result.stderr).strip()
    return result.returncode == 0, detail


_run_kdeconnect_action = run_kdeconnect_action


def mount_kdeconnect_device(device_id: str) -> tuple[bool, str]:
    mounted, detail = run_kdeconnect_action(device_id, "--mount")
    if not mounted:
        return False, detail
    result = _run_command(
        ["kdeconnect-cli", "--device", device_id, "--get-mount-point"], timeout=12,
    )
    if result is None or result.returncode != 0 or not result.stdout.strip():
        return False, "The device connected, but its file location was not reported."
    return True, result.stdout.strip()


_mount_kdeconnect_device = mount_kdeconnect_device


def send_kdeconnect_sms(
    device_id: str, destination: str, message: str,
) -> tuple[bool, str]:
    result = _run_command([
        "kdeconnect-cli", "--device", device_id,
        "--send-sms", message, "--destination", destination,
    ], timeout=30)
    if result is None:
        return False, "KDE Connect did not respond."
    detail = (result.stdout or result.stderr).strip()
    return result.returncode == 0, detail


_send_kdeconnect_sms = send_kdeconnect_sms


def configure_dynamic_lock_service(enabled: bool) -> tuple[bool, str]:
    helper = "/usr/bin/kyth-dynamic-lock"
    unit = "/usr/lib/systemd/user/kyth-dynamic-lock.service"
    if not os.path.exists(helper) or not os.path.exists(unit):
        return False, "Dynamic Lock will be available after the next KythOS update and restart."
    _run_command(["systemctl", "--user", "daemon-reload"], timeout=20)
    action = "enable" if enabled else "disable"
    result = _run_command(
        ["systemctl", "--user", action, "--now", "kyth-dynamic-lock.service"],
        timeout=30,
    )
    if result is None or result.returncode != 0:
        detail = "" if result is None else (result.stderr or result.stdout).strip()
        return False, detail or "Could not update the Dynamic Lock service."
    return True, "Dynamic Lock is on." if enabled else "Dynamic Lock is off."


_configure_dynamic_lock_service = configure_dynamic_lock_service
