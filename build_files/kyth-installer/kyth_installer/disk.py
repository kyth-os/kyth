"""Pure disk/partition inspection helpers for kyth-installer.

Nothing here mutates block devices or the running system — see plan.py for
partitioning/formatting orchestration and system.py for account/mount
mutation. Kept dependency-free of the rest of kyth_installer (besides
config.py) so it can be unit tested in isolation.
"""

import json
import os
import subprocess
import sys
from typing import Optional

from .config import EFI_PART_GUID, MIN_KYTHOS_BYTES, _IS_LIVE_SESSION


def _human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _running_system_disk() -> str:
    # Returns the raw mount SOURCE for "/" (which may be a partition, an LVM
    # logical volume, or a LUKS dm-crypt mapping) — callers resolve this up
    # to the physical disk via _parent_disk(), which walks every layer of
    # device-mapper indirection rather than assuming a single PKNAME hop.
    try:
        source = subprocess.check_output(
            ["findmnt", "-n", "-o", "SOURCE", "/"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        ).strip()
    except Exception:
        return ""
    if not source or not source.startswith("/dev/"):
        return ""
    return source


def _get_live_usb_disk() -> Optional[str]:
    for path in ("/run/initramfs/live", "/run/initramfs/iso"):
        try:
            source = subprocess.check_output(
                ["findmnt", "-n", "-o", "SOURCE", path],
                text=True, stderr=subprocess.DEVNULL, timeout=5,
            ).strip()
            if not source or not source.startswith("/dev/"):
                continue
            try:
                pkname = subprocess.check_output(
                    ["lsblk", "-n", "-o", "PKNAME", source],
                    text=True, stderr=subprocess.DEVNULL, timeout=5,
                ).strip().splitlines()
                parent = next((line.strip() for line in pkname if line.strip()), "")
                if parent:
                    return f"/dev/{parent}"
            except Exception:
                pass
            try:
                disk = subprocess.check_output(
                    ["lsblk", "-n", "-o", "NAME,TYPE", source],
                    text=True, stderr=subprocess.DEVNULL, timeout=5,
                )
                for line in disk.splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[1] == "disk":
                        return f"/dev/{parts[0].lstrip('└─├─')}"
            except Exception:
                pass
            try:
                devtype = subprocess.check_output(
                    ["lsblk", "-n", "-o", "TYPE", source],
                    text=True, stderr=subprocess.DEVNULL, timeout=5,
                ).strip()
                if devtype == "disk":
                    return source
            except Exception:
                pass
        except Exception:
            pass
    return None


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
    dev = _normal_device_path(dev)
    if not dev:
        return ""
    out = _lsblk_text(["-n", "-o", "TYPE", dev])
    return out.splitlines()[0].strip() if out else ""


def _parent_disk(dev: str | None) -> str | None:
    # Walks every layer of indirection (partition, LVM LV/PV, LUKS mapper)
    # up to the underlying physical disk. A single PKNAME hop is not enough
    # for e.g. an LVM logical volume on a LUKS-encrypted partition, where
    # the immediate PKNAME is itself another non-disk device.
    dev = _normal_device_path(dev)
    seen: set[str] = set()
    while dev and dev not in seen:
        seen.add(dev)
        if _device_type(dev) == "disk":
            return dev
        parent = _lsblk_text(["-n", "-o", "PKNAME", dev])
        if not parent:
            return None
        dev = _normal_device_path(parent.splitlines()[0])
    return None


def _mount_sources(path: str, recursive: bool = False) -> set[str]:
    sources: set[str] = set()
    try:
        cmd = ["findmnt"]
        if recursive:
            cmd.append("-R")
        cmd.extend(["-n", "-o", "SOURCE", path])
        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL, timeout=5)
    except Exception:
        out = ""
    for line in out.splitlines():
        source = line.strip()
        if source.startswith("/dev/"):
            sources.add(os.path.realpath(source))
    return sources


def _protected_install_disks() -> set[str]:
    protected: set[str] = set()
    for dev in {_running_system_disk()}:
        disk = _parent_disk(dev)
        if disk:
            protected.add(disk)
    for mount in ("/", "/boot", "/boot/efi", "/sysroot", "/run/initramfs/live", "/run/initramfs/iso"):
        for source in _mount_sources(mount):
            disk = _parent_disk(source)
            if disk:
                protected.add(disk)
    for source in _mount_sources("/run/initramfs", recursive=True):
        disk = _parent_disk(source)
        if disk:
            protected.add(disk)
    for source in _mount_sources("/run/media", recursive=True):
        if _IS_LIVE_SESSION:
            disk = _parent_disk(source)
            if disk:
                protected.add(disk)
    return protected


