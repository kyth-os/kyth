"""Gaming domain services (health, steam, tools, compat, …)."""
from .constants import (
    _PROC_MOUNT_ESCAPE_RE,
    _PROTONDB_CACHE_PATH,
    _PROTONDB_TIER_STYLE,
    _STEAM_NON_GAME_PATTERNS,
)
from .tools import (
    GAMING_TOOLS,
    _compat_tool_version,
    _gamescope_installed,
    _mangohud_installed,
    _ntsync_state,
    _proton_cachyos_version,
    _vkbasalt_installed,
    _vulkan_state,
    command_details,
    discord_screenshare_fix_command,
    heroic_epic_launcher_command,
    lutris_installer_command,
    obs_pipewire_fix_command,
    opticscaler_deploy_command,
    scx_scheduler_command,
)
from .steam import (
    _decode_proc_mount_field,
    _detect_bottles_apps,
    _detect_heroic_games,
    _detect_installed_games,
    _detect_lutris_games,
    _detect_steam_games,
    _find_steam_libraries,
    _parse_steam_acf,
    _parse_steam_acf_text,
    _scan_steamapps_manifests,
    _steam_libraries_on_ntfs,
    _steam_library_roots,
)
from .protondb import (
    _ProtonDbBatchWorker,
    _load_protondb_cache,
    _save_protondb_cache,
)
from .health import (
    _collect_gaming_dashboard,
    _gaming_health_items,
    _gaming_migration_checklist_items,
    _ludusavi_backup_summary,
    _streaming_health_items,
)
from .compat import (
    blocked_compat_lookup,
    find_compat_game,
    recommended_launcher_for_game,
    recommended_profile_for_game,
)
from .gamenight import GameNightManager, _cleanup_game_night
from .windows_partitions import _probe_windows_partitions

# Pure re-export (no Qt)
from ..hardware import _find_ntfs_drives  # noqa: F401

__all__ = [
    "GAMING_TOOLS",
    "GameNightManager",
    "TrackedThread",
    "Worker",
    "DataWorker",
    "_PROTONDB_TIER_STYLE",
    "_ProtonDbBatchWorker",
    "_collect_gaming_dashboard",
    "_detect_installed_games",
    "_find_ntfs_drives",
    "_gaming_health_items",
    "_gaming_migration_checklist_items",
    "_load_protondb_cache",
    "_probe_windows_partitions",
    "_save_protondb_cache",
    "_steam_libraries_on_ntfs",
    "_streaming_health_items",
    "blocked_compat_lookup",
    "command_details",
    "discord_screenshare_fix_command",
    "find_compat_game",
    "heroic_epic_launcher_command",
    "lutris_installer_command",
    "obs_pipewire_fix_command",
    "opticscaler_deploy_command",
    "recommended_launcher_for_game",
    "recommended_profile_for_game",
    "scx_scheduler_command",
]


def __getattr__(name: str):
    """Lazy re-export of Qt worker types so pure gaming imports stay Qt-free."""
    if name in {"DataWorker", "TrackedThread", "Worker"}:
        from ..runtime import DataWorker, TrackedThread, Worker
        mapping = {
            "DataWorker": DataWorker,
            "TrackedThread": TrackedThread,
            "Worker": Worker,
        }
        return mapping[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
