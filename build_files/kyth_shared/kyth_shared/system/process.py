"""Process helpers and short-lived probe cache.

Pure stdlib utilities shared by system services and CLI helpers. No Qt.

The hybrid mem+disk probe cache now lives in :mod:`kyth_shared.system.probe`
as :class:`ProbeService` — this module re-exports the same symbols for
backwards compatibility so existing ``from kyth_shared.system.process import
probe_cached`` imports keep working while the implementation is unified.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from typing import Callable, Iterable, TypeVar

from kyth_shared.commands import command_stdout as _raw_command_stdout, run_text

T = TypeVar("T")


def is_live_session() -> bool:
    try:
        with open("/proc/cmdline") as _f:
            return "kyth.live" in _f.read()
    except OSError:
        return False


# Re-exported from probe.py — single source of truth (ProbeService.mem+disk).
# Kept as module-level aliases so ``process.PROBE_CACHE`` etc still resolve for
# tests that inspect the cache dict directly.
try:
    from kyth_shared.system.probe import DISK_BACKED_KEYS as _DISK_BACKED_KEYS  # noqa: F401
    from kyth_shared.system.probe import DISK_TTL as _DISK_TTL  # noqa: F401

    DISK_BACKED_KEYS = _DISK_BACKED_KEYS
    BOOTC_CACHE_TTL = 5.0  # legacy alias; probe.DIS​K_TTL["bootc-status-data"] is canonical
    FLATPAK_CACHE_TTL = 10.0

    # Expose the ProbeService singleton's mem store for introspection.
    from kyth_shared.system.probe import _service as _probe_service

    PROBE_CACHE = _probe_service._mem  # type: ignore[attr-defined]
    PROBE_CACHE_LOCK = _probe_service._lock  # type: ignore[attr-defined]
except Exception:
    # Fallback for import-order cycles during early build — tests never hit this.
    import threading as _threading  # noqa: PLC0415

    DISK_BACKED_KEYS = frozenset({
        "bootc-status-data",
        "bootc-status-text",
        "bootc-branch",
        "kernel-flavor",
        "flatpak-apps",
        "flatpak-updates",
        "nvidia-detect",
        "controllers-detect",
    })
    BOOTC_CACHE_TTL = 5.0
    FLATPAK_CACHE_TTL = 10.0
    PROBE_CACHE_LOCK = _threading.Lock()
    PROBE_CACHE: dict[str, tuple[float, object]] = {}


def run_command(cmd: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str] | None:
    return run_text(cmd, timeout=timeout)


def command_stdout(cmd: list[str], timeout: int = 5) -> str:
    return _raw_command_stdout(cmd, timeout=timeout)


def strip_ansi(text: str) -> str:
    """Strip ANSI CSI escape sequences (color, cursor movement, etc.)."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def with_idle_inhibit(cmd: list[str], reason: str) -> list[str]:
    inhibit = shutil.which("systemd-inhibit")
    if not inhibit:
        return cmd
    return [inhibit, "--what=idle:sleep", f"--why={reason}", "--mode=block", *cmd]


def invalidate_probe_caches(keys: Iterable[str] | None = None) -> None:  # type: ignore[no-redef]
    from kyth_shared.system.probe import invalidate_probe_caches as _probe_invalidate

    return _probe_invalidate(keys)


def disk_section_usable(key: str, data: object) -> bool:  # noqa: F401 — re-export for legacy callers
    from kyth_shared.system.probe import _disk_section_usable

    return _disk_section_usable(key, data)


def probe_cached(key: str, ttl: float, fetch: Callable[[], T]) -> T:
    from kyth_shared.system.probe import probe_cached as _probe_cached

    return _probe_cached(key, ttl, fetch)


def get_disk_write_bytes() -> int:
    """Sum write bytes across all block devices from /proc/diskstats."""
    try:
        total = 0
        with open("/proc/diskstats") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 10:
                    total += int(parts[9])
        return total * 512
    except Exception:
        return 0


# pylint: disable=unused-import
from kyth_shared import get_rx_bytes, human_bytes, human_bytes_pair, parse_size_bytes  # noqa: F401 — re-export pure API for existing imports
# pylint: enable=unused-import


def format_elapsed(seconds: int) -> str:
    mins, secs = divmod(max(0, seconds), 60)
    return f"{mins}m {secs:02d}s" if mins else f"{secs}s"


def format_eta(seconds: int) -> str:
    if seconds > 60:
        return f"~{format_elapsed(seconds)} remaining"
    if seconds > 0:
        return f"~{seconds}s remaining"
    return ""


def format_dl_progress_line(downloaded: int, total: int, speed_bps: int, eta_sec: int) -> str:
    dl_downloaded, dl_total = human_bytes_pair(downloaded, total)
    parts = [f"{dl_downloaded} / {dl_total}", f"{human_bytes(speed_bps)}/s"]
    eta_str = format_eta(eta_sec)
    if eta_str:
        parts.append(eta_str)
    return "  ·  ".join(parts)
