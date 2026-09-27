"""lookup — find_efi_partition, get_root_partition"""

from __future__ import annotations

import json
import logging

import kyth_installer.disk as _disk

_logger = logging.getLogger(__name__)

def find_efi_partition(disk: str) -> str:
    """Return the EFI System Partition on the target disk, or ''."""
    target = _disk._normal_device_path(disk) or disk
    for part in _disk.list_partitions(disk):
        if part.get("efi"):
            return part["name"]
    # Never scan other disks: an ESP on a second drive is not this install's
    # bootloader target, and the live ISO/USB ESP is especially dangerous.
    try:
        protected = _disk._protected_install_disks()
    except Exception:  # noqa: BLE001 -- broad: must catch StopIteration from mock side_effect and other probe failures
        _logger.debug("find_efi_partition: protected-disk lookup failed", exc_info=True)
        # Fail closed: if we can't determine what's protected, don't risk
        # handing back a live-media ESP as an install target.
        return ""
    for mount in ("/boot/efi", "/efi"):
        try:
            out = _disk._findmnt_source(mount)
            if not out:
                continue
            parent = _disk._parent_disk(out)
            # Only reuse a currently-mounted ESP when it is on the selected
            # install disk and is not the live session's own media.
            if parent in protected or parent != target:
                continue
            return out
        except Exception:  # noqa: BLE001 -- broad: must catch StopIteration from mock side_effect and other probe failures
            _logger.debug("find_efi_partition: findmnt probe of %s failed", mount, exc_info=True)
    return ""



def _partition_devpath(name: str) -> str:
    return name if str(name).startswith("/") else f"/dev/{name}"


def _blkid_btrfs_on_disk(disk: str) -> str:
    result = _disk.run_command(
        ["blkid", "--output", "device", "--match-types", "btrfs"],
        capture_output=True, text=True, check=True,
    )
    for raw_dev in result.stdout.splitlines():
        dev = raw_dev.strip()
        if dev and dev.startswith(disk):
            return dev
    return ""


def get_root_partition(disk: str) -> str:
    """Pick the KythOS root filesystem on disk — never a larger foreign OS."""
    parts: list[dict] = []
    try:
        result = _disk.run_command(
            ["lsblk", "--json", "--bytes", "--output", "NAME,SIZE,TYPE,FSTYPE,LABEL", disk],
            capture_output=True, text=True, check=True,
        )
        for d in json.loads(result.stdout).get("blockdevices", []):
            for c in d.get("children", []):
                if c.get("type") == "part":
                    parts.append({
                        "name": _partition_devpath(c["name"]),
                        "size": int(c.get("size", 0) or 0),
                        "fstype": (c.get("fstype") or "").lower(),
                        "label": c.get("label") or "",
                    })
    except Exception:  # noqa: BLE001 -- broad: must catch StopIteration from mock side_effect and other probe failures
        _logger.debug("get_root_partition: lsblk probe of %s failed", disk, exc_info=True)

    labeled = [p for p in parts if p["label"] == "KythOS"]
    if labeled:
        return max(labeled, key=lambda p: p["size"])["name"]
    btrfs = [p for p in parts if p["fstype"] == "btrfs"]
    if btrfs:
        return max(btrfs, key=lambda p: p["size"])["name"]

    try:
        blkid = _blkid_btrfs_on_disk(disk)
        if blkid:
            return blkid
    except Exception:  # noqa: BLE001 -- broad: must catch StopIteration from mock side_effect and other probe failures
        _logger.debug("get_root_partition: blkid probe of %s failed", disk, exc_info=True)

    if parts and all(not p["fstype"] for p in parts):
        # lsblk omitted FSTYPE (legacy probe / incomplete JSON) — largest last-resort.
        return max(parts, key=lambda p: p["size"])["name"]
    if len(parts) == 1:
        return parts[0]["name"]
    if parts:
        raise RuntimeError(
            f"Cannot determine root partition on {disk}: "
            "no btrfs or LABEL=KythOS partition found."
        )
    raise RuntimeError(
        f"Cannot determine root partition on {disk}. "
        "lsblk and blkid both failed — check that the disk completed writing."
    )

