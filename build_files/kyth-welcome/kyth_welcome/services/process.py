"""Process helpers and short-lived probe cache.

Pure stdlib utilities shared by System Hub services and CLI helpers. No Qt.
"""
from __future__ import annotations

# pylint: disable=unused-import
from kyth_shared.system.process import (  # noqa: F401 — re-export pure API for existing imports
    BOOTC_CACHE_TTL,
    DISK_BACKED_KEYS,
    FLATPAK_CACHE_TTL,
    PROBE_CACHE,
    PROBE_CACHE_LOCK,
    command_stdout,
    disk_section_usable,
    format_dl_progress_line,
    format_elapsed,
    format_eta,
    get_disk_write_bytes,
    invalidate_probe_caches,
    is_live_session,
    probe_cached,
    run_command,
    strip_ansi,
    with_idle_inhibit,
)
from kyth_shared import get_rx_bytes, human_bytes, human_bytes_pair, parse_size_bytes  # noqa: F401 — re-export pure API for existing imports
# pylint: enable=unused-import
