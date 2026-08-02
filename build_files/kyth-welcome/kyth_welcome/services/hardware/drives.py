"""NTFS/BitLocker drive listing and controller detection snapshot."""
from __future__ import annotations

import json
from kyth_shared.system.controllers import detect_controllers
from kyth_welcome.services.command import run_sync

from ..process import probe_cached


def _find_ntfs_drives() -> list[dict]:
    """Return other system NTFS and locked BitLocker partitions visible to lsblk."""
    try:
        r = run_sync(
            ["lsblk", "--json", "--output", "NAME,FSTYPE,SIZE,LABEL,MOUNTPOINT,PATH"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        data = json.loads(r.stdout)
    except Exception:
        return []

    results: list[dict] = []

    def _walk(devices: list):
        for dev in devices:
            if not isinstance(dev, dict):
                continue
            fstype = (dev.get("fstype") or "").lower()
            if fstype in ("ntfs", "ntfs3", "bitlocker"):
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

    _walk(data.get("blockdevices", []))
    return results
 # _find_ntfs_drives

def _detect_controllers() -> dict:
    """Snapshot of all connected controllers and driver state. Thread-safe."""
    return probe_cached("controllers-detect", 5.0, detect_controllers)
 # _detect_controllers
