"""Steam/Heroic/Lutris/Bottles library detection and ACF parsing."""
from __future__ import annotations

import glob
import json
import os
import re

from .constants import _PROC_MOUNT_ESCAPE_RE, _STEAM_NON_GAME_PATTERNS

try:
    from ..hardware.drives import _find_ntfs_drives as _ntfs_drives_provider
except Exception:
    _ntfs_drives_provider = None  # type: ignore[assignment]


def _parse_steam_acf(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            text = fh.read()
    except OSError:
        return {}
    return _parse_steam_acf_text(text)
 # _parse_steam_acf

def _parse_steam_acf_text(text: str) -> dict:
    data: dict[str, str] = {}
    for key in ("appid", "name", "installdir"):
        match = re.search(rf'"{re.escape(key)}"\s+"([^"]*)"', text, re.IGNORECASE)
        if match:
            data[key] = match.group(1)
    return data
 # _parse_steam_acf_text

def _steam_library_roots() -> list[str]:
    roots: list[str] = []
    for root in (
        os.path.expanduser("~/.local/share/Steam"),
        os.path.expanduser("~/.steam/steam"),
        os.path.expanduser("~/.var/app/com.valvesoftware.Steam/.local/share/Steam"),
    ):
        if os.path.isdir(root) and root not in roots:
            roots.append(root)

    for root in list(roots):
        vdf = os.path.join(root, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, "r", encoding="utf-8", errors="ignore") as fh:
                text = fh.read()
        except OSError:
            continue
        for match in re.finditer(r'"path"\s+"([^"]+)"', text):
            lib = match.group(1).replace("\\\\", "/")
            lib = os.path.expanduser(lib)
            if os.path.isdir(lib) and lib not in roots:
                roots.append(lib)
    return roots
 # _steam_library_roots

def _decode_proc_mount_field(value: str) -> str:
    """Decode the octal escapes used by /proc/mounts fields."""
    return _PROC_MOUNT_ESCAPE_RE.sub(
        lambda match: chr(int(match.group(1), 8)),
        value,
    )
 # _decode_proc_mount_field

def _steam_libraries_on_ntfs() -> list[str]:
    """Steam library roots that sit on an NTFS/other system filesystem.

    Reusing the old PC game drive as a Steam library is the first thing
    most switchers try, and Proton breaks on NTFS in ways that look like
    "Linux gaming is broken" rather than "wrong filesystem" — so detect it
    proactively instead of waiting for the support request.
    """
    mounts: list[tuple[str, str]] = []
    try:
        with open("/proc/mounts", encoding="utf-8") as fh:
            for line in fh:
                parts = line.split()
                if len(parts) >= 3:
                    # /proc/mounts octal-escapes spaces and tabs in mount points.
                    mount_point = _decode_proc_mount_field(parts[1])
                    mounts.append((mount_point, parts[2].lower()))
    except OSError:
        return []
    # Longest mount point first so nested mounts resolve to the right fs.
    mounts.sort(key=lambda entry: len(entry[0]), reverse=True)

    flagged: list[str] = []
    for root in _steam_library_roots():
        real = os.path.realpath(root)
        for mount_point, fstype in mounts:
            if real == mount_point or real.startswith(mount_point.rstrip("/") + "/"):
                # ntfs-3g mounts report as "fuseblk"; exFAT/FAT are equally
                # unfit for Proton prefixes (no symlinks), so flag them too.
                if fstype in ("ntfs", "ntfs3", "fuseblk", "exfat", "vfat"):
                    flagged.append(root)
                break
    return flagged
 # _steam_libraries_on_ntfs

def _detect_steam_games() -> list[dict]:
    games: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for root in _steam_library_roots():
        steamapps = os.path.join(root, "steamapps")
        for manifest in glob.glob(os.path.join(steamapps, "appmanifest_*.acf")):
            data = _parse_steam_acf(manifest)
            name = data.get("name", "").strip()
            appid = data.get("appid", "").strip()
            installdir = data.get("installdir", "").strip()
            if not name:
                continue
            install_path = os.path.join(steamapps, "common", installdir) if installdir else steamapps
            key = ("Steam", appid or name.lower())
            if key in seen:
                continue
            seen.add(key)
            games.append({
                "name": name,
                "launcher": "Steam",
                "path": install_path,
                "appid": appid,
            })
    return games
 # _detect_steam_games

def _detect_heroic_games() -> list[dict]:
    games: list[dict] = []
    seen: set[str] = set()
    roots = [
        os.path.expanduser("~/.config/heroic"),
        os.path.expanduser("~/.var/app/com.heroicgameslauncher.hgl/config/heroic"),
    ]
    for root in roots:
        for pattern in (
            os.path.join(root, "GamesConfig", "*.json"),
            os.path.join(root, "legendaryConfig", "legendary", "installed.json"),
            os.path.join(root, "gog_store", "installed.json"),
        ):
            for path in glob.glob(pattern):
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                        data = json.load(fh)
                except (OSError, json.JSONDecodeError):
                    continue
                entries = data.values() if isinstance(data, dict) else data if isinstance(data, list) else []
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    name = (
                        entry.get("title")
                        or entry.get("name")
                        or entry.get("app_name")
                        or entry.get("appName")
                        or ""
                    )
                    install_path = (
                        entry.get("install_path")
                        or entry.get("installPath")
                        or entry.get("path")
                        or entry.get("folder_name")
                        or ""
                    )
                    name = str(name).strip()
                    if not name or name in seen:
                        continue
                    seen.add(name)
                    games.append({
                        "name": name,
                        "launcher": "Heroic",
                        "path": str(install_path),
                        "appid": str(entry.get("app_name") or entry.get("appName") or ""),
                    })
    return games
 # _detect_heroic_games

def _detect_lutris_games() -> list[dict]:
    games: list[dict] = []
    seen: set[str] = set()
    roots = [
        os.path.expanduser("~/.local/share/lutris/games"),
        os.path.expanduser("~/.var/app/net.lutris.Lutris/data/lutris/games"),
    ]
    for root in roots:
        for path in glob.glob(os.path.join(root, "*.yml")) + glob.glob(os.path.join(root, "*.yaml")):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as fh:
                    text = fh.read()
            except OSError:
                continue
            name_match = re.search(r"(?m)^\s*name:\s*[\"']?(.+?)[\"']?\s*$", text)
            game_match = re.search(r"(?m)^\s*game_slug:\s*[\"']?(.+?)[\"']?\s*$", text)
            path_match = re.search(r"(?m)^\s*(?:prefix|working_dir):\s*[\"']?(.+?)[\"']?\s*$", text)
            name = (name_match.group(1) if name_match else "").strip()
            if not name:
                name = os.path.splitext(os.path.basename(path))[0].replace("-", " ").title()
            key = (game_match.group(1) if game_match else name).lower()
            if key in seen:
                continue
            seen.add(key)
            games.append({
                "name": name,
                "launcher": "Lutris",
                "path": (path_match.group(1).strip() if path_match else path),
                "appid": "",
            })
    return games
 # _detect_lutris_games

def _detect_bottles_apps() -> list[dict]:
    games: list[dict] = []
    seen: set[str] = set()
    roots = [
        os.path.expanduser("~/.local/share/bottles/bottles"),
        os.path.expanduser("~/.var/app/com.usebottles.bottles/data/bottles/bottles"),
    ]
    for root in roots:
        for path in glob.glob(os.path.join(root, "*")):
            if not os.path.isdir(path):
                continue
            name = os.path.basename(path).replace("_", " ").replace("-", " ").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            games.append({
                "name": name,
                "launcher": "Bottles",
                "path": path,
                "appid": "",
            })
    return games
 # _detect_bottles_apps

def _detect_ntfs_steam_games() -> list[dict]:
    """Read-only scan of mounted Windows NTFS partitions for Steam libraries.

    Uses _find_ntfs_drives (lsblk, probe_cached 30s) so we do not re-scan
    /proc/mounts ourselves and we tolerate BitLocker-locked partitions (no
    mount). Never writes — missed mount or permission error -> empty list."""
    if _ntfs_drives_provider is None:
        return []
    try:
        drives = _ntfs_drives_provider()
    except Exception:
        return []
    seen: set[str] = set()
    games: list[dict] = []
    for drive in drives:
        mount = (drive.get("mount") or "").strip() if isinstance(drive, dict) else ""
        if not mount or not os.path.isdir(mount):
            continue
        for steamapps in _find_steam_libraries(mount):
            for item in _scan_steamapps_manifests(steamapps):
                key = item.get("appid") or item.get("name", "").lower()
                if not key or key in seen:
                    continue
                seen.add(key)
                games.append({
                    "name": item.get("name", ""),
                    "launcher": "Steam (Windows NTFS)",
                    "path": os.path.join(steamapps, "common", item.get("name", "")),
                    "appid": item.get("appid", ""),
                    "ntfs": True,
                    "steamapps": steamapps,
                })
    return games
 # _detect_ntfs_steam_games

def _detect_installed_games() -> list[dict]:
    games = []
    games.extend(_detect_steam_games())
    games.extend(_detect_ntfs_steam_games())
    games.extend(_detect_heroic_games())
    games.extend(_detect_lutris_games())
    games.extend(_detect_bottles_apps())
    games.sort(key=lambda item: (item.get("launcher", ""), item.get("name", "").lower()))
    return games
 # _detect_installed_games


def _find_steam_libraries(mount_point: str) -> list[str]:
    """Scan a mounted NTFS drive for steamapps directories."""
    found: list[str] = []
    # Known other system Steam install locations
    candidates = [
        os.path.join(mount_point, "Program Files (x86)", "Steam", "steamapps"),
        os.path.join(mount_point, "Program Files", "Steam", "steamapps"),
        os.path.join(mount_point, "SteamLibrary", "steamapps"),
        os.path.join(mount_point, "Steam", "steamapps"),
        os.path.join(mount_point, "Games", "Steam", "steamapps"),
        os.path.join(mount_point, "Games", "SteamLibrary", "steamapps"),
    ]
    for path in candidates:
        if os.path.isdir(path):
            found.append(path)
    # Shallow scan: check one level of subdirs for SteamLibrary/steamapps patterns
    try:
        for entry in os.scandir(mount_point):
            if not entry.is_dir(follow_symlinks=False):
                continue
            for sub in (
                os.path.join(entry.path, "steamapps"),
                os.path.join(entry.path, "SteamLibrary", "steamapps"),
            ):
                if os.path.isdir(sub) and sub not in found:
                    found.append(sub)
    except (PermissionError, OSError):
        pass
    return found
 # _find_steam_libraries

def _scan_steamapps_manifests(steamapps_dir: str) -> list[dict]:
    """List games recorded in a steamapps directory (works on read-only NTFS mounts)."""
    games: list[dict] = []
    seen: set[str] = set()
    for manifest in glob.glob(os.path.join(steamapps_dir, "appmanifest_*.acf")):
        data = _parse_steam_acf(manifest)
        name = data.get("name", "").strip()
        appid = data.get("appid", "").strip()
        if not name or (appid or name.lower()) in seen:
            continue
        lowered = name.lower()
        if any(lowered.startswith(pat) for pat in _STEAM_NON_GAME_PATTERNS):
            continue
        seen.add(appid or lowered)
        games.append({"name": name, "appid": appid})
    games.sort(key=lambda item: item["name"].lower())
    return games
 # _scan_steamapps_manifests

