"""Windows partition probe for game library migration."""
from __future__ import annotations

import json
import os
import subprocess


def _probe_windows_partitions() -> list[dict]:
    """Scan for NTFS partitions, check dirty/hibernated state, find Steam dirs.
    Returns list of dicts safe to call from a non-main thread."""
    import json as _json
    try:
        raw = subprocess.check_output(
            ["lsblk", "--json", "-o", "NAME,FSTYPE,LABEL,MOUNTPOINTS,SIZE,PATH"],
            text=True, timeout=8,
        )
        data = _json.loads(raw)
    except Exception:
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
            r = subprocess.run(
                ["ntfsfix", "--no-action", path],
                capture_output=True, text=True, timeout=8,
            )
            combined = (r.stdout + r.stderr).lower()
            if "unclean" in combined or "dirty" in combined:
                is_dirty = True
        except FileNotFoundError:
            # ntfsfix not present — fall back to mount-attempt heuristic below
            pass
        except Exception:
            pass

        # Resolve mountpoint from lsblk JSON
        raw_mounts: list = dev.get("mountpoints") or []
        mountpoint: str = next((m for m in raw_mounts if m and m != "[SWAP]"), "")

        steam_paths: list[str] = []
        user_profiles: list[dict] = []
        windows_root = False
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
            "user_profiles": user_profiles,
        })

    return results
