import glob
import json
import os
import re
import shutil
import subprocess
import time
from urllib.request import Request, urlopen

from ..qt import Signal
from ..core_base import (
    TrackedThread, Worker, DataWorker, _run_command, _command_stdout,
    _is_live_session, _has_staged_update
)
from .hardware import _find_ntfs_drives, _detect_controllers
from .software import _is_flatpak_installed

_PROC_MOUNT_ESCAPE_RE = re.compile(r"\\([0-7]{3})")

_STEAM_NON_GAME_PATTERNS = (
    "steamworks common redistributables",
    "steam linux runtime",
    "proton",
    "steamvr",
)

_PROTONDB_CACHE_PATH = os.path.expanduser("~/.cache/kyth-protondb.json")
_PROTONDB_TIER_STYLE = {
    "platinum": ("#102010", "#7ee8a2"),
    "gold":     ("#2b2410", "#d4a843"),
    "silver":   ("#181e2b", "#8cadcf"),
    "bronze":   ("#2b1a10", "#c47c4a"),
    "borked":   ("#3a1010", "#f48771"),
    "pending":  ("#252526", "#858585"),
}

def _mangohud_installed() -> bool:
    return shutil.which("mangohud") is not None
 # _mangohud_installed

def _gamescope_installed() -> bool:
    return shutil.which("gamescope") is not None
 # _gamescope_installed

def _vkbasalt_installed() -> bool:
    return any(
        os.path.exists(p) for p in (
            "/usr/lib64/vkbasalt/libvkbasalt.so",
            "/usr/lib/vkbasalt/libvkbasalt.so",
            "/usr/lib64/libvkbasalt.so",
            "/usr/lib/libvkbasalt.so",
        )
    )
 # _vkbasalt_installed

def _proton_cachyos_version() -> str | None:
    """Return the latest installed Proton-CachyOS directory name, or None."""
    found: list[str] = []
    for base in (
        "/usr/share/steam/compatibilitytools.d",
        "/var/lib/kyth/proton-cachyos",
    ):
        try:
            found.extend(e for e in os.listdir(base) if e.startswith("proton-cachyos"))
        except OSError:
            pass
    return sorted(found)[-1] if found else None
 # _proton_cachyos_version

def _compat_tool_version(prefix: str) -> str | None:
    """Return the latest installed Steam compatibility tool matching prefix."""
    bases = [
        "/usr/share/steam/compatibilitytools.d",
        "/var/lib/kyth/proton-cachyos",
        os.path.expanduser("~/.steam/root/compatibilitytools.d"),
        os.path.expanduser("~/.steam/steam/compatibilitytools.d"),
        os.path.expanduser("~/.local/share/Steam/compatibilitytools.d"),
    ]
    found: list[str] = []
    for base in bases:
        try:
            found.extend(e for e in os.listdir(base) if e.lower().startswith(prefix.lower()))
        except OSError:
            pass
    return sorted(found)[-1] if found else None
 # _compat_tool_version

def _ntsync_state() -> tuple[str, str]:
    if os.path.exists("/dev/ntsync"):
        return "ok", "/dev/ntsync is present."
    module_probe = _run_command(["modprobe", "-n", "ntsync"], timeout=5)
    if module_probe is not None and module_probe.returncode == 0:
        return "warn", "ntsync module exists but /dev/ntsync is not present yet."
    return "warn", "ntsync device not detected; Proton will fall back to fsync/esync."
 # _ntsync_state

def _vulkan_state() -> tuple[str, str]:
    if shutil.which("vulkaninfo"):
        result = _run_command(["vulkaninfo", "--summary"], timeout=12)
        if result is not None and result.returncode == 0:
            gpus = [
                line.split("=", 1)[1].strip()
                for line in result.stdout.splitlines()
                if "deviceName" in line and "=" in line
            ]
            return "ok", "Vulkan ready" + (f": {', '.join(gpus[:2])}" if gpus else ".")
        return "err", "vulkaninfo is installed but Vulkan probing failed."
    render_nodes = glob.glob("/dev/dri/renderD*")
    if render_nodes:
        return "warn", "Render device exists, but vulkaninfo is not installed for a full check."
    return "err", "No Vulkan render device detected."
 # _vulkan_state

