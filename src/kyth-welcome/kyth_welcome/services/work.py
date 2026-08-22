"""Work setup helpers — Microsoft 365 shortcuts, fonts, Outlook PST import.

Pure stdlib (plus optional readpst). No Qt.
"""
from __future__ import annotations

import glob
import os
import shlex
from pathlib import Path
from typing import Callable

from kyth_welcome.services.command import run_sync

from .gaming import _find_ntfs_drives
from .browser_apps import chromium_app_window_command

WORK_APPS = [
    ("org.libreoffice.LibreOffice", "LibreOffice",
     "Writer, Calc, and Impress — opens and saves Word, Excel, and PowerPoint files."),
    ("eu.betterbird.Betterbird", "Betterbird",
     "Desktop email, calendar, and contacts — connects to Microsoft 365, Gmail, and IMAP accounts."),
]

M365_APPS = [
    ("Outlook",    "https://outlook.office.com/mail/",               "Email and calendar"),
    ("Word",       "https://office.live.com/start/Word.aspx",       "Documents"),
    ("Excel",      "https://office.live.com/start/Excel.aspx",      "Spreadsheets"),
    ("PowerPoint", "https://office.live.com/start/PowerPoint.aspx", "Presentations"),
    ("OneNote",    "https://www.onenote.com/notebooks",              "Notes"),
    ("Teams",      "https://teams.microsoft.com/",                   "Chat and meetings"),
]

MS_FONTS_DIR = os.path.expanduser("~/.local/share/fonts/msttcorefonts")
PST_IMPORT_DIR = os.path.expanduser("~/Documents/Outlook Import")

# Underscore aliases for page import style
_WORK_APPS = WORK_APPS
_M365_APPS = M365_APPS
_MS_FONTS_DIR = MS_FONTS_DIR
_PST_IMPORT_DIR = PST_IMPORT_DIR


def ms_fonts_installed() -> bool:
    try:
        return any(entry.lower().endswith(".ttf") for entry in os.listdir(MS_FONTS_DIR))
    except OSError:
        return False


_ms_fonts_installed = ms_fonts_installed


def m365_icon(name: str) -> str:
    icon = f"kyth-m365-{name.lower()}"
    if os.path.exists(f"/usr/share/icons/hicolor/scalable/apps/{icon}.svg"):
        return icon
    return "internet-web-browser"


_m365_icon = m365_icon


def m365_desktop_entry(name: str, url: str, comment: str) -> str | None:
    launch = chromium_app_window_command(url)
    if launch is None:
        return None
    cmd, wm_class = launch
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name} (Microsoft 365)\n"
        f"Comment={comment}\n"
        f"Exec={shlex.join(cmd)}\n"
        f"Icon={m365_icon(name)}\n"
        "Categories=Office;\n"
        f"StartupWMClass={wm_class}\n"
    )


_m365_desktop_entry = m365_desktop_entry


def create_m365_shortcuts() -> int:
    """Write launcher .desktop entries for the Microsoft 365 web apps."""
    apps_dir = os.path.expanduser("~/.local/share/applications")
    written = 0
    try:
        os.makedirs(apps_dir, exist_ok=True)
    except OSError:
        return 0
    for name, url, comment in M365_APPS:
        entry = m365_desktop_entry(name, url, comment)
        if entry is None:
            continue
        path = os.path.join(apps_dir, f"kyth-m365-{name.lower()}.desktop")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(entry)
            written += 1
        except OSError:
            pass
    return written


_create_m365_shortcuts = create_m365_shortcuts


def scan_for_pst_files() -> list[str]:
    """Look for Outlook .pst archives in the usual profile locations."""
    found: list[str] = []
    roots = [d.get("mount") for d in _find_ntfs_drives() if d.get("mount")]
    roots.append(os.path.expanduser("~"))
    for root in roots:
        for pattern in (
            "Users/*/Documents/Outlook Files/*.pst",
            "Users/*/Documents/*.pst",
            "Users/*/AppData/Local/Microsoft/Outlook/*.pst",
            "Documents/*.pst",
            "Downloads/*.pst",
        ):
            found.extend(glob.glob(os.path.join(root, pattern)))
    return sorted(set(found))


_scan_for_pst_files = scan_for_pst_files


def convert_pst(path: str) -> tuple[bool, str]:
    """Convert a .pst to mbox folders under ~/Documents/Outlook Import."""
    name = os.path.splitext(os.path.basename(path))[0]
    dest = os.path.join(PST_IMPORT_DIR, name)
    try:
        os.makedirs(dest, exist_ok=True)
        r = run_sync(
            ["readpst", "-r", "-o", dest, path],
            capture_output=True, text=True, timeout=3600, check=False,
        )
    except FileNotFoundError:
        return False, "readpst is not installed — update KythOS to the latest image."
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        return False, str(exc)
    if r.returncode != 0:
        return False, (r.stderr or r.stdout).strip() or "Conversion failed."
    return True, dest


