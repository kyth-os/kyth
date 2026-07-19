"""util — _safe_int, _normal_device_path, _lsblk_text, _device_type, _block_size_bytes"""

from __future__ import annotations

import os

import kyth_installer.disk as _disk
subprocess = _disk.subprocess

def _safe_int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default



def _normal_device_path(name: str | None) -> str | None:
    if not name:
        return None
    name = str(name).strip()
    if not name:
        return None
    if not name.startswith("/dev/"):
        name = f"/dev/{name}"
    return os.path.realpath(name)



def _lsblk_text(args: list[str], timeout: int = 5) -> str:
    try:
        return subprocess.check_output(["lsblk", *args], text=True, stderr=subprocess.DEVNULL, timeout=timeout).strip()
    except Exception:
        return ""



def _device_type(dev: str | None) -> str:
    dev = _disk._normal_device_path(dev)
    if not dev:
        return ""
    out = _disk._lsblk_text(["-n", "-o", "TYPE", dev])
    return out.splitlines()[0].strip() if out else ""



def _block_size_bytes(device: str) -> int:
    try:
        out = subprocess.check_output(["blockdev", "--getss", device], text=True, stderr=subprocess.DEVNULL, timeout=5).strip()
        return max(512, _disk._safe_int(out, 512))
    except Exception:
        return 512



