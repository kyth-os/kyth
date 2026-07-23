"""Process helpers and short-lived probe cache.

Pure stdlib utilities shared by System Hub services and CLI helpers. No Qt.

In-process cache (seconds) is short so post-mutation refreshes stay accurate.
For keys registered in ``services.probe.DISK_TTL``, a disk-backed cache written
by ``kyth-probe`` (and write-through on live fetch) warms cold Hub starts.
"""
from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")

_logger = logging.getLogger(__name__)


def _is_live_session() -> bool:
    try:
        with open("/proc/cmdline") as _f:
            return "kyth.live" in _f.read()
    except OSError:
        return False

# Short-lived cache for expensive read-only probes (bootc status, flatpak list).
# Helpers that would otherwise each spawn the same command share one snapshot.
# Worker completion invalidates so post-operation refreshes stay accurate.
_PROBE_CACHE_LOCK = threading.Lock()
_PROBE_CACHE: dict[str, tuple[float, object]] = {}
_BOOTC_CACHE_TTL = 5.0
_FLATPAK_CACHE_TTL = 10.0

# Keys that participate in the on-disk probe cache (see services.probe).
_DISK_BACKED_KEYS = frozenset({
    "bootc-status-data",
    "bootc-status-text",
    "bootc-branch",
    "kernel-flavor",
    "flatpak-apps",
    "flatpak-updates",
    "nvidia-detect",
    "controllers-detect",
})


def _run_command(cmd: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except Exception:
        return None


def _command_stdout(cmd: list[str], timeout: int = 5) -> str:
    result = _run_command(cmd, timeout=timeout)
    if result is None:
        return ""
    return result.stdout.strip()


def _strip_ansi(text: str) -> str:
    """Strip ANSI CSI escape sequences (color, cursor movement, etc.)."""
    return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", text)


def _with_idle_inhibit(cmd: list[str], reason: str) -> list[str]:
    inhibit = shutil.which("systemd-inhibit")
    if not inhibit:
        return cmd
    return [inhibit, "--what=idle:sleep", f"--why={reason}", "--mode=block", *cmd]


def _invalidate_probe_caches() -> None:
    with _PROBE_CACHE_LOCK:
        _PROBE_CACHE.clear()
    try:
        from .probe import invalidate_disk_sections
        invalidate_disk_sections(_DISK_BACKED_KEYS)
    except Exception:
        _logger.warning("_invalidate_probe_caches: disk cache invalidation failed — stale values may be served", exc_info=True)


def _disk_section_usable(key: str, data: object) -> bool:
    """Whether a disk section value is safe to serve as a cache hit.

    ``False`` (e.g. nvidia absent) and ``0`` (no flatpak updates) are usable.
    ``None`` / empty sentinels are not.
    """
    if data is None:
        return False
    if key == "bootc-status-text" and data == "":
        return False
    if key == "bootc-branch" and data == "":
        return False
    return True


def _probe_cached(key: str, ttl: float, fetch: Callable[[], T]) -> T:
    with _PROBE_CACHE_LOCK:
        hit = _PROBE_CACHE.get(key)
        if hit is not None and time.monotonic() - hit[0] < ttl:
            return hit[1]  # type: ignore[return-value]

    # Warm path: on-disk cache from kyth-probe (or prior write-through).
    if key in _DISK_BACKED_KEYS:
        try:
            from .probe import DISK_TTL, read_section

            disk_hit = read_section(key, max_age=max(ttl, DISK_TTL.get(key, ttl)))
            if _disk_section_usable(key, disk_hit):
                with _PROBE_CACHE_LOCK:
                    mem = _PROBE_CACHE.get(key)
                    if mem is not None and time.monotonic() - mem[0] < ttl:
                        return mem[1]  # type: ignore[return-value]
                    _PROBE_CACHE[key] = (time.monotonic(), disk_hit)
                return disk_hit  # type: ignore[return-value]
        except Exception:
            _logger.debug("_probe_cached: disk cache read for %r failed", key, exc_info=True)

    value = fetch()
    with _PROBE_CACHE_LOCK:
        hit = _PROBE_CACHE.get(key)
        if hit is not None and time.monotonic() - hit[0] < ttl:
            return hit[1]  # type: ignore[return-value]
        _PROBE_CACHE[key] = (time.monotonic(), value)

    if key in _DISK_BACKED_KEYS:
        try:
            from .probe import update_sections

            update_sections({key: value})
        except Exception:
            _logger.debug("_probe_cached: disk cache write for %r failed", key, exc_info=True)
    return value


def _get_disk_write_bytes() -> int:
    """Sum write bytes across all block devices from /proc/diskstats."""
    try:
        total = 0
        with open("/proc/diskstats") as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 10:
                    total += int(parts[9])  # sectors written (512 bytes each)
        return total * 512
    except Exception:
        return 0


# pylint: disable-next=unused-import
from kyth_shared import _get_rx_bytes, _human_bytes, _human_bytes_pair, _parse_size_bytes  # noqa: F401
