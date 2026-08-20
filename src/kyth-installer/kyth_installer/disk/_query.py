"""query — _partition_mountpoints, _is_active_mount, _descendant_mountpoints, list_disks, list_partitions, list_free_space, _partition_number, _partition_size_bytes, _partition_start_bytes, _partitions_after, _latest_partition_on_disk, list_filesystems"""

from __future__ import annotations

import logging
import sys

import kyth_installer.disk as _disk

from ..config import EFI_PART_GUID, MIN_KYTHOS_BYTES
from kyth_shared import human_bytes as _human_size

_logger = logging.getLogger(__name__)

def _partition_mountpoints(child: dict) -> list[str]:
    mounts = child.get("mountpoints")
    if isinstance(mounts, list):
        return [str(m) for m in mounts if m]
    mount = child.get("mountpoint")
    return [str(mount)] if mount else []



def _is_active_mount(mounts: list[str]) -> bool:
    return bool(mounts)



def _descendant_mountpoints(device: dict) -> list[str]:
    mounts: list[str] = []
    for child in device.get("children") or []:
        mounts.extend(_disk._partition_mountpoints(child))
        mounts.extend(_disk._descendant_mountpoints(child))
    return mounts



def list_disks():
    # Fetch the device tree and running-system disk once and share them with
    # both _protected_install_disks() and the current-disk resolution below,
    # instead of each independently re-walking ancestry from scratch.
    tree = _disk._lsblk_tree()
    running_disk = _disk._running_system_disk()
    protected = _disk._protected_install_disks(tree=tree, running_disk=running_disk)
    current_disk = _disk._parent_disk(running_disk, tree=tree)
    disks = []
    try:
        blockdevices = _disk._lsblk_blockdevices(
            ["--paths", "--nodeps", "--output", "NAME,SIZE,MODEL,TYPE,TRAN,ROTA,RM,RO,PTTYPE"]
        )
        for d in blockdevices:
            if d.get("type") != "disk":
                continue
            name = _disk._normal_device_path(d.get("name"))
            if not name or not _disk._disk_path_is_safe(name):
                continue
            size = _disk._safe_int(d.get("size"))
            if size <= 0 or bool(d.get("ro")):
                continue
            if name in protected:
                continue
            disks.append({
                "name": name,
                "size": _human_size(size),
                "size_bytes": size,
                "model": (d.get("model") or "Unknown drive").strip(),
                "ssd": not bool(d.get("rota")),
                "transport": d.get("tran") or "",
                "removable": bool(d.get("rm")),
                "partition_table": (d.get("pttype") or "").lower(),
                "current": bool(current_disk) and name == current_disk,
            })
    except (OSError, ValueError, RuntimeError) as exc:  # noqa: BLE001 -- narrow: lsblk/subprocess failures are OSError/RuntimeError
        _logger.debug("disk scan failed: %s", exc, exc_info=True)
        print(f"disk scan failed: {exc}", file=sys.stderr)
    return disks