def _disk_path_is_safe(path: str) -> bool:
    base = os.path.basename(path)
    if base.startswith(("loop", "ram", "zram")):
        return False
    return path.startswith("/dev/")


def list_disks():
    protected = _protected_install_disks()
    current_disk = _parent_disk(_running_system_disk())
    disks = []
    try:
        out = subprocess.check_output(
            ["lsblk", "--json", "--bytes", "--paths", "--nodeps", "--output", "NAME,SIZE,MODEL,TYPE,TRAN,ROTA,RM,RO,PTTYPE"],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        for d in json.loads(out).get("blockdevices", []):
            if d.get("type") != "disk":
                continue
            name = _normal_device_path(d.get("name"))
            if not name or not _disk_path_is_safe(name):
                continue
            size = _safe_int(d.get("size"))
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
    except Exception as exc:
        print(f"disk scan failed: {exc}", file=sys.stderr)
    return disks


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
        mounts.extend(_partition_mountpoints(child))
        mounts.extend(_descendant_mountpoints(child))
    return mounts


def list_partitions(disk: str, *, strict: bool = False):
    disk = _normal_device_path(disk)
    if not disk:
        return []
    parts = []
    try:
        out = subprocess.check_output(
            ["lsblk", "--json", "--bytes", "--paths", "--output", "NAME,SIZE,TYPE,FSTYPE,PARTTYPE,LABEL,MOUNTPOINT,MOUNTPOINTS,START", disk],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        devices = json.loads(out).get("blockdevices", [])

        def walk(items):
            for child in items or []:
                if child.get("type") == "part":
                    name = _normal_device_path(child.get("name"))
                    size = _safe_int(child.get("size"))
                    fstype = (child.get("fstype") or "").lower()
                    parttype = (child.get("parttype") or "").lower()
                    mounts = _partition_mountpoints(child) + _descendant_mountpoints(child)
                    is_efi = parttype == EFI_PART_GUID or (fstype == "vfat" and "/boot/efi" in mounts)
                    current = _is_active_mount(mounts)
                    in_use = bool(child.get("children"))
                    alongside_candidate = bool(
                        name and size >= MIN_KYTHOS_BYTES and not is_efi
                        and not current and not in_use
                    )
                    start_val = _safe_int(child.get("start"))
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
                        "alongside_candidate": alongside_candidate,
                    })
                walk(child.get("children"))

        walk(devices)
    except Exception as exc:
        print(f"partition scan failed for {disk}: {exc}", file=sys.stderr)
        if strict:
            raise RuntimeError(
                f"Could not read the partition table on {disk}. No storage changes were made."
            ) from exc
    return parts


