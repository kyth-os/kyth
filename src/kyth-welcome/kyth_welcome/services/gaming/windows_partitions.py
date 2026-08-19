"""Windows partition probe for game library migration."""
from __future__ import annotations

import logging
import os
from kyth_welcome.services.command import run_sync

_logger = logging.getLogger(__name__)


def _probe_windows_partitions() -> list[dict]:
    """Scan for NTFS partitions, check dirty/hibernated state, find Steam dirs.
    Returns list of dicts safe to call from a non-main thread."""
    import json as _json
    try:
        result = run_sync(
            ["lsblk", "--json", "-o", "NAME,FSTYPE,LABEL,MOUNTPOINTS,SIZE,PATH"],
            capture_output=True, text=True, timeout=8, check=True,
        )
        data = _json.loads(result.stdout)
    except (OSError, ValueError, _json.JSONDecodeError) as exc:
        import logging
        logging.getLogger(__name__).debug("windows partitions json parse failed: %s", exc, exc_info=True)
        return []

    ntfs_devs: list[dict] = []
    locked_devs: list[dict] = []

    def _walk(nodes: list) -> None:
        for node in nodes or []:
            if not isinstance(node, dict):
                continue
            fstype = (node.get("fstype") or "").lower()
            if fstype == "ntfs":
                ntfs_devs.append(node)
            elif fstype == "bitlocker" and not node.get("children"):
                # Locked BitLocker partition. Once unlocked, the cleartext NTFS
                # mapper device shows up as a child and is collected above —
                # Windows 11 enables Device Encryption by default, so most
                # modern Windows drives arrive in this state.
                locked_devs.append(node)
            _walk(node.get("children") or [])

    _walk(data.get("blockdevices", []))

    results: list[dict] = []
    for dev in locked_devs:
        name = dev.get("name") or ""
        path = dev.get("path") or (f"/dev/{name}" if name else "")
        if not path:
            continue
        results.append({
            "device":        path,
            "label":         dev.get("label") or "",
            "size":          dev.get("size") or "",
            "mountpoint":    "",
            "is_bitlocker":  True,
            "is_dirty":      False,
            "is_hibernated": False,
            "steam_paths":   [],
            "launcher_paths": {},
            "has_onedrive": False,
            "browser_profiles": [],
            "user_profiles": [],
        })
    for dev in ntfs_devs:
        name = dev.get("name") or ""
        path = dev.get("path") or (f"/dev/{name}" if name else "")
        if not path:
            continue
        label = dev.get("label") or ""
        size  = dev.get("size") or ""

        # Dirty/hibernated check via ntfsfix --no-action (reads; never writes)
        is_dirty = False
        is_hibernated = False
        try:
            r = run_sync(
                ["ntfsfix", "--no-action", path],
                capture_output=True, text=True, timeout=8, check=False,
            )
            combined = (r.stdout + r.stderr).lower()
            if "unclean" in combined or "dirty" in combined:
                is_dirty = True
        except FileNotFoundError:
            # ntfsfix not present — fall back to mount-attempt heuristic below
            pass
        except (OSError, ValueError, _json.JSONDecodeError) as exc:
            _logger.debug("_probe_windows_partitions: ntfsfix check of %s failed: %s", path, exc, exc_info=True)

        # Resolve mountpoint from lsblk JSON
        raw_mounts: list = dev.get("mountpoints") or []
        mountpoint: str = next((m for m in raw_mounts if m and m != "[SWAP]"), "")

        steam_paths: list[str] = []
        launcher_paths: dict[str, list[str]] = {}
        user_profiles: list[dict] = []
        windows_root = False
        has_onedrive = False
        browser_profiles: list[dict] = []
        if mountpoint:
            windows_root = os.path.isdir(os.path.join(mountpoint, "Windows"))
            hiberfil = os.path.join(mountpoint, "hiberfil.sys")
            if os.path.exists(hiberfil):
                is_hibernated = True
                is_dirty = True
            for candidate in (
                "Program Files (x86)/Steam",
                "Program Files/Steam",
                "SteamLibrary",
            ):
                full = os.path.join(mountpoint, candidate)
                if os.path.isdir(full):
                    steam_paths.append(full)
            # Additional launcher library roots — Epic, GOG, Ubisoft, Battle.net, EA
            _launcher_candidates: dict[str, list[str]] = {
                "epic": ["Program Files/Epic Games", "Program Files (x86)/Epic Games"],
                "gog": ["Program Files (x86)/GOG Galaxy", "GOG Games"],
                "ubisoft": ["Program Files (x86)/Ubisoft", "Program Files/Ubisoft"],
                "battlenet": ["Program Files (x86)/Battle.net", "Program Files/Battle.net"],
                "ea": ["Program Files/EA Games", "Program Files (x86)/EA Games", "Program Files (x86)/Origin Games"],
            }
            for launcher, candidates in _launcher_candidates.items():
                found: list[str] = []
                for cand in candidates:
                    full = os.path.join(mountpoint, cand)
                    if os.path.isdir(full):
                        found.append(full)
                if found:
                    launcher_paths[launcher] = found
            users_dir = os.path.join(mountpoint, "Users")
            if os.path.isdir(users_dir):
                for entry in sorted(os.listdir(users_dir)):
                    if entry.lower() in ("all users", "default", "default user", "public", "desktop.ini"):
                        continue
                    profile = os.path.join(users_dir, entry)
                    if not os.path.isdir(profile):
                        continue
                    folders = [
                        name for name in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos", "Saved Games")
                        if os.path.isdir(os.path.join(profile, name))
                    ]
                    # OneDrive detection — folder on disk or cloud placeholder
                    for od_name in ("OneDrive",):
                        od_path = os.path.join(profile, od_name)
                        if os.path.isdir(od_path):
                            has_onedrive = True
                            if od_name not in folders:
                                folders.append(od_name)
                        # OneDrive Business: "OneDrive - <org>"
                        try:
                            for sub in os.listdir(profile):
                                if sub.lower().startswith("onedrive -") and os.path.isdir(os.path.join(profile, sub)):
                                    has_onedrive = True
                                    if sub not in folders:
                                        folders.append(sub)
                        except OSError:
                            pass
                    # Browser profile detection (for Takeout summary)
                    _browser_roots = [
                        ("chrome", os.path.join(profile, "AppData/Local/Google/Chrome/User Data")),
                        ("edge", os.path.join(profile, "AppData/Local/Microsoft/Edge/User Data")),
                        ("firefox", os.path.join(profile, "AppData/Roaming/Mozilla/Firefox/Profiles")),
                        ("brave", os.path.join(profile, "AppData/Local/BraveSoftware/Brave-Browser/User Data")),
                    ]
                    for bname, bpath in _browser_roots:
                        if os.path.isdir(bpath):
                            browser_profiles.append({"browser": bname, "user": entry, "path": bpath})
                    if folders:
                        user_profiles.append({
                            "name": entry,
                            "path": profile,
                            "folders": folders,
                        })

        results.append({
            "device":       path,
            "label":        label,
            "size":         size,
            "mountpoint":   mountpoint,
            "is_dirty":     is_dirty,
            "is_hibernated": is_hibernated,
            "windows_root": windows_root,
            "steam_paths":  steam_paths,
            "launcher_paths": launcher_paths,
            "has_onedrive": has_onedrive,
            "browser_profiles": browser_profiles,
            "user_profiles": user_profiles,
        })

    return results
