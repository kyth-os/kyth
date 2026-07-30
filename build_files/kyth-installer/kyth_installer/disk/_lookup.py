"""lookup — find_efi_partition, get_root_partition"""

from __future__ import annotations

import json
import logging

import kyth_installer.disk as _disk

_logger = logging.getLogger(__name__)

def find_efi_partition(disk: str) -> str:
    """Return the EFI partition path on disk, or on another safe disk as fallback, or ''."""
    for part in _disk.list_partitions(disk):
        if part.get("efi"):
            return part["name"]
    try:
        for d in _disk.list_disks():
            other_disk = d.get("name")
            if other_disk and other_disk != disk:
                for part in _disk.list_partitions(other_disk):
                    if part.get("efi"):
                        return part["name"]
    except Exception:
        _logger.debug("find_efi_partition: fallback scan of other disks failed", exc_info=True)
    try:
        protected = _disk._protected_install_disks()
    except Exception:
        _logger.debug("find_efi_partition: protected-disk lookup failed", exc_info=True)
        # Fail closed: if we can't determine what's protected, don't risk
        # handing back a live-media ESP as an install target.
        return ""
    for mount in ("/boot/efi", "/efi"):
        try:
            out = _disk._findmnt_source(mount)
            if not out:
                continue
            # This mount could be the live ISO/USB's own ESP (e.g. /boot/efi
            # inside the live session) rather than one on a real install
            # target — never hand that back, or the installer would bind-mount
            # the live media's boot partition and leave the installed system
            # with no bootloader once the USB is removed.
            if _disk._parent_disk(out) in protected:
                continue
            return out
        except Exception:
            _logger.debug("find_efi_partition: findmnt probe of %s failed", mount, exc_info=True)
    return ""



def get_root_partition(disk: str) -> str:
    try:
        result = _disk.run_command(
            ["lsblk", "--json", "--bytes", "--output", "NAME,SIZE,TYPE", disk],
            capture_output=True, text=True, check=True,
        )
        out = result.stdout
        parts = []
        for d in json.loads(out).get("blockdevices", []):
            for c in d.get("children", []):
                if c.get("type") == "part":
                    parts.append((int(c.get("size", 0)), c["name"]))
        if parts:
            return "/dev/" + sorted(parts, reverse=True)[0][1]
    except Exception:
        _logger.debug("get_root_partition: lsblk probe of %s failed", disk, exc_info=True)
    try:
        result = _disk.run_command(
            ["blkid", "--output", "device", "--match-types", "btrfs"],
            capture_output=True, text=True, check=True,
        )
        out = result.stdout
        for raw_dev in out.splitlines():
            dev = raw_dev.strip()
            if dev and dev.startswith(disk):
                return dev
    except Exception:
        _logger.debug("get_root_partition: blkid probe of %s failed", disk, exc_info=True)
    raise RuntimeError(
        f"Cannot determine root partition on {disk}. "
        "lsblk and blkid both failed — check that the disk completed writing."
    )

