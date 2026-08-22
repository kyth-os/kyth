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


@dataclass(frozen=True)
class PulseNextStep:
    """Single primary action for Pulse home — one thing, not a card dump."""

    title: str
    body: str
    button: str
    target: str
    severity: str
    orb_label: str
    orb_caption: str


def pulse_greeting(hour: int, hostname: str) -> str:
    """Time-of-day greeting. Hostname is the machine name, not a person."""
    if hour < 12:
        prefix = "Good morning"
    elif hour < 17:
        prefix = "Good afternoon"
    else:
        prefix = "Good evening"
    name = (hostname or "This PC").strip() or "This PC"
    return f"{prefix}, {name}"


def pulse_next_step(
    *,
    staged: bool = False,
    rollback: bool = False,
    windows_found: bool = False,
    ntfs_library: bool = False,
    setup_incomplete: bool = False,
    setup_target: str = "Hardware",
    repair_needed: bool = False,
    profile: str = "everyday",
) -> PulseNextStep:
    """Pick the one Pulse action. Worse problems win."""
    if ntfs_library:
        return PulseNextStep(
            title="Steam library is on NTFS",
            body="Games on this drive will fail to launch. Proton needs a Linux disk.",
            button="Fix this now",
            target="Play",
            severity="warn",
            orb_label="ATTENTION",
            orb_caption="Games need a Linux disk",
        )
    if setup_incomplete:
        return PulseNextStep(
            title="Finish setup",
            body="A few first-boot steps are still open. Pick up whenever you are ready.",
            button="Resume",
            target=setup_target or "Hardware",
            severity="warn",
            orb_label="SETUP",
            orb_caption="A few steps are still open",
        )
    if staged:
        return PulseNextStep(
            title="Update is staged",
            body="A new image is ready. Restart to apply it — rollback stays one click away.",
            button="Restart now",
            target="reboot",
            severity="warn",
            orb_label="RESTART",
            orb_caption="New image ready",
        )
    if repair_needed:
        return PulseNextStep(
            title="Guardian found something",
            body="A safe fix is ready. Review it before anything else.",
            button="Open Repair",
            target="Repair",
            severity="warn",
            orb_label="ATTENTION",
            orb_caption="A fix is ready",
        )
    if windows_found:
        return PulseNextStep(
            title="Windows disk detected",
            body="Bring files, saves, and familiar workflows over. Originals stay put.",
            button="Move in",
            target="Move In",
            severity="ok",
            orb_label="CLEAR",
            orb_caption="Bring files over when ready",
        )
    if rollback:
        return PulseNextStep(
            title="Rollback is ready",
            body="Yesterday's image is saved. One click if an update misbehaves.",
            button="Review updates",
            target="Update",
            severity="ok",
            orb_label="CLEAR",
            orb_caption="Guardian watching",
        )
    dest = "Play" if profile == "gaming" else "Apps"
    return PulseNextStep(
        title="This PC is quiet",
        body="Atomic updates, one-click rollback. Nothing needs you right now.",
        button=f"Open {dest}",
        target=dest,
        severity="ok",
        orb_label="CLEAR",
        orb_caption="Guardian watching",
    )


PLAY_LAUNCHERS: tuple[tuple[str, str], ...] = (
    ("Steam", "com.valvesoftware.Steam"),
    ("Heroic", "com.heroicgameslauncher.hgl"),
    ("Lutris", "net.lutris.Lutris"),
    ("Bottles", "com.usebottles.bottles"),
)


def play_launcher_states(installed: dict[str, bool]) -> tuple[tuple[str, bool], ...]:
    """Name + installed flag for the Play launcher row."""
    return tuple((name, bool(installed.get(app_id))) for name, app_id in PLAY_LAUNCHERS)


def this_pc_timeline(
    *,
    branch: str = "",
    staged: bool = False,
    rollback: bool = False,
    rollback_when: str = "",
) -> tuple[tuple[str, str, str, str], ...]:
    """(key, title, body, state) for the This PC deployment timeline."""
    channel = (branch or "unknown").strip() or "unknown"
    staged_body = "New image ready · restart to apply" if staged else "No staged image"
    if rollback and rollback_when:
        rollback_body = rollback_when
    elif rollback:
        rollback_body = "One click to yesterday"
    else:
        rollback_body = "Appears after the first update"
    return (
        ("current", "Current", f"Kyth {channel} · healthy", "ok"),
        ("staged", "Staged", staged_body, "info" if staged else "dim"),
        ("rollback", "Rollback", rollback_body, "ok" if rollback else "dim"),
    )


MOVE_IN_JOURNEY: tuple[tuple[str, str, str, str], ...] = (
    ("files", "Files", "Copy documents, pictures, and downloads. Originals stay on the Windows disk.", "Move Files"),
    ("games", "Games", "Proton needs a Linux disk. Move Steam libraries off NTFS before you play.", "Play"),
    ("apps", "Apps", "Install familiar apps and reconnect cloud storage.", "Apps"),
    ("habits", "Muscle memory", "Shortcuts, phone link, and PowerToys-style tools.", "Move Files"),
)


def move_in_step(key: str) -> tuple[str, str, str, str]:
    for step in MOVE_IN_JOURNEY:
        if step[0] == key:
            return step
    return MOVE_IN_JOURNEY[0]


def move_in_active_step(*, ntfs_library: bool = False, windows_found: bool = False) -> str:
    """Pick the loudest Move In step from what we already know."""
    if ntfs_library:
        return "games"
    if windows_found:
        return "files"
    return "files"


MOVE_IN_CHECKLIST: tuple[tuple[str, str, str], ...] = (
    ("Bookmarks", "Bring browser bookmarks over.", "Move Files"),
    ("Fonts", "Copy familiar system fonts.", "Move Files"),
    ("Phone link", "Pair a phone for SMS and sharing.", "Move Files"),
    ("Cloud", "Reconnect OneDrive, Drive, or Dropbox.", "Cloud Storage"),
)


def pulse_dest_tiles(profile: str) -> tuple[tuple[str, str, str], ...]:
    """Destination tiles. Gaming leads with Play; Everyday leads with Apps."""
    play = ("Play", "Play", "Launch games and tune performance.")
    apps = ("Apps", "Apps", "Install apps and set up work.")
    this_pc = ("This PC", "This PC", "Health, updates, and hardware.")
    move_in = ("Move In", "Move In", "Bring files, saves, and shortcuts.")
    if profile == "gaming":
        return (play, apps, this_pc, move_in)
    return (apps, play, this_pc, move_in)


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
