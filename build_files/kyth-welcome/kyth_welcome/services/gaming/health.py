"""Gaming health dashboard, migration checklist, and streaming checks."""
from __future__ import annotations

import os
import shutil

from .steam import _detect_installed_games
from .tools import (
    _compat_tool_version,
    _gamescope_installed,
    _mangohud_installed,
    _proton_cachyos_version,
    _ntsync_state,
    _vulkan_state,
)
from ..bootc import _has_staged_update
from ..hardware import _detect_controllers, _find_ntfs_drives
from ..process import _run_command
from ..software import _is_flatpak_installed


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
        newest = max(existing, key=os.path.getmtime)
        return "ok", "Save backups", f"Ludusavi installed; backup/config path found: {newest}"
    if ludusavi_ok:
        return "warn", "Save backups", "Ludusavi installed; run a backup before migration or modding."
    return "warn", "Save backups", "Install Ludusavi before importing saves or modding."
 # _ludusavi_backup_summary


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