def _gaming_health_items(*, controllers: dict | None = None,
                         windows_drives: list | None = None) -> list[tuple[str, str, str]]:
    """Small, fast checks aimed at PC gamers before they launch a title.

    controllers/windows_drives accept precomputed probe results so callers that
    build several sections (the gaming dashboard) don't repeat the hardware scans.
    """
    pc_ver = _proton_cachyos_version()
    ge_ver = _compat_tool_version("GE-Proton")
    vulkan_status, vulkan_summary = _vulkan_state()
    ntsync_status, ntsync_summary = _ntsync_state()
    steam_ok = _is_flatpak_installed("com.valvesoftware.Steam")
    heroic_ok = _is_flatpak_installed("com.heroicgameslauncher.hgl")
    lutris_ok = _is_flatpak_installed("net.lutris.Lutris")
    if controllers is None:
        controllers = _detect_controllers()
    controller_count = len(controllers.get("usb_controllers", [])) + len(controllers.get("input_nodes", []))
    if windows_drives is None:
        windows_drives = _find_ntfs_drives()
    ntfs_count = sum(not d.get("is_bitlocker") for d in windows_drives)
    bitlocker_count = sum(bool(d.get("is_bitlocker")) for d in windows_drives)
    if bitlocker_count:
        windows_drive_summary = (
            f"{ntfs_count} readable NTFS and {bitlocker_count} locked BitLocker "
            "partition(s) detected; unlock and migrate them below."
        )
    else:
        windows_drive_summary = f"{ntfs_count} NTFS partition(s) detected; use migration below."

    return [
        ("ok" if steam_ok else "warn", "Steam", "Installed." if steam_ok else "Install Steam to run your Steam library."),
        ("ok" if pc_ver else "err", "Proton-CachyOS", pc_ver or "Missing; use Update Proton-CachyOS below."),
        ("ok" if ge_ver else "dim", "GE-Proton", ge_ver or "Optional runner for stubborn games."),
        (vulkan_status, "Vulkan", vulkan_summary),
        (ntsync_status, "NTSYNC", ntsync_summary),
        ("ok" if shutil.which("umu-run") else "warn", "umu-launcher", "Installed." if shutil.which("umu-run") else "Needed by some Lutris/Heroic launcher flows."),
        ("ok" if _gamescope_installed() else "warn", "Gamescope", "Installed." if _gamescope_installed() else "Missing compositor for HDR/VRR/upscaling presets."),
        ("ok" if _mangohud_installed() else "warn", "MangoHud", "Installed." if _mangohud_installed() else "Missing performance overlay."),
        ("ok" if controller_count else "dim", "Controllers", f"{controller_count} controller input(s) detected." if controller_count else "Connect one and press Refresh."),
        ("ok" if heroic_ok or lutris_ok else "dim", "Non-Steam launchers", "Heroic or Lutris installed." if heroic_ok or lutris_ok else "Install Heroic or Lutris for Epic, GOG, Battle.net, EA, and Ubisoft."),
        ("warn" if windows_drives else "ok", "PC game drives", windows_drive_summary if windows_drives else "No PC game drives detected."),
        ("warn" if _has_staged_update() else "ok", "OS update", "Update staged; reboot before benchmarking." if _has_staged_update() else "No staged OS update."),
    ]
 # _gaming_health_items

