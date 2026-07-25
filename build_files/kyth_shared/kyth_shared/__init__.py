"""Shared utilities used by both kyth-installer and kyth-welcome.

These are small, pure-Python helpers with no Qt dependencies that both
sub-projects need in identical form. Keeping them here prevents drift
(e.g. one codebase handling IEC units and the other not).
"""

from __future__ import annotations

import time
from collections import deque


def _parse_size_bytes(size_str: str) -> int:
    """Parse ``'8.3 GB'``, ``'500 MB'``, or ``'2 GiB'`` to bytes.

    Returns 0 on failure so callers can treat 0 as "unknown/unparseable".
    Normalises IEC prefixes (GiB/MiB → GB/MB) internally.
    """
    try:
        parts = size_str.strip().split()
        value = float(parts[0])
        unit = parts[1].upper().rstrip("B") if len(parts) > 1 else ""
        unit = unit.replace("I", "")  # GiB/MiB → GB/MB
        mult = {"": 1, "K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
        return int(value * mult.get(unit, 0))
    except Exception:
        return 0


def _get_rx_bytes() -> int:
    """Return total received bytes across all non-loopback interfaces.

    Reads ``/proc/net/dev`` and sums the receive byte counter (column 2)
    for every interface except ``lo``.  Returns 0 on error.
    """
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


def _human_bytes(n: int | float) -> str:
    """Format a byte count as a human-readable string (e.g. ``'1.5 GB'``).

    Shows whole numbers for raw bytes, one decimal place for KB and above.
    """
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} TB"


def _human_bytes_pair(downloaded: int, total: int) -> tuple[str, str]:
    """Format a downloaded/total pair, e.g. ``('1.4', '1.5 GB')``.

    The unit appears only on the total element so callers can show
    ``f\"{dl_dl} / {dl_total}\"`` without redundant units.
    """
    for unit, threshold in (("GB", 1024**3), ("MB", 1024**2), ("KB", 1024)):
        if abs(total) >= threshold:
            return f"{downloaded / threshold:.1f}", f"{total / threshold:.1f} {unit}"
    return str(downloaded), f"{total} B"


class _NetStatsTracker:
    """Pure-Python rolling-window network throughput tracker.

    Polled by both the Qt ``DownloadMonitor`` (welcome) and the stdlib
    ``_net_monitor`` (installer).  Call ``tick(rx_now)`` once per second
    and read ``downloaded``, ``avg_speed``, and ``eta_sec`` from the
    returned dict.
    """

    def __init__(self, total_bytes: int, rx_start: int):
        self._total = total_bytes
        self._rx_start = rx_start
        self._rx_prev = 0
        self._t_prev = time.monotonic()
        self._samples: deque[float] = deque(maxlen=5)

    def tick(self, rx_now: int) -> dict[str, int]:
        downloaded = min(self._total, max(0, rx_now - self._rx_start))
        t_now = time.monotonic()
        dt = t_now - self._t_prev
        if dt > 0 and self._rx_prev > 0:
            delta = max(0, rx_now - self._rx_prev)
            if delta > 0:
                self._samples.append(delta / dt)
        self._rx_prev = rx_now
        self._t_prev = t_now

        avg_speed = int(sum(self._samples) / len(self._samples)) if self._samples else 0
        remaining = max(0, self._total - downloaded)
        eta_sec = int(remaining / avg_speed) if avg_speed > 0 else 0
        return {
            "downloaded": downloaded,
            "total": self._total,
            "speed": avg_speed,
            "eta_sec": eta_sec,
        }


from .apps import load_app_db, suggest_app

