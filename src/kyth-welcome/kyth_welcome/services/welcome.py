"""Home / first-week follow-up probes (pure)."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass

from .process import run_command

_FIRST_WEEK_DISMISS = os.path.expanduser("~/.config/kyth-first-week-done")
FIRST_WEEK_MIN_DAYS = 2
FIRST_WEEK_MAX_DAYS = 30

# (label, copy, Hub page key) — gather_first_week_checklist() fills `done`.
FIRST_WEEK_ITEMS: tuple[tuple[str, str, str], ...] = (
    ("Default Apps", "Steam, bottles, and flatpaks installed.", "App Store"),
    ("Browser", "Brave browser set up.", "App Store"),
    ("Browser Integration", "Plasma desktop connection enabled.", "App Store"),
    ("Steam Integration", "Steam libraries and backups set up.", "Gaming"),
    ("Controller Setup", "Game controllers detected.", "Controllers"),
    ("KDE Connect", "Phone pairing and notifications set up.", "Move Files"),
    ("Cloud Sync", "rclone/cloud sync initialized.", "Cloud Storage"),
    ("Printers", "Local or network printers configured.", "Hardware"),
    ("Rollback Safety", "Previous builds cached for rollback.", "Update"),
)


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
    result = run_command(["kdeconnect-cli", "--list-devices"], timeout=6)
    return bool(result and result.returncode == 0 and result.stdout.strip())


def cloud_storage_configured() -> bool:
    return path_exists("~/.config/kyth-cloud-sync.json") or path_exists("~/.config/rclone/rclone.conf")


def printer_configured() -> bool:
    result = run_command(["lpstat", "-v"], timeout=5)
    return bool(result and result.returncode == 0 and result.stdout.strip())


def browser_integration_native_ready() -> bool:
    if path_exists("/usr/bin/plasma-browser-integration-host"):
        return True
    result = run_command(["rpm", "-q", "plasma-browser-integration"], timeout=5)
    return bool(result and result.returncode == 0)


def _first_boot_markers() -> list[str]:
    markers = [os.path.expanduser("~/.config/kyth-welcome-done")]
    try:
        from kyth_shared.session import default_flatpaks_sentinel

        sentinel = default_flatpaks_sentinel()
    except (OSError, ImportError):
        sentinel = None
    if sentinel is not None:
        markers.append(str(sentinel))
    return markers


def first_week_days() -> int | None:
    """Days since first boot, or None when unknown or already dismissed."""
    if os.path.exists(_FIRST_WEEK_DISMISS):
        return None
    stamps = []
    for marker in _first_boot_markers():
        try:
            stamps.append(os.stat(marker).st_mtime)
        except OSError:
            continue
    if not stamps:
        return None
    age = (time.time() - min(stamps)) / 86400.0
    return int(age)


def gather_first_week_checklist() -> list[bool]:
    """Subprocess-backed first-week flags — run off the GUI thread."""
    from kyth_shared.session import default_flatpaks_done

    from .bootc import has_rollback_deployment
    from .flatpak import is_installed

    return [
        default_flatpaks_done(),
        is_installed("com.brave.Browser"),
        browser_integration_native_ready(),
        is_installed("com.valvesoftware.Steam"),
        controller_seen(),
        kdeconnect_configured(),
        cloud_storage_configured(),
        printer_configured(),
        has_rollback_deployment(),
    ]


@dataclass(frozen=True)
class HomeHeroView:
    """What page_welcome.py's hero banner and recommended-action card should
    show, driven purely by system state — no Qt, so the decision tree is
    testable without a display."""
    pill_text: str
    pill_object_name: str
    rec_text: str
    rec_btn_label: str
    rec_target: str


def home_hero_view(staged: bool, rollback: bool, windows_found: bool) -> HomeHeroView:
    if staged:
        pill_text, pill_object_name = "RESTART REQUIRED", "glowing-pill-warn"
    else:
        pill_text, pill_object_name = "SYSTEM UP-TO-DATE", "glowing-pill-ok"

    if staged:
        rec_text = "Restart to apply staged updates."
        rec_btn_label = "Restart Now"
        rec_target = "reboot"
    elif rollback:
        rec_text = "Previous build is saved in case of bugs."
        rec_btn_label = "Manage Rollbacks"
        rec_target = "Update"
    elif windows_found:
        rec_text = "Import games and documents from Windows."
        rec_btn_label = "Transfer Files"
        rec_target = "Move Files"
    else:
        rec_text = "System is up-to-date. Ready for configuration."
        rec_btn_label = "Configure Games"
        rec_target = "Gaming"

    return HomeHeroView(pill_text, pill_object_name, rec_text, rec_btn_label, rec_target)


def home_categories(*, has_nvidia: bool):
    """Return home navigation content independently of Qt construction."""
    categories = [
        (("applications-games", "input-gaming"), "◉", "Games", [
            ("Set up game launchers", "Gaming"), ("Tune performance", "Performance"),
            ("Check if your games work", "Compatibility"), ("Connect a controller", "Controllers"),
        ]),
        (("plasmadiscover", "applications-all"), "⬡", "Apps", [
            ("Browse and install apps", "App Store"), ("Move files and saves", "Move Files"),
        ]),
        (("computer", "computer-laptop"), "◈", "System & Security", [
            ("Check for updates", "Update"), ("View hardware and devices", "Hardware"),
            ("Run a health report", "Diagnostics"), ("Fix problems", "Repair"),
        ]),
        (("folder-network", "network-workgroup"), "◫", "Network & Internet", [
            ("Connect to a VPN", "VPN"), ("Map network shares", "Network Shares"),
            ("Set up cloud storage", "Cloud Storage"),
        ]),
    ]
    advanced = [("Manage NVIDIA drivers", "NVIDIA")] if has_nvidia else []
    advanced.extend((("Choose a kernel", "Kernel"), ("Pick an update channel", "Channels")))
    categories.append((("cpu", "applications-system"), "◌", "Advanced", advanced))
    return categories


def visible_category_indexes(profile: str, games_flags: list[bool]) -> list[int]:
    return [i for i, games in enumerate(games_flags) if profile == "gaming" or not games]


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