def _gaming_migration_checklist_items(*, controllers: dict | None = None,
                                      windows_drives: list | None = None,
                                      saves: tuple | None = None) -> list[tuple[str, str, str]]:
    steam_ok = _is_flatpak_installed("com.valvesoftware.Steam")
    heroic_ok = _is_flatpak_installed("com.heroicgameslauncher.hgl")
    lutris_ok = _is_flatpak_installed("net.lutris.Lutris")
    discord_ok = _is_flatpak_installed("com.discordapp.Discord")
    obs_ok = _is_flatpak_installed("com.obsproject.Studio")
    ludusavi_status, _, ludusavi_summary = saves if saves is not None else _ludusavi_backup_summary()
    controller_info = controllers if controllers is not None else _detect_controllers()
    controller_count = len(controller_info.get("usb_controllers", [])) + len(controller_info.get("input_nodes", []))
    if windows_drives is None:
        windows_drives = _find_ntfs_drives()
    ntfs_count = sum(not d.get("is_bitlocker") for d in windows_drives)
    bitlocker_count = sum(bool(d.get("is_bitlocker")) for d in windows_drives)
    if bitlocker_count:
        migration_summary = (
            f"{ntfs_count} readable NTFS and {bitlocker_count} locked BitLocker "
            "partition(s) detected; unlock them on Move Files first."
        )
    else:
        migration_summary = f"{ntfs_count} NTFS partition(s) detected; copy games read-only below."
    pc_ver = _proton_cachyos_version()
    return [
        ("ok" if steam_ok else "warn", "Steam installed", "Ready." if steam_ok else "Install Steam, then enable Steam Play for all titles."),
        ("ok" if pc_ver else "err", "Proton-CachyOS ready", pc_ver or "Missing; update Proton-CachyOS before testing PC games."),
        ("ok" if heroic_ok and lutris_ok else "warn", "Non-Steam launchers", "Heroic and Lutris installed." if heroic_ok and lutris_ok else "Install Heroic for Epic/GOG and Lutris for Battle.net/EA/Ubisoft."),
        (ludusavi_status, "Saves backed up", ludusavi_summary),
        ("warn" if windows_drives else "dim", "Game library migration", migration_summary if windows_drives else "No PC game drive detected."),
        ("ok" if controller_count else "dim", "Controller tested", f"{controller_count} controller input(s) detected." if controller_count else "Connect a controller and use the Controllers page to verify input."),
        ("ok" if discord_ok and obs_ok else "warn", "Social and capture", "Discord and OBS installed." if discord_ok and obs_ok else "Install Discord and OBS if this player streams, records, or joins voice chat."),
        ("ok", "Blocked games explained", "Compatibility page uses dated source checks for anti-cheat blockers."),
    ]
 # _gaming_migration_checklist_items

def _collect_gaming_dashboard() -> dict:
    # Probe hardware and saves once; health and checklist share the results.
    controllers = _detect_controllers()
    windows_drives = _find_ntfs_drives()
    saves = _ludusavi_backup_summary()
    return {
        "health": _gaming_health_items(controllers=controllers, windows_drives=windows_drives),
        "checklist": _gaming_migration_checklist_items(
            controllers=controllers, windows_drives=windows_drives, saves=saves),
        "streaming": _streaming_health_items(),
        "saves": saves,
        "games": _detect_installed_games(),
    }
 # _collect_gaming_dashboard

def _ludusavi_backup_summary() -> tuple[str, str, str]:
    ludusavi_ok = _is_flatpak_installed("com.github.mtkennerly.ludusavi")
    candidates = [
        os.path.expanduser("~/Ludusavi"),
        os.path.expanduser("~/Games/Ludusavi"),
        os.path.expanduser("~/Documents/Ludusavi"),
        os.path.expanduser("~/.var/app/com.github.mtkennerly.ludusavi"),
    ]
    existing = [path for path in candidates if os.path.exists(path)]
    if ludusavi_ok and existing:
        newest = max(existing, key=lambda path: os.path.getmtime(path))
        return "ok", "Save backups", f"Ludusavi installed; backup/config path found: {newest}"
    if ludusavi_ok:
        return "warn", "Save backups", "Ludusavi installed; run a backup before migration or modding."
    return "warn", "Save backups", "Install Ludusavi before importing saves or modding."
 # _ludusavi_backup_summary

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

def _detect_installed_games() -> list[dict]:
    games = []
    games.extend(_detect_steam_games())
    games.extend(_detect_heroic_games())
    games.extend(_detect_lutris_games())
    games.extend(_detect_bottles_apps())
    games.sort(key=lambda item: (item.get("launcher", ""), item.get("name", "").lower()))
    return games
 # _detect_installed_games

def _load_protondb_cache() -> dict[str, str]:
    try:
        with open(_PROTONDB_CACHE_PATH, encoding="utf-8") as _f:
            data = json.load(_f)
            if isinstance(data, dict):
                return data
    except (OSError, json.JSONDecodeError):
        pass
    return {}
 # _load_protondb_cache

