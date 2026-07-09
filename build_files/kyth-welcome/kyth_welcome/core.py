# Facade for backwards compatibility. All page modules import from .core.
# Core foundation is defined in .core_base to avoid circular imports.

from . import core_base
for _k, _v in core_base.__dict__.items():
    if not _k.startswith("__"):
        globals()[_k] = _v
from .services.updates import UpdateCheckWorker, FirmwareCheckWorker, ChangelogWorker
from .services.hardware import (
    HardwareProbe, HardwareProbeWorker, _detect_nvidia, _nvidia_module_loaded,
    _akmod_nvidia_built, _akmod_nvidia_installed, _hw_setup_service_state, _hw_setup_done,
    _status_palette, _gpu_probe, _firmware_probe, _connectivity_probe, _audio_probe,
    _controller_probe, _strip_ansi, _format_display_mode, _cpu_probe, _memory_probe,
    _display_probe, _parse_kscreen_output, _thermal_probe, _peripheral_probe,
    _displaylink_probe, _storage_probe, _platform_probe, _vaapi_failure_summary,
    _mesa_vaapi_failure_context, _compact_vaapi_failure_details, _vaapi_profiles,
    _successful_vaapi_probe, _codec_probe, _collect_hardware_probes, _find_ntfs_drives,
    _detect_controllers
)
from .services.gaming import (
    _mangohud_installed, _gamescope_installed, _vkbasalt_installed, _ge_proton_version,
    _compat_tool_version, _ntsync_state, _vulkan_state, _gaming_health_items,
    _gaming_migration_checklist_items, _collect_gaming_dashboard, _ludusavi_backup_summary,
    _parse_steam_acf, _parse_steam_acf_text, _steam_library_roots, _decode_proc_mount_field,
    _steam_libraries_on_ntfs, _detect_steam_games, _detect_heroic_games, _detect_lutris_games,
    _detect_bottles_apps, _detect_installed_games, _load_protondb_cache, _save_protondb_cache,
    _ProtonDbBatchWorker, _streaming_health_items, _find_steam_libraries, _scan_steamapps_manifests
)
from .services.network import (
    _rclone_available, _rclone_list_remotes, _rclone_has_remote_type, _load_sync_config,
    _save_sync_config, _load_smb_config, _save_smb_config, _systemd_escape_mount_path,
    _is_cifs_available, _is_mounted, _build_add_share_script, _build_remove_share_script
)
from .services.software import (
    _installed_flatpak_ids, _is_flatpak_installed, _chromium_app_window_id,
    _chromium_app_window_cmd, _install_flatpak_inline, _first_run_app_setup_state,
    _davinci_flatpak_app_id, _davinci_download_dir, _davinci_zip_candidates
)
from .services.diagnostics import (
    _tail_file, _system_hub_log_has_self_error, _system_hub_probe, _diagnostics_report,
    _health_command_report, _health_recommendations
)
