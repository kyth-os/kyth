"""Windows Takeout — unified launcher + cloud + browser inventory (pure, no Qt)."""
from __future__ import annotations

import os

# Display names for launcher keys used in windows_partitions.launcher_paths
_LAUNCHER_DISPLAY: dict[str, str] = {
    "epic": "Epic Games",
    "gog": "GOG Galaxy",
    "ubisoft": "Ubisoft Connect",
    "battlenet": "Battle.net",
    "ea": "EA / Origin",
}

# Where each launcher is re-installed on KythOS (Heroic / Lutris / Bottles)
_LAUNCHER_REINSTALL_HINT: dict[str, str] = {
    "epic": "Heroic (Epic) — System Hub → Gaming → Launchers",
    "gog": "Heroic (GOG) — System Hub → Gaming → Launchers",
    "ubisoft": "Lutris / Ubisoft Connect — System Hub → Gaming → Launchers",
    "battlenet": "Lutris / Bottles — System Hub → Gaming → Launchers",
    "ea": "Lutris / EA App — System Hub → Gaming → Launchers",
}


def summarize_takeout(partitions: list[dict]) -> dict:
    """Build a Takeout summary from probed partitions.

    Returns dict with counts and per-item lists safe for UI rendering.
    Never touches widgets or spawns processes — purely derives from
    already-probed partition dicts.
    """
    steam_count = sum(len(p.get("steam_paths") or []) for p in partitions)
    launcher_items: list[dict] = []
    for p in partitions:
        for key, paths in (p.get("launcher_paths") or {}).items():
            for pp in paths:
                launcher_items.append({
                    "launcher": key,
                    "display": _LAUNCHER_DISPLAY.get(key, key),
                    "path": pp,
                    "device": p.get("device", ""),
                    "hint": _LAUNCHER_REINSTALL_HINT.get(key, "Reinstall via Heroic/Lutris"),
                })
    launcher_count = len(launcher_items)

    profiles = [prof for p in partitions for prof in (p.get("user_profiles") or [])]
    profile_count = len(profiles)

    # Folders that exist on disk and are worth copying
    folder_hits: list[dict] = []
    for p in partitions:
        for prof in (p.get("user_profiles") or []):
            for folder in (prof.get("folders") or []):
                # Only user-data folders, skip browser internals
                if folder in ("Desktop", "Documents", "Pictures", "Music", "Videos", "Saved Games", "Downloads"):
                    folder_hits.append({"user": prof["name"], "folder": folder, "profile": prof["path"]})
                elif folder.startswith("OneDrive"):
                    folder_hits.append({"user": prof["name"], "folder": folder, "profile": prof["path"], "onedrive": True})

    has_onedrive = any(p.get("has_onedrive") for p in partitions)
    browser_profiles = [b for p in partitions for b in (p.get("browser_profiles") or [])]
    browser_count = len(browser_profiles)

    # Saves — defer to extras scanner, but expose hint count here (0 until extras scan completes)
    # Callers can enrich with extras results via enrich_with_extras().
    dirty = sum(1 for p in partitions if p.get("is_dirty") or p.get("is_hibernated"))
    locked = sum(1 for p in partitions if p.get("is_bitlocker"))
    readable = sum(1 for p in partitions if not p.get("is_bitlocker") and not p.get("is_dirty") and not p.get("is_hibernated") and p.get("mountpoint"))

    # Simple readiness score 0-5 biased toward user comfort
    score = 0
    if readable:
        score += 1
    if profile_count:
        score += 1
    if steam_count or launcher_count:
        score += 1
    if browser_count:
        score += 1
    if has_onedrive:
        score += 1
    score = min(5, score)

    return {
        "steam_count": steam_count,
        "launcher_count": launcher_count,
        "launcher_items": launcher_items,
        "profile_count": profile_count,
        "folder_hits": folder_hits,
        "has_onedrive": has_onedrive,
        "browser_count": browser_count,
        "browser_profiles": browser_profiles,
        "dirty_count": dirty,
        "locked_count": locked,
        "readable_count": readable,
        "score": score,
    }


def enrich_with_extras(summary: dict, extras_results: list[dict]) -> dict:
    """Merge saves/wallpaper/fonts extras into a Takeout summary (non-destructive)."""
    try:
        saves = 0
        wallpapers = 0
        fonts = 0
        for item in extras_results or []:
            saves += len(item.get("saves") or [])
            if item.get("wallpaper"):
                wallpapers += 1
            fonts += len(item.get("fonts") or [])
        summary = dict(summary)
        summary["saves_count"] = saves
        summary["wallpapers_count"] = wallpapers
        summary["fonts_count"] = fonts
    except Exception:
        pass
    return summary


def takeout_checklist(summary: dict) -> list[dict]:
    """Return ordered checklist rows for the Takeout wizard UI."""
    rows: list[dict] = []
    if summary.get("steam_count"):
        rows.append({"status": "ok", "title": "Steam libraries", "detail": f"{summary['steam_count']} Steam folder(s) found — copy to Linux disk via Gaming → Migration (don't add NTFS as library)."})
    if summary.get("launcher_count"):
        rows.append({"status": "ok", "title": "Other launchers", "detail": f"{summary['launcher_count']} launcher folder(s) found — {', '.join(sorted(set(i['display'] for i in summary['launcher_items'])))} — reinstall launchers on KythOS, then restore game saves."})
    if summary.get("profile_count"):
        rows.append({"status": "ok", "title": "User files", "detail": f"{summary['profile_count']} Windows user profile(s) — Documents/Pictures/etc. appear in Copy My Files below."})
    if summary.get("has_onedrive"):
        rows.append({"status": "ok", "title": "OneDrive", "detail": "OneDrive folders found — after copying, set up sync via Cloud Storage → OneDrive (rclone). Files-On-Demand placeholders need to be made Available Offline on Windows first."})
    if summary.get("browser_count"):
        rows.append({"status": "ok", "title": "Browser data", "detail": f"{summary['browser_count']} browser profile(s) — bookmarks import below; passwords come via browser Sync (Chrome/Firefox/Edge sign-in)."})
    if summary.get("dirty_count"):
        rows.append({"status": "warn", "title": "Drive state", "detail": f"{summary['dirty_count']} drive(s) are hibernated/dirty — boot Windows → full Shut Down, then rescan."})
    if summary.get("locked_count"):
        rows.append({"status": "warn", "title": "BitLocker", "detail": f"{summary['locked_count']} drive(s) locked — use Unlock Drive with recovery key (aka.ms/myrecoverykey)."})
    saves = summary.get("saves_count")
    if isinstance(saves, int) and saves > 0:
        rows.append({"status": "ok", "title": "Game saves", "detail": f"{saves} save location(s) found — Copy All Found Saves below, then restore placements with Ludusavi."})
    return rows


__all__ = ["summarize_takeout", "enrich_with_extras", "takeout_checklist"]