def _save_protondb_cache(cache: dict[str, str]) -> None:
    try:
        os.makedirs(os.path.dirname(_PROTONDB_CACHE_PATH), exist_ok=True)
        with open(_PROTONDB_CACHE_PATH, "w", encoding="utf-8") as _f:
            json.dump(cache, _f)
    except OSError:
        pass
 # _save_protondb_cache

class _ProtonDbBatchWorker(TrackedThread):
    """Fetches ProtonDB tiers for a list of Steam appids, skipping already-cached ones."""
    tier_fetched = Signal(str, str)   # (appid, tier)
    finished_all = Signal(dict)       # full {appid: tier} map

    def __init__(self, appids: list[str], existing: dict[str, str]):
        super().__init__()
        self._appids = appids
        self._existing = dict(existing)

    def run(self):
        result = dict(self._existing)
        for appid in self._appids:
            if not appid or appid in result:
                continue
            try:
                req = Request(
                    f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json",
                    headers={"User-Agent": "KythOS-GameCheck/1.0"},
                )
                with urlopen(req, timeout=8) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    tier = data.get("tier") or "pending"
                    result[appid] = tier
                    self.tier_fetched.emit(appid, tier)
            except Exception:
                result[appid] = "pending"
            time.sleep(0.06)
        self.finished_all.emit(result)
 # _ProtonDbBatchWorker

def _streaming_health_items() -> list[tuple[str, str, str]]:
    pipewire_ok = shutil.which("pw-cli") is not None or shutil.which("wpctl") is not None
    obs_capture_ok = any(
        os.path.exists(path) for path in (
            "/usr/lib64/libobs_vkcapture.so",
            "/usr/lib/libobs_vkcapture.so",
            "/usr/lib64/obs-plugins/libobs_vkcapture.so",
            "/usr/lib/obs-plugins/libobs_vkcapture.so",
        )
    )
    v4l2_probe = _run_command(["modprobe", "-n", "v4l2loopback"], timeout=4)
    v4l2_ok = v4l2_probe is not None and v4l2_probe.returncode == 0
    mic_hint = "PipeWire ready; test mic in Discord/OBS." if pipewire_ok else "PipeWire tools not found."
    obs_ok = _is_flatpak_installed("com.obsproject.Studio")
    discord_ok = _is_flatpak_installed("com.discordapp.Discord")

    return [
        ("ok" if obs_ok else "warn", "OBS Studio", "Installed." if obs_ok else "Install OBS for capture and streaming."),
        ("ok" if discord_ok else "warn", "Discord", "Installed." if discord_ok else "Install Discord for voice and screen share testing."),
        ("ok" if pipewire_ok else "warn", "PipeWire", mic_hint),
        ("ok" if obs_capture_ok else "warn", "Game capture", "obs-vkcapture runtime present." if obs_capture_ok else "obs-vkcapture runtime not detected."),
        ("ok" if v4l2_ok else "dim", "Virtual camera", "v4l2loopback available." if v4l2_ok else "Optional: v4l2loopback not available."),
    ]
 # _streaming_health_items

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

