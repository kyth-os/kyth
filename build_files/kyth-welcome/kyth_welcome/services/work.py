"""Work setup helpers — Microsoft 365 shortcuts, fonts, Outlook PST import.

Pure stdlib (plus optional readpst). No Qt.
"""
from __future__ import annotations

import glob
import os
import shlex
import subprocess

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
        r = subprocess.run(
            ["readpst", "-r", "-o", dest, path],
            capture_output=True, text=True, timeout=3600, check=False,
        )
    except FileNotFoundError:
        return False, "readpst is not installed — update KythOS to the latest image."
    except Exception as exc:
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
