"""Process helpers and short-lived probe cache.

Pure stdlib utilities shared by system services and CLI helpers. No Qt.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time
from typing import Callable, TypeVar

from kyth_shared.commands import command_stdout as _raw_command_stdout, run_text

T = TypeVar("T")

_logger = logging.getLogger(__name__)


def is_live_session() -> bool:
    try:
        with open("/proc/cmdline") as _f:
            return "kyth.live" in _f.read()
    except OSError:
        return False


PROBE_CACHE_LOCK = threading.Lock()
PROBE_CACHE: dict[str, tuple[float, object]] = {}
BOOTC_CACHE_TTL = 5.0
FLATPAK_CACHE_TTL = 10.0

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


def invalidate_probe_caches() -> None:
    with PROBE_CACHE_LOCK:
        PROBE_CACHE.clear()
    try:
        from kyth_shared.system.probe import invalidate_disk_sections
        invalidate_disk_sections(DISK_BACKED_KEYS)
    except Exception:
        _logger.warning("invalidate_probe_caches: disk cache invalidation failed — stale values may be served", exc_info=True)


def disk_section_usable(key: str, data: object) -> bool:
    """Whether a disk section value is safe to serve as a cache hit."""
    if data is None:
        return False
    if key == "bootc-status-text" and data == "":
        return False
    if key == "bootc-branch" and data == "":
        return False
    return True


def probe_cached(key: str, ttl: float, fetch: Callable[[], T]) -> T:
    with PROBE_CACHE_LOCK:
        hit = PROBE_CACHE.get(key)
        if hit is not None and time.monotonic() - hit[0] < ttl:
            return hit[1]  # type: ignore[return-value]

    # Warm path: on-disk cache from kyth-probe (or prior write-through).
    if key in DISK_BACKED_KEYS:
        try:
            from kyth_shared.system.probe import DISK_TTL, read_section

            disk_hit = read_section(key, max_age=max(ttl, DISK_TTL.get(key, ttl)))
            if disk_section_usable(key, disk_hit):
                with PROBE_CACHE_LOCK:
                    mem = PROBE_CACHE.get(key)
                    if mem is not None and time.monotonic() - mem[0] < ttl:
                        return mem[1]  # type: ignore[return-value]
                    PROBE_CACHE[key] = (time.monotonic(), disk_hit)
                return disk_hit  # type: ignore[return-value]
        except Exception:
            _logger.debug("probe_cached: disk cache read for %r failed", key, exc_info=True)

    value = fetch()
    with PROBE_CACHE_LOCK:
        hit = PROBE_CACHE.get(key)
        if hit is not None and time.monotonic() - hit[0] < ttl:
            return hit[1]  # type: ignore[return-value]
        PROBE_CACHE[key] = (time.monotonic(), value)

    if key in DISK_BACKED_KEYS:
        try:
            from kyth_shared.system.probe import update_sections

            update_sections({key: value})
        except Exception:
            _logger.debug("probe_cached: disk cache write for %r failed", key, exc_info=True)
    return value


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