# Static gaming tool definitions used by GamingPage.
GAMING_TOOLS = [
    {
        "flatpak": "com.valvesoftware.Steam",
        "name": "Steam",
        "desc": "Valve's gaming platform plus PC games through Proton.",
        "ujust": "install-steam",
        "launch": ["flatpak", "run", "com.valvesoftware.Steam"],
    },
    {
        "flatpak": "net.lutris.Lutris",
        "name": "Lutris",
        "desc": "Battle.net, EA App, Ubisoft Connect, and other compatibility launchers.",
        "ujust": "install-lutris",
        "launch": ["flatpak", "run", "net.lutris.Lutris"],
    },
    {
        "flatpak": "com.heroicgameslauncher.hgl",
        "name": "Heroic Games Launcher",
        "desc": "Epic Games, GOG, and Amazon Games library in one place.",
        "ujust": "install-heroic",
        "launch": ["flatpak", "run", "com.heroicgameslauncher.hgl"],
    },
    {
        "flatpak": "com.usebottles.bottles",
        "name": "Bottles",
        "desc": "Best for running standalone .exe and .msi installers in isolated app environments.",
        "ujust": "install-bottles",
        "launch": ["flatpak", "run", "com.usebottles.bottles"],
    },
    {
        "flatpak": "com.github.mtkennerly.ludusavi",
        "name": "Ludusavi",
        "desc": "Back up and restore game saves across Steam, Heroic, Lutris, and PC migrations.",
        "ujust": "install-ludusavi",
        "launch": ["flatpak", "run", "com.github.mtkennerly.ludusavi"],
    },
    {
        "flatpak": "org.prismlauncher.PrismLauncher",
        "name": "Prism Launcher",
        "desc": "Minecraft launcher with modpacks, multiple instances, and Java version control.",
        "ujust": "install-prismlauncher",
        "launch": ["flatpak", "run", "org.prismlauncher.PrismLauncher"],
    },
    {
        "flatpak": "io.itch.itch",
        "name": "Itch.io",
        "desc": "Indie game store and library manager.",
        "ujust": "install-itch",
        "launch": ["flatpak", "run", "io.itch.itch"],
    },
    {
        "flatpak": "org.libretro.RetroArch",
        "name": "RetroArch",
        "desc": "Multi-system emulator frontend (NES, SNES, PS1, N64, …).",
        "ujust": "install-retroarch",
        "launch": ["flatpak", "run", "org.libretro.RetroArch"],
    },
    {
        "flatpak": "org.freedesktop.Piper",
        "name": "Piper",
        "desc": "GUI for configuring gaming mice — DPI, buttons, and LEDs.",
        "ujust": "install-piper",
        "launch": ["flatpak", "run", "org.freedesktop.Piper"],
    },
    {
        "flatpak": "org.openrgb.OpenRGB",
        "name": "OpenRGB",
        "desc": "Unified RGB lighting control for motherboards, RAM, GPUs, and peripherals. Pre-installed — RGB profiles are applied automatically at login.",
        "ujust": "install-openrgb",
        "launch": ["openrgb"],
    },
    {
        "flatpak": "io.github.benjamimgois.goverlay",
        "name": "GOverlay",
        "desc": "Graphical tuning for MangoHud and vkBasalt overlays — adjust metrics, colors, and presets without editing config files.",
        "ujust": "install-goverlay",
        "launch": ["flatpak", "run", "io.github.benjamimgois.goverlay"],
    },
    {
        "flatpak": "io.github.radiolamp.mangojuice",
        "name": "MangoJuice",
        "desc": "Lightweight MangoHud configuration editor for overlay layout and metrics.",
        "ujust": "install-mangojuice",
        "launch": ["flatpak", "run", "io.github.radiolamp.mangojuice"],
    },
    {
        "flatpak": "com.dec05eba.gpu_screen_recorder",
        "name": "GPU Screen Recorder",
        "desc": "Near-zero overhead gameplay capture and instant replay using AMD/NVIDIA GPU encoding.",
        "ujust": "install-gpu-screen-recorder",
        "launch": ["flatpak", "run", "com.dec05eba.gpu_screen_recorder"],
    },
    {
        "flatpak": "dev.vencord.Vesktop",
        "name": "Vesktop",
        "desc": "Discord client with native Wayland support, better screenshare, and no telemetry.",
        "ujust": "install-vesktop",
        "launch": ["flatpak", "run", "dev.vencord.Vesktop"],
    },
]

# Gaming action command builders extracted from GamingPage.
def discord_screenshare_fix_command():
    return [
        "bash", "-c",
        "flatpak override --user com.discordapp.Discord "
        "--env=ELECTRON_OZONE_PLATFORM_HINT=auto "
        "--socket=wayland --socket=fallback-x11 --device=dri "
        "--talk-name=org.freedesktop.portal.Desktop "
        "--talk-name=org.kde.StatusNotifierWatcher",
    ]

def obs_pipewire_fix_command():
    return [
        "bash", "-c",
        "flatpak override --user com.obsproject.Studio "
        "--socket=wayland --socket=pulseaudio --device=dri "
        "--talk-name=org.freedesktop.portal.Desktop",
    ]

# Parameterized gaming action command builders extracted from GamingPage.
def opticscaler_deploy_command(game_dir):
    return ["ujust", "deploy-opticscaler", game_dir]

