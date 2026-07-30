"""util — _safe_int, _normal_device_path, _lsblk_text, _lsblk_blockdevices, _findmnt_source, _device_type, _block_size_bytes"""

from __future__ import annotations

import json
import os
import re

import kyth_installer.disk as _disk

_SAFE_DEVICE_PATH_RE = re.compile(r"^/dev/[A-Za-z0-9._/+:-]+$")

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
    real = os.path.realpath(name)
    if not real.startswith("/dev/"):
        return None
    if not _SAFE_DEVICE_PATH_RE.fullmatch(real):
        return None
    return real



def _lsblk_text(args: list[str], timeout: int = 5) -> str:
    try:
        result = _disk.run_command(
            ["lsblk", *args], capture_output=True, text=True, check=True, timeout=timeout,
        )
        return result.stdout.strip()
    except Exception:
        return ""



def _findmnt_source(target: str, timeout: int = 5) -> str:
    """Return the mount SOURCE for `target` (a path), or "" if it isn't a
    real block device path. Propagates subprocess/timeout failures — some
    callers (e.g. _running_system_disk()) want to swallow those entirely,
    others (e.g. find_efi_partition()) want to log them, so this doesn't
    decide that for them."""
    result = _disk.run_command(
        ["findmnt", "-n", "-o", "SOURCE", target],
        capture_output=True, text=True, check=True, timeout=timeout,
    )
    source = result.stdout.strip()
    return source if source.startswith("/dev/") else ""



def _lsblk_blockdevices(args: list[str], timeout: int = 5) -> list[dict]:
    """Run `lsblk --json --bytes ...args` and return its top-level
    "blockdevices" list. Unlike _lsblk_text(), this does NOT swallow
    failures — callers in disk/_query.py each apply their own policy
    (log-and-continue with partial results, log-and-return-empty, or raise)
    and need the real exception to do that."""
    result = _disk.run_command(
        ["lsblk", "--json", "--bytes", *args],
        capture_output=True, text=True, check=True, timeout=timeout,
    )
    out = result.stdout
    return json.loads(out).get("blockdevices", [])



def _device_type(dev: str | None) -> str:
    dev = _disk._normal_device_path(dev)
    if not dev:
        return ""
    out = _disk._lsblk_text(["-n", "-o", "TYPE", dev])
    return out.splitlines()[0].strip() if out else ""



def _block_size_bytes(device: str) -> int:
    try:
        result = _disk.run_command(
            ["blockdev", "--getss", device],
            capture_output=True, text=True, check=True, timeout=5,
        )
        out = result.stdout.strip()
        return max(512, _disk._safe_int(out, 512))
    except Exception:
        return 512


