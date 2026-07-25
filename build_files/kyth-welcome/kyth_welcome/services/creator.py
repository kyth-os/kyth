"""Creator-tool discovery helpers."""

from __future__ import annotations

import glob
import os

from .flatpak import is_installed
from .process import _command_stdout

DAVINCI_APP_IDS = (
    "com.blackmagic.Resolve",
    "com.blackmagic.ResolveStudio",
    "com.blackmagicdesign.resolve",
)


def davinci_flatpak_app_id() -> str | None:
    """Return the installed DaVinci Resolve Flatpak ID, if any."""
    return next((app_id for app_id in DAVINCI_APP_IDS if is_installed(app_id)), None)


def davinci_download_dir() -> str:
    """Return the user's existing XDG download directory."""
    candidate = _command_stdout(["xdg-user-dir", "DOWNLOAD"])
    if candidate:
        candidate = os.path.expanduser(candidate)
        if os.path.isdir(candidate):
            return candidate
    return os.path.expanduser("~/Downloads")


def davinci_zip_candidates() -> list[str]:
    """Find likely DaVinci Linux downloads, newest first."""
    roots: list[str] = []
    for candidate in (davinci_download_dir(), os.path.expanduser("~/Downloads")):
        expanded = os.path.abspath(os.path.expanduser(candidate))
        if os.path.isdir(expanded) and expanded not in roots:
            roots.append(expanded)

    matches: dict[str, float] = {}
    patterns = (
        "DaVinci_Resolve*_Linux.zip",
        "DaVinci_Resolve_Studio*_Linux.zip",
        "*DaVinci*Resolve*Linux*.zip",
    )
    for root in roots:
        for pattern in patterns:
            for base in (root, os.path.join(root, "*")):
                for path in glob.iglob(os.path.join(base, pattern)):
                    if not os.path.isfile(path) or path in matches:
                        continue
                    try:
                        matches[path] = os.path.getmtime(path)
                    except OSError:
                        matches[path] = 0
    return sorted(matches, key=lambda item: (matches[item], item.lower()), reverse=True)


# Compatibility names for downstream imports while the public API settles.
_davinci_flatpak_app_id = davinci_flatpak_app_id
_davinci_download_dir = davinci_download_dir
_davinci_zip_candidates = davinci_zip_candidates