def list_partitions(disk: str, *, strict: bool = False):
    disk = _disk._normal_device_path(disk)
    if not disk:
        return []
    parts = []
    try:
        devices = _disk._lsblk_blockdevices(
            ["--paths", "--output", "NAME,SIZE,TYPE,FSTYPE,PARTTYPE,LABEL,MOUNTPOINT,MOUNTPOINTS,START,RO", disk]
        )

        def walk(items):
            for child in items or []:
                if child.get("type") == "part":
                    name = _disk._normal_device_path(child.get("name"))
                    size = _disk._safe_int(child.get("size"))
                    fstype = (child.get("fstype") or "").lower()
                    parttype = (child.get("parttype") or "").lower()
                    mounts = _disk._partition_mountpoints(child) + _disk._descendant_mountpoints(child)
                    is_efi = parttype == EFI_PART_GUID or (fstype == "vfat" and "/boot/efi" in mounts)
                    current = _disk._is_active_mount(mounts)
                    in_use = bool(child.get("children"))
                    read_only = bool(child.get("ro"))
                    alongside_candidate = bool(
                        name and size >= MIN_KYTHOS_BYTES and not is_efi
                        and not current and not in_use and not read_only
                    )
                    ntfs_resize_candidate = bool(
                        alongside_candidate
                        and fstype in ("ntfs", "ntfs3")
                        and size >= (64 * 1024**3) + MIN_KYTHOS_BYTES
                    )
                    start_val = _disk._safe_int(child.get("start"))
                    start_bytes = start_val * 512
                    parts.append({
                        "name": name,
                        "size": _human_size(size),
                        "size_bytes": size,
                        "start_bytes": start_bytes,
                        "fstype": fstype,
                        "label": child.get("label") or "",
                        "parttype": parttype,
                        "mountpoints": mounts,
                        "efi": is_efi,
                        "current": current,
                        "in_use": in_use,
                        "read_only": read_only,
                        "alongside_candidate": alongside_candidate,
                        "ntfs_resize_candidate": ntfs_resize_candidate,
                    })
                walk(child.get("children"))

        walk(devices)
    except (OSError, ValueError, RuntimeError) as exc:  # noqa: BLE001 -- narrow: lsblk JSON/subprocess failures
        _logger.debug("partition scan failed for %s: %s", disk, exc, exc_info=True)
        print(f"partition scan failed for {disk}: {exc}", file=sys.stderr)
        if strict:
            raise RuntimeError(
                f"Could not read the partition table on {disk}. No storage changes were made."
            ) from exc
    return parts



