"""User-owned AppImage discovery and uninstall helpers (pure)."""
from __future__ import annotations

import configparser
import os
import shlex


def is_user_appimage_path(path: str, home: str | None = None) -> bool:
    """True when `path` resolves to an existing .AppImage file under `home`."""
    if not path:
        return False
    home = os.path.realpath(os.path.expanduser(home or "~"))
    try:
        real = os.path.realpath(os.path.expanduser(path))
    except OSError:
        return False
    return (
        real.startswith(home + os.sep)
        and os.path.isfile(real)
        and os.path.basename(real).lower().endswith(".appimage")
    )


def appimage_entry_from_desktop_text(
    desktop_text: str, desktop_path: str, home: str | None = None
) -> dict[str, str] | None:
    """Parse a .desktop file's text for an Exec/TryExec line pointing at a
    user-owned AppImage; return the app entry dict page_software_installed.py
    lists, or None when the entry isn't a user AppImage launcher."""
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    try:
        parser.read_string(desktop_text)
    except Exception:
        return None
    if not parser.has_section("Desktop Entry"):
        return None
    entry = parser["Desktop Entry"]
    exec_line = entry.get("Exec", "")
    try_exec = entry.get("TryExec", "")
    candidates: list[str] = []
    for line in (exec_line, try_exec):
        if not line:
            continue
        try:
            parts = shlex.split(line)
        except ValueError:
            parts = line.split()
        candidates.extend(part for part in parts if ".AppImage" in part or ".appimage" in part)
    appimage_path = next((part for part in candidates if is_user_appimage_path(part, home)), "")
    if not appimage_path:
        return None
    appimage_path = os.path.realpath(os.path.expanduser(appimage_path))
    return {
        "kind": "appimage",
        "app_id": appimage_path,
        "name": entry.get("Name", "") or os.path.basename(appimage_path),
        "origin": "AppImage",
        "installation": "user file",
        "path": appimage_path,
        "desktop_path": desktop_path,
        "icon": entry.get("Icon", ""),
    }


def uninstall_app_detail(app: dict[str, str]) -> str:
    if app["kind"] == "appimage":
        launcher = " · launcher" if app.get("desktop_path") else ""
        return f"{app['path']} · AppImage{launcher}"
    return f"{app['app_id']} · {app['installation']} install · {app['origin']}"


def safe_home_targets(paths: list[str], home: str | None = None) -> list[str]:
    """Resolve `paths` and keep only those that stay under `home` — the
    uninstall delete list must never include a path a crafted .desktop entry
    or symlink could point outside the user's own files."""
    home = os.path.realpath(os.path.expanduser(home or "~"))
    safe: list[str] = []
    for target in paths:
        real = os.path.realpath(os.path.expanduser(target))
        if real.startswith(home + os.sep):
            safe.append(real)
    return safe


def flatpak_uninstall_command(app_id: str, installation: str) -> list[str]:
    cmd = ["flatpak", "uninstall", "-y"]
    if installation == "user":
        cmd.append("--user")
    elif installation == "system":
        cmd.append("--system")
    cmd.append(app_id)
    return cmd