_convert_pst = convert_pst


def refresh_m365_shortcuts() -> None:
    """Rewrite existing shortcuts whose generated content changed."""
    apps_dir = os.path.expanduser("~/.local/share/applications")
    for name, url, comment in M365_APPS:
        path = os.path.join(apps_dir, f"kyth-m365-{name.lower()}.desktop")
        if not os.path.exists(path):
            continue
        entry = m365_desktop_entry(name, url, comment)
        if entry is None:
            continue
        try:
            with open(path, "r", encoding="utf-8") as fh:
                current = fh.read()
            if current != entry:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(entry)
        except OSError:
            pass


_refresh_m365_shortcuts = refresh_m365_shortcuts


def m365_shortcuts_present() -> bool:
    apps_dir = os.path.expanduser("~/.local/share/applications")
    return all(
        os.path.exists(os.path.join(apps_dir, f"kyth-m365-{name.lower()}.desktop"))
        for name, _, _ in M365_APPS
    )


_m365_shortcuts_present = m365_shortcuts_present


WORK_FLATPAKS = (
    ("com.brave.Browser", "Brave"),
    ("org.libreoffice.LibreOffice", "LibreOffice"),
)


def work_ready_checks() -> list[tuple[str, Callable[[], tuple[bool, str]]]]:
    """Return (label, check_fn) pairs. check_fn → (ok, msg). All offline-safe."""
    checks: list[tuple[str, Callable[[], tuple[bool, str]]]] = []
    try:
        from .flatpak import _is_flatpak_installed
        for app_id, name in WORK_FLATPAKS:
            checks.append(
                (name.lower(), lambda i=app_id, n=name: (
                    True, f"{n} installed",
                ) if _is_flatpak_installed(i) else (False, f"{n} not installed"))
            )
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001
        pass
    checks.append(("fonts", _fonts_check))
    checks.append(("cloud", _cloud_check))
    checks.append(("print", _printer_check))
    return checks


def _fonts_check() -> tuple[bool, str]:
    try:
        from kyth_shared.system.fonts_ready import fonts_ready
        return fonts_ready()
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001
        return False, str(exc)


def _cloud_check() -> tuple[bool, str]:
    conf = Path.home() / ".config" / "rclone" / "rclone.conf"
    if conf.is_file():
        return True, "rclone config present"
    return True, "rclone/cloud optional — configure in Hub Cloud if needed"


def _printer_check() -> tuple[bool, str]:
    if Path("/run/cups/cups.sock").exists():
        return True, "CUPS is running"
    return True, "printer optional — add one from Hub Work or system-config-printer"


def _app_installed(app_id: str) -> bool:
    try:
        from .flatpak import _is_flatpak_installed
        return bool(_is_flatpak_installed(app_id))
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001
        return False


def _install_work_flatpak(app_id: str) -> tuple[bool, str]:
    try:
        result = run_sync(
            [
                "flatpak", "install", "-y", "--noninteractive", "--or-update",
                "flathub", app_id,
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    except FileNotFoundError:
        return False, "flatpak is not installed"
    except (OSError, ValueError, RuntimeError) as exc:
        return False, str(exc)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()[:200]
        if "Network" in err or "network" in err or "offline" in err.lower():
            return False, "offline — will apply when networked"
        return False, err or f"flatpak install exited {result.returncode}"
    return True, "installed"


def orchestrate_work_setup(dry_run: bool = False) -> tuple[bool, str]:
    """Install Brave/LibreOffice if missing, refresh M365 shortcuts, report fonts/cloud/printer."""
    notes: list[str] = []
    failed: list[str] = []
    for app_id, name in WORK_FLATPAKS:
        if _app_installed(app_id):
            notes.append(f"{name}: already installed")
            continue
        if dry_run:
            notes.append(f"{name}: would install from Flathub")
            continue
        ok, msg = _install_work_flatpak(app_id)
        (notes if ok else failed).append(f"{name}: {msg}")
    if dry_run:
        notes.append("M365 shortcuts: would refresh")
    else:
        try:
            written = create_m365_shortcuts()
            notes.append(f"M365 shortcuts: {written} written")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001
            notes.append(f"M365 shortcuts: {exc}")
    font_ok, font_msg = _fonts_check()
    notes.append(f"fonts: {font_msg}" + ("" if font_ok else " (Hub Work → MS fonts)"))
    _ok, cloud_msg = _cloud_check()
    notes.append(f"cloud: {cloud_msg}")
    _ok, print_msg = _printer_check()
    notes.append(f"print: {print_msg}")
    summary = "; ".join(failed + notes) if failed else "; ".join(notes)
    if dry_run:
        return True, "dry-run ok: " + summary
    return not failed, summary
