"""Shared on-disk probe cache for expensive read-only system queries.

``kyth-probe`` (user/system oneshot) refreshes the cache; System Hub and other
CLI tools read it before spawning ``bootc`` / ``flatpak`` / ``lspci``.

Arch #6: This is a re-export shim only — single source of truth is
``kyth_shared.system.probe``. New code should import from there;
this shim exists for ``kyth_welcome`` backward compat only.
"""
from __future__ import annotations

# pylint: disable=unused-import
from kyth_shared.system.probe import (  # noqa: F401 — re-export pure API for existing imports
    CACHE_VERSION,
    COLLECT_SECTIONS,
    DISK_BACKED_KEYS,
    DISK_TTL,
    MUTATION_KEYS_BOOTC,
    MUTATION_KEYS_FLATPAK,
    ProbeCollector,
    ProbeResult,
    ProbeService,
    ProbeStatus,
    _count_flatpak_updates,
    _service,
    cache_read_paths,
    collect_snapshot,
    collect_probe_results,
    default_collectors,
    default_write_path,
    invalidate_after_bootc_change,
    invalidate_after_flatpak_change,
    invalidate_disk_sections,
    invalidate_probe_caches,
    load_cache_file,
    probe_cached,
    read_section,
    refresh_cache,
    system_cache_path,
    update_sections,
    user_home_cache_path,
    user_runtime_cache_path,
    write_cache_file,
)
# pylint: enable=unused-import
