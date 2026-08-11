"""util — _safe_int, _normal_device_path, _lsblk_text, _lsblk_blockdevices, _lsblk_tree, _findmnt_source, _device_type, _block_size_bytes"""

from __future__ import annotations

import os

from kyth_shared.disk_utils import _normal_device_path as _pure_normal_path
from kyth_shared.disk_utils import _safe_int as _pure_safe_int
from kyth_shared.runtime_output import parse_lsblk_devices

import kyth_installer.disk as _disk

# Re-export pure helpers via the patchable seam — tests patch disk._safe_int etc.
def _safe_int(value, default: int = 0) -> int:
    return _pure_safe_int(value, default)


def _normal_device_path(name: str | None) -> str | None:
    return _pure_normal_path(name)



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
    return parse_lsblk_devices(result.stdout)



def _lsblk_tree() -> dict[str, dict]:
    """Single system-wide `lsblk --json --paths -o NAME,PKNAME,TYPE` snapshot,
    flattened into {normalized_device_path: {"pkname": normalized_path_or_None,
    "type": str}}.

    Ancestry walks (_parent_disk) used to re-invoke lsblk once per level of
    LVM/LUKS indirection (a TYPE check plus a PKNAME lookup, each its own
    subprocess). This lets a caller fetch the whole device graph once and
    resolve any number of ancestry walks against it with zero further
    subprocess spawns. Best-effort: returns an empty dict on failure, and
    callers fall back to the per-device lsblk calls for anything missing
    from it.
    """
    tree: dict[str, dict] = {}
    try:
        devices = _disk._lsblk_blockdevices(["--paths", "-o", "NAME,PKNAME,TYPE"])
    except Exception:
        return tree

    def walk(items):
        for item in items or []:
            name = _disk._normal_device_path(item.get("name"))
            if name:
                pkname = _disk._normal_device_path(item.get("pkname")) or None
                tree[name] = {"pkname": pkname, "type": (item.get("type") or "").strip()}
            walk(item.get("children"))

    walk(devices)
    return tree



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