def heroic_epic_launcher_command():
    return ["flatpak", "run", "com.heroicgameslauncher.hgl"]

def lutris_installer_command(lutris_target):
    return ["flatpak", "run", "net.lutris.Lutris", lutris_target]

# Scheduler command builder extracted from GamingPage.
def scx_scheduler_command(scheduler):
    if scheduler == "stop":
        return ["kyth-scx", "stop"]
        label = "Stopping sched-ext loader"
    else:
        return ["kyth-scx", "set", scheduler]
        label = f"Switching sched-ext scheduler to {scheduler}"

# Page-level gaming helpers extracted from GamingPage.
def command_details(cmd: list[str], result=None, exc: Exception | None = None) -> str:
    lines = ["Command:", "  " + " ".join(cmd)]
    if exc is not None:
        lines.extend(["", "Error:", str(exc)])
        return "\n".join(lines)
    if result is None:
        return "\n".join(lines)
    lines.extend(["", f"Exit code: {result.returncode}"])
    stdout = result.stdout.decode("utf-8", errors="replace").strip() if result.stdout else ""
    stderr = result.stderr.decode("utf-8", errors="replace").strip() if result.stderr else ""
    if stdout:
        lines.extend(["", "stdout:", stdout])
    if stderr:
        lines.extend(["", "stderr:", stderr])
    return "\n".join(lines)

def find_compat_game(compat_games, query: str):
    needle = query.strip().lower()
    if not needle:
        return None
    for game in compat_games:
        if game.name.lower() == needle:
            return game
    for game in compat_games:
        if needle in game.name.lower() or game.name.lower() in needle:
            return game
    return None

def recommended_launcher_for_game(game) -> str:
    name = game.name.lower()
    if "overwatch" in name:
        return "Lutris with Battle.net via umu-run"
    if any(token in name for token in ("red dead", "gta")):
        return "Steam when owned there; otherwise Lutris/Heroic plus the Rockstar launcher"
    if game.status == "blocked":
        return "None on Linux until the publisher enables support"
    if game.status == "native":
        return "Steam native Linux build"
    return "Steam with Proton Experimental first, then Proton-CachyOS"

def recommended_profile_for_game(game) -> str:
    if game.status == "blocked":
        return "Do not try bypass launch options; use other system or wait for publisher support."
    if any(token in game.name.lower() for token in ("cyberpunk", "red dead", "hogwarts")):
        return "kyth-gamescope quality -- %command%"
    if game.anticheat in ("EAC", "BattlEye", "VAC", "Warden"):
        return "game-performance --profile gaming -- %command%"
    return "kyth-gamescope quality -- %command%"

def blocked_compat_lookup(compat_games) -> tuple[dict[str, str], set[str]]:
    """Blocked Steam appids (from compat source URLs) and lowercase names."""
    appids: dict[str, str] = {}
    names: set[str] = set()
    for game in compat_games:
        if game.status != "blocked":
            continue
        names.add(game.name.lower())
        m = re.search(r"protondb\.com/app/(\d+)", game.source_url)
        if m:
            appids[m.group(1)] = game.name
    return appids, names


class GameNightManager:
    _inhibit_proc = None

    @classmethod
    def start(cls) -> bool:
        if cls._inhibit_proc and cls._inhibit_proc.poll() is None:
            return False

        subprocess.Popen(["kyth-performance-mode", "save"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.Popen(["kyth-performance-mode", "gaming"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if shutil.which("systemd-inhibit"):
            cls._inhibit_proc = subprocess.Popen(
                ["systemd-inhibit", "--what=idle:sleep", "--why=KythOS Game Night Mode", "sleep", "14400"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        return True

    @classmethod
    def stop(cls) -> None:
        if cls._inhibit_proc and cls._inhibit_proc.poll() is None:
            cls._inhibit_proc.terminate()
            cls._inhibit_proc = None
        subprocess.Popen(["kyth-performance-mode", "restore"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @classmethod
    def is_active(cls) -> bool:
        return cls._inhibit_proc is not None and cls._inhibit_proc.poll() is None


import atexit

def _cleanup_game_night():
    GameNightManager.stop()

atexit.register(_cleanup_game_night)


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
