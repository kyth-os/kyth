"""NTFS/BitLocker drive listing and controller detection snapshot."""
from __future__ import annotations

import subprocess

from kyth_shared.runtime_output import parse_lsblk_devices
from kyth_shared.system.controllers import detect_controllers
from kyth_welcome.services.command import run_sync

from ..process import probe_cached

_NTFS_LIKE_FSTYPES = ("ntfs", "ntfs3", "bitlocker")


def _find_ntfs_drives() -> list[dict]:
    """Return other system NTFS and locked BitLocker partitions visible to
    lsblk. probe_cached like _detect_controllers()/_detect_nvidia() below —
    this has several callers (page_welcome.py, page_gaming_dashboard.py,
    page_gaming_migration, services/work.py, services/gaming/health.py)
    that can land within the same TTL window, and an uncached lsblk spawn
    on every one of them added up across a single Gaming Hub visit."""
    return probe_cached("ntfs-drives", 30.0, _fetch_ntfs_drives)  # coalesce with hardware-probes window


def _fetch_ntfs_drives() -> list[dict]:
    try:
        r = run_sync(
            ["lsblk", "--json", "--output", "NAME,FSTYPE,SIZE,LABEL,MOUNTPOINT,PATH"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        devices = parse_lsblk_devices(r.stdout)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        import logging
        logging.getLogger(__name__).debug("lsblk parse failed: %s", exc, exc_info=True)
        return []

    results: list[dict] = []

    def _walk(devices: list):
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            fstype = (dev.get("fstype") or "").lower()
            if fstype in _NTFS_LIKE_FSTYPES:
                name = dev.get("name") or ""
                path = dev.get("path") or (f"/dev/{name}" if name else "")
                if not path:
                    continue
                results.append({
                    "dev":   path,
                    "name":  name,
                    "size":  dev.get("size", "?"),
                    "label": dev.get("label") or "",
                    "mount": dev.get("mountpoint") or "",
                    "is_bitlocker": fstype == "bitlocker",
                })
            _walk(dev.get("children") or [])

    _walk(devices)
    return results
 # _find_ntfs_drives

def _detect_controllers() -> dict:
    """Snapshot of all connected controllers and driver state. Thread-safe."""
    return probe_cached("controllers-detect", 120.0, detect_controllers)
 # _detect_controllers
