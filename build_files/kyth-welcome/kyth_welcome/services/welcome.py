"""Home / first-week follow-up probes (pure)."""
from __future__ import annotations

import os
import time

from .process import _run_command
from .software import _is_flatpak_installed

_FIRST_WEEK_DISMISS = os.path.expanduser("~/.config/kyth-first-week-done")
_FIRST_BOOT_MARKERS = (
    "/var/lib/kyth/default-flatpaks-v8-done",
    os.path.expanduser("~/.config/kyth-welcome-done"),
)
FIRST_WEEK_MIN_DAYS = 2
FIRST_WEEK_MAX_DAYS = 30


def path_exists(path: str) -> bool:
    return os.path.exists(os.path.expanduser(path))


def controller_seen() -> bool:
    for path in ("/dev/input/by-id", "/dev/input/by-path"):
        try:
            names = os.listdir(path)
        except OSError:
            continue
        if any(token in name.lower() for name in names for token in ("joystick", "gamepad", "controller")):
            return True
    return False


def kdeconnect_configured() -> bool:
    if path_exists("~/.config/kdeconnect"):
        return True
    result = _run_command(["kdeconnect-cli", "--list-devices"], timeout=6)
    return bool(result and result.returncode == 0 and result.stdout.strip())


def cloud_storage_configured() -> bool:
    return path_exists("~/.config/kyth-cloud-sync.json") or path_exists("~/.config/rclone/rclone.conf")


def printer_configured() -> bool:
    result = _run_command(["lpstat", "-v"], timeout=5)
    return bool(result and result.returncode == 0 and result.stdout.strip())


def browser_integration_native_ready() -> bool:
    result = _run_command(["rpm", "-q", "plasma-browser-integration"], timeout=5)
    if result and result.returncode == 0:
        return True
    return path_exists("/usr/bin/plasma-browser-integration-host")


def first_week_days() -> int | None:
    """Days since first boot, or None when unknown or already dismissed."""
    if os.path.exists(_FIRST_WEEK_DISMISS):
        return None
    stamps = []
    for marker in _FIRST_BOOT_MARKERS:
        try:
            stamps.append(os.stat(marker).st_mtime)
        except OSError:
            continue
    if not stamps:
        return None
    age = (time.time() - min(stamps)) / 86400.0
    return int(age)


def first_week_items() -> list[tuple[str, bool, str]]:
    """Return (label, done, page_key) checklist for the first-week card."""
    return [
        ("Install a game launcher", _is_flatpak_installed("com.valvesoftware.Steam"), "Gaming"),
        ("Pair a controller", controller_seen(), "Controllers"),
        ("Connect phone (KDE Connect)", kdeconnect_configured(), "Move Files"),
        ("Set up cloud storage", cloud_storage_configured(), "Cloud Storage"),
        ("Add a printer", printer_configured(), "Repair"),
        ("Browser integration", browser_integration_native_ready(), "Work Setup"),
    ]


# Underscore aliases
_path_exists = path_exists
_controller_seen = controller_seen
_kdeconnect_configured = kdeconnect_configured
_cloud_storage_configured = cloud_storage_configured
_printer_configured = printer_configured
_browser_integration_native_ready = browser_integration_native_ready
_first_week_days = first_week_days
_FIRST_WEEK_DISMISS = _FIRST_WEEK_DISMISS
_FIRST_WEEK_MIN_DAYS = FIRST_WEEK_MIN_DAYS
_FIRST_WEEK_MAX_DAYS = FIRST_WEEK_MAX_DAYS