def list_free_space(disk: str) -> list[dict]:
    """Return unallocated gaps on disk (>= MIN_KYTHOS_BYTES) as start/end/size in bytes."""
    disk = _normal_device_path(disk)
    if not disk:
        return []
    try:
        disk_size = _partition_size_bytes(disk)
        sector = _block_size_bytes(disk)
    except Exception as exc:
        print(f"free space scan failed for {disk}: {exc}", file=sys.stderr)
        return []

    try:
        partitions = list_partitions(disk, strict=True)
    except RuntimeError:
        return []

    spans = []
    for part in partitions:
        name = part.get("name")
        size = _safe_int(part.get("size_bytes"))
        if not name or size <= 0:
            return []
        try:
            start = _safe_int(part.get("start_bytes"), -1)
            if start < 0:
                start = _partition_start_bytes(name)
        except Exception:
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

    regions = []
    for start, end in gaps:
        aligned_start = ((start + sector - 1) // sector) * sector
        aligned_end = (end // sector) * sector
        size_bytes = aligned_end - aligned_start
        if size_bytes >= MIN_KYTHOS_BYTES:
            regions.append({
                "start_bytes": aligned_start,
                "end_bytes": aligned_end,
                "size_bytes": size_bytes,
                "size": _human_size(size_bytes),
            })
    return regions


def _partition_number(partition: str) -> int:
    out = _lsblk_text(["-n", "-o", "PARTN", partition])
    if not out:
        raise RuntimeError(f"Could not determine partition number for {partition}.")
    return _safe_int(out.splitlines()[0], 0)


def _partition_size_bytes(partition: str) -> int:
    out = _lsblk_text(["-b", "-n", "-o", "SIZE", partition])
    size = _safe_int(out.splitlines()[0] if out else 0)
    if size <= 0:
        raise RuntimeError(f"Could not determine partition size for {partition}.")
    return size


def _partition_start_bytes(partition: str) -> int:
    # lsblk's START column (and the kernel's underlying sysfs "start" attribute)
    # is always expressed in fixed 512-byte sectors, regardless of the device's
    # actual logical block size and regardless of the --bytes flag.
    out = _lsblk_text(["-b", "-n", "-o", "START", partition])
    start = _safe_int(out.splitlines()[0] if out else 0, -1)
    if start < 0:
        raise RuntimeError(f"Could not determine partition start for {partition}.")
    return start * 512


def list_filesystems() -> list[dict]:
    return [
        {"id": "btrfs", "name": "Btrfs", "root_ok": True, "efi_ok": False},
        {"id": "ext4", "name": "ext4", "root_ok": False, "efi_ok": False},
        {"id": "xfs", "name": "XFS", "root_ok": False, "efi_ok": False},
        {"id": "fat32", "name": "FAT32", "root_ok": False, "efi_ok": True},
        {"id": "linux-swap", "name": "Swap", "root_ok": False, "efi_ok": False},
    ]


def partition_has_active_mount(partition: str) -> bool:
    try:
        out = subprocess.check_output(
            ["findmnt", "-n", "-o", "TARGET", partition],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
        return bool(out.strip())
    except Exception:
        return False


def _block_size_bytes(device: str) -> int:
    try:
        out = subprocess.check_output(["blockdev", "--getss", device], text=True, stderr=subprocess.DEVNULL, timeout=5).strip()
        return max(512, _safe_int(out, 512))
    except Exception:
        return 512


def _partitions_after(disk: str, partition: str) -> list[dict]:
    part_start = _partition_start_bytes(partition)
    found = []
    try:
        out = subprocess.check_output(
            ["lsblk", "--json", "--bytes", "--paths", "--output", "NAME,TYPE,START,SIZE", disk],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
        stack = list(json.loads(out).get("blockdevices", []))
        while stack:
            item = stack.pop()
            if item.get("type") == "part":
                name = _normal_device_path(item.get("name"))
                if name and name != partition and _safe_int(item.get("start"), -1) * 512 > part_start:
                    found.append(item)
            stack.extend(item.get("children") or [])
    except Exception as exc:
        raise RuntimeError(
            f"Could not verify the partition order on {disk}. No storage changes were made."
        ) from exc
    return found


def _latest_partition_on_disk(disk: str, before: set[str]) -> str | None:
    after = {p["name"] for p in list_partitions(disk) if p.get("name")}
    created = list(after - before)
    if not created:
        return None
    import re
    def sort_key(name: str):
        return [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', name)]
    return sorted(created, key=sort_key)[-1]


def find_efi_partition(disk: str) -> str:
    """Return the EFI partition path on disk, or on another safe disk as fallback, or ''."""
    for part in list_partitions(disk):
        if part.get("efi"):
            return part["name"]
    try:
        for d in list_disks():
            other_disk = d.get("name")
            if other_disk and other_disk != disk:
                for part in list_partitions(other_disk):
                    if part.get("efi"):
                        return part["name"]
    except Exception:
        pass
    for mount in ("/boot/efi", "/efi"):
        try:
            out = subprocess.check_output(
                ["findmnt", "-n", "-o", "SOURCE", mount],
                text=True, stderr=subprocess.DEVNULL, timeout=5,
            ).strip()
            if out and out.startswith("/dev/"):
                return out
        except Exception:
            pass
    return ""


def get_root_partition(disk: str) -> str:
    try:
        out = subprocess.check_output(
            ["lsblk", "--json", "--bytes", "--output", "NAME,SIZE,TYPE", disk],
            text=True, stderr=subprocess.DEVNULL,
        )
        parts = []
        for d in json.loads(out).get("blockdevices", []):
            for c in d.get("children", []):
                if c.get("type") == "part":
                    parts.append((int(c.get("size", 0)), c["name"]))
        if parts:
            return "/dev/" + sorted(parts, reverse=True)[0][1]
    except Exception:
        pass
    try:
        out = subprocess.check_output(
            ["blkid", "--output", "device", "--match-types", "btrfs"],
            text=True, stderr=subprocess.DEVNULL,
        )
        for dev in out.splitlines():
            dev = dev.strip()
            if dev and dev.startswith(disk):
                return dev
    except Exception:
        pass
    raise RuntimeError(
        f"Cannot determine root partition on {disk}. "
        "lsblk and blkid both failed — check that the disk completed writing."
    )
