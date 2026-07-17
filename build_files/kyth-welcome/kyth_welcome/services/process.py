"""Process helpers and short-lived probe cache.

Pure stdlib utilities shared by System Hub services and CLI helpers. No Qt.
"""
from __future__ import annotations

import shutil
import subprocess
import threading
import time
from typing import Callable, TypeVar

T = TypeVar("T")


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


def _run_command(cmd: list[str], timeout: int = 5) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception:
        return None


def _command_stdout(cmd: list[str], timeout: int = 5) -> str:
    result = _run_command(cmd, timeout=timeout)
    if result is None:
        return ""
    return result.stdout.strip()


def _with_idle_inhibit(cmd: list[str], reason: str) -> list[str]:
    inhibit = shutil.which("systemd-inhibit")
    if not inhibit:
        return cmd
    return [inhibit, "--what=idle:sleep", f"--why={reason}", "--mode=block", *cmd]


def _invalidate_probe_caches() -> None:
    with _PROBE_CACHE_LOCK:
        _PROBE_CACHE.clear()


def _probe_cached(key: str, ttl: float, fetch: Callable[[], T]) -> T:
    with _PROBE_CACHE_LOCK:
        hit = _PROBE_CACHE.get(key)
        if hit is not None and time.monotonic() - hit[0] < ttl:
            return hit[1]  # type: ignore[return-value]
        value = fetch()
        _PROBE_CACHE[key] = (time.monotonic(), value)
        return value


def _get_rx_bytes() -> int:
    """Sum RX bytes across all non-loopback interfaces from /proc/net/dev."""
    try:
        total = 0
        with open("/proc/net/dev") as f:
            for line in f:
                if ":" not in line:
                    continue
                iface, data = line.split(":", 1)
                if iface.strip() == "lo":
                    continue
                total += int(data.split()[0])
        return total
    except Exception:
        return 0


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


def _parse_size_bytes(size_str: str) -> int:
    """Parse '8.3 GB' or '500 MB' to bytes. Returns 0 on failure."""
    try:
        parts = size_str.strip().split()
        value = float(parts[0])
        unit = parts[1].upper().rstrip("B") if len(parts) > 1 else ""
        mult = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        return int(value * mult.get(unit, 0))
    except Exception:
        return 0


def _human_bytes(n: int) -> str:
    """Format bytes as a human-readable string."""
    for unit, threshold in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if abs(n) >= threshold:
            return f"{n / threshold:.1f} {unit}"
    return f"{n} B"


def _human_bytes_pair(downloaded: int, total: int) -> tuple[str, str]:
    """Format a downloaded/total pair using the same unit, anchored to total."""
    for unit, threshold in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if abs(total) >= threshold:
            return f"{downloaded / threshold:.1f}", f"{total / threshold:.1f} {unit}"
    return str(downloaded), f"{total} B"