def list_free_space(disk: str) -> list[dict]:
    """Return unallocated gaps on disk (>= MIN_KYTHOS_BYTES) as start/end/size in bytes."""
    disk = _disk._normal_device_path(disk)
    if not disk:
        return []
    try:
        disk_size = _disk._partition_size_bytes(disk)
        sector = _disk._block_size_bytes(disk)
    except (OSError, ValueError, RuntimeError) as exc:  # noqa: BLE001 -- narrow: block-size probe failures
        _logger.debug("free space scan failed for %s: %s", disk, exc, exc_info=True)
        print(f"free space scan failed for {disk}: {exc}", file=sys.stderr)
        return []

    try:
        partitions = _disk.list_partitions(disk, strict=True)
    except RuntimeError:
        return []

    spans = []
    for part in partitions:
        name = part.get("name")
        size = _disk._safe_int(part.get("size_bytes"))
        if not name or size <= 0:
            return []
        try:
            # start_bytes from lsblk is already bytes (512*START), but on
            # 4K-native devices the alignment sector differs. Keep raw byte
            # value; gap alignment below uses the device's logical sector so
            # 512 vs 4096 mismatch cannot hide an exact-match free region
            # from validate_plan_state's contains_free_region check.
            start = _disk._safe_int(part.get("start_bytes"), -1)
            if start < 0:
                start = _disk._partition_start_bytes(name)
            # Normalize to sector alignment to avoid 512/4096 drift causing
            # exact-match failures on 4K-native disks (gate #5).
            start = (start // sector) * sector
            # Also quantize size to sector to keep end = start+size aligned
            size = (size // sector) * sector
            if size <= 0:
                return []
        except (OSError, ValueError, RuntimeError) as exc:
            _logger.debug("free-space region computation failed for %s: %s", disk, exc, exc_info=True)
            return []
        if start < 0 or start + size > disk_size:
            return []
        spans.append((start, start + size))
    spans.sort()

    # Leave the first MiB (GPT header + alignment) and the last MiB (GPT backup
    # header/table) alone, matching the alignment parted itself uses.
    reserve = 1024 * 1024
    cursor = reserve
    usable_end = disk_size - reserve

    gaps = []
    for start, end in spans:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < usable_end:
        gaps.append((cursor, usable_end))

    # On GPT without a BIOS boot partition the guided flow needs an extra 1 MiB
    # for GRUB (MIN+BIOS_BOOT). Filter at that higher threshold so the UI
    # never offers a gap that would later fail validate_plan_state after the
    # user confirms destructive work. Probe best-effort — fallback to MIN on
    # probe failure to avoid hiding usable space.
    try:
        from ..config import BIOS_BOOT_BYTES
        from ..plan import _is_gpt_disk as _check_gpt, _has_bios_boot_partition as _check_bios

        _is_gpt = _check_gpt(disk)
        _has_bios = _check_bios(disk) if _is_gpt else True
        required = MIN_KYTHOS_BYTES + (BIOS_BOOT_BYTES if _is_gpt and not _has_bios else 0)
    except (OSError, ValueError, AttributeError, RuntimeError) as exc:
        _logger.debug("min-required-bytes fallback for %s: %s", disk, exc, exc_info=True)
        required = MIN_KYTHOS_BYTES

    regions = []
    for start, end in gaps:
        aligned_start = ((start + sector - 1) // sector) * sector
        aligned_end = (end // sector) * sector
        size_bytes = aligned_end - aligned_start
        if size_bytes >= required:
            regions.append({
                "start_bytes": aligned_start,
                "end_bytes": aligned_end,
                "size_bytes": size_bytes,
                "size": _human_size(size_bytes),
            })
    return regions



def _partition_number(partition: str) -> int:
    out = _disk._lsblk_text(["-n", "-o", "PARTN", partition])
    if not out:
        raise RuntimeError(f"Could not determine partition number for {partition}.")
    return _disk._safe_int(out.splitlines()[0], 0)



def _partition_size_bytes(partition: str) -> int:
    out = _disk._lsblk_text(["-b", "-n", "-o", "SIZE", partition])
    size = _disk._safe_int(out.splitlines()[0] if out else 0)
    if size <= 0:
        raise RuntimeError(f"Could not determine partition size for {partition}.")
    return size



def _partition_start_bytes(partition: str) -> int:
    # lsblk's START column (and the kernel's underlying sysfs "start" attribute)
    # is always expressed in fixed 512-byte sectors, regardless of the device's
    # actual logical block size and regardless of the --bytes flag.
    out = _disk._lsblk_text(["-b", "-n", "-o", "START", partition])
    start = _disk._safe_int(out.splitlines()[0] if out else 0, -1)
    if start < 0:
        raise RuntimeError(f"Could not determine partition start for {partition}.")
    return start * 512



def _partitions_after(disk: str, partition: str) -> list[dict]:
    part_start = _disk._partition_start_bytes(partition)
    found = []
    try:
        stack = list(_disk._lsblk_blockdevices(["--paths", "--output", "NAME,TYPE,START,SIZE", disk]))
        while stack:
            item = stack.pop()
            if item.get("type") == "part":
                name = _disk._normal_device_path(item.get("name"))
                if name and name != partition and _disk._safe_int(item.get("start"), -1) * 512 > part_start:
                    found.append(item)
            stack.extend(item.get("children") or [])
    except Exception as exc:
        raise RuntimeError(
            f"Could not verify the partition order on {disk}. No storage changes were made."
        ) from exc
    return found



def _latest_partition_on_disk(disk: str, before: set[str]) -> str | None:
    after = {p["name"] for p in _disk.list_partitions(disk) if p.get("name")}
    created = list(after - before)
    if not created:
        return None
    import re
    def sort_key(name: str):
        return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', name)]
    return sorted(created, key=sort_key)[-1]



def list_filesystems() -> list[dict]:
    return [
        {"id": "btrfs", "name": "Btrfs", "root_ok": True, "efi_ok": False},
        {"id": "ext4", "name": "ext4", "root_ok": False, "efi_ok": False},
        {"id": "xfs", "name": "XFS", "root_ok": False, "efi_ok": False},
        {"id": "fat32", "name": "FAT32", "root_ok": False, "efi_ok": True},
        {"id": "linux-swap", "name": "Swap", "root_ok": False, "efi_ok": False},
    ]


