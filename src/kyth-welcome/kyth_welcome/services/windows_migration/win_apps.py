"""Scan mounted Windows Program Files for installed app folder names (pure)."""
from __future__ import annotations

import os

# Folder names that are Windows itself or generic — not useful for app mapping
_SKIP_FOLDERS = {
    "common files", "internet explorer", "windows nt", "windows defender",
    "windowsapps", "windows mail", "windows media player", "windows photo viewer",
    "microsoft", "microsoft shared", "reference assemblies", "msbuild",
    "windows kits", "windows security",
}


def scan_windows_program_files(partitions: list[dict]) -> list[str]:
    """Return sorted unique Program Files folder basenames from mounted NTFS partitions."""
    names: set[str] = set()
    for p in partitions or []:
        mp = p.get("mountpoint") or ""
        if not mp or p.get("is_bitlocker") or p.get("is_dirty") or p.get("is_hibernated"):
            continue
        for rel in ("Program Files", "Program Files (x86)"):
            base = os.path.join(mp, rel)
            try:
                for entry in os.listdir(base):
                    low = entry.lower()
                    if low in _SKIP_FOLDERS or entry.startswith("."):
                        continue
                    full = os.path.join(base, entry)
                    if os.path.isdir(full):
                        names.add(entry.strip())
            except OSError:
                continue
    return sorted(names, key=lambda s: s.lower())


def map_to_familiar(folder_names: list[str], familiar_apps: list[tuple[str, str, str]]) -> list[dict]:
    """Map each Windows folder name to a familiar app entry via find_familiar_app_match."""
    from ..software import find_familiar_app_match
    mapped: list[dict] = []
    for name in folder_names:
        m = find_familiar_app_match(name, familiar_apps)
        if m:
            mapped.append({"windows_name": name, "match": m[0], "desc": m[1], "app_id": m[2]})
        else:
            mapped.append({"windows_name": name, "match": None, "desc": "No curated Linux equivalent yet — search Flathub or use Bottles only as last resort.", "app_id": ""})
    return mapped
