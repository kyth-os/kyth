"""Read-only discovery helpers for installer planning."""

from __future__ import annotations

import contextlib
import logging
import re
import shutil

from .config import BIOS_BOOT_BYTES, BIOS_BOOT_GUID, MIN_KYTHOS_BYTES, MIN_KYTHOS_GIB
from .disk import _safe_int

_logger = logging.getLogger(__name__)


def is_gpt_disk(disk: str, *, run_command) -> bool:
    """Probe a disk's partition-table type without mutating it."""
    try:
        result = run_command(
            ["blkid", "-o", "value", "-s", "PTTYPE", disk],
            capture_output=True, text=True, check=True, timeout=5,
        )
        if result.stdout.strip().lower() == "gpt":
            return True
    except Exception:
        _logger.debug("GPT blkid probe failed for %r", disk, exc_info=True)
    try:
        result = run_command(
            ["parted", "-s", disk, "print"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        return "Partition Table: gpt" in result.stdout
    except Exception:
        return False


def has_bios_boot_partition(disk: str, *, list_partitions) -> bool:
    """Return whether a disk already contains the required BIOS boot partition."""
    return any(
        (part.get("parttype") or "").lower() == BIOS_BOOT_GUID
        for part in list_partitions(disk)
    )


def suggest_windows_resize_target(*, list_disks, probe_storage, snapshot=None) -> dict | None:
    """Return the largest viable NTFS partition across safe disks."""
    best = None
    all_disks = tuple(list_disks())
    for disk_info in all_disks:
        name = disk_info.get("name")
        if not name:
            continue
        try:
            current = (
                snapshot if snapshot and snapshot.disks_by_name.get(name)
                else probe_storage(name, disks=all_disks)
            )
        except Exception:
            continue
        for partition, info in current.partitions_by_name.items():
            if info.get("fstype", "").lower() != "ntfs":
                continue
            size = _safe_int(info.get("size_bytes"))
            if size < (64 + MIN_KYTHOS_GIB) * 1024**3:
                continue
            candidate = {
                "disk": name,
                "partition": partition,
                "size_bytes": size,
                "free_bytes": _safe_int(info.get("free_bytes") or 0),
            }
            if best is None or size > best["size_bytes"]:
                best = candidate
    return best


@contextlib.contextmanager
def disk_hold(disk: str, log):
    """Hold the shared exclusive storage lease through a planning mutation."""
    from .storage_guard import DiskLease

    with DiskLease(disk, log, exclusive=True):
        yield


def find_bootcurrent_esp(*, run_command, as_root, which=shutil.which) -> str | None:
    """Return the BootCurrent firmware entry, when efibootmgr can read it."""
    if which("efibootmgr") is None:
        return None
    try:
        result = run_command(
            as_root(["efibootmgr", "-v"]), capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        match = re.search(r"BootCurrent:\s*([0-9A-Fa-f]{4})", result.stdout)
        if not match:
            return None
        boot = match.group(1)
        return next(
            (line.strip() for line in result.stdout.splitlines()
             if line.strip().startswith(f"Boot{boot}")),
            None,
        )
    except Exception:
        return None


def required_guided_space(disk: str, *, is_gpt, has_bios_boot) -> int:
    """Return required guided-install bytes including a missing BIOS helper."""
    if is_gpt(disk) and not has_bios_boot(disk):
        return MIN_KYTHOS_BYTES + BIOS_BOOT_BYTES
    return MIN_KYTHOS_BYTES


def get_manual_mounts(context, *, get_journal, list_partitions) -> list[dict]:
    """Return non-root mount assignments from a committed manual journal."""
    journal = get_journal(context)
    if not journal or not journal.committed:
        return []
    if not getattr(journal, "disk", ""):
        raise RuntimeError("Committed partition journal has no target disk.")
    discovered = {
        part.get("name"): part for part in list_partitions(journal.disk)
        if part.get("name")
    }
    created = {
        op.get("params", {}).get("partition")
        for op in journal.ops if isinstance(op, dict) and op.get("kind") == "create"
    }
    mounts: list[dict] = []
    assigned_mountpoints: set[str] = set()
    assigned_partitions: set[str] = set()
    for op in journal.ops:
        if not isinstance(op, dict) or not isinstance(op.get("params"), dict):
            raise RuntimeError("Committed partition journal contains malformed operations.")
        if op.get("kind") not in ("create", "set_mountpoint"):
            continue
        mountpoint = str(op["params"].get("mountpoint", "")).strip()
        partition = str(op["params"].get("partition", "")).strip()
        if not mountpoint or mountpoint in ("/", "/boot/efi") or not partition:
            continue
        if partition not in discovered and partition not in created:
            raise RuntimeError(
                f"Manual mount target {partition} disappeared after partition commit."
            )
        if mountpoint in assigned_mountpoints:
            raise RuntimeError(f"Manual mount point {mountpoint} is assigned more than once.")
        if partition in assigned_partitions:
            raise RuntimeError(f"Manual partition {partition} has multiple mount assignments.")
        fs_type = op["params"].get("fs_type", "") if op["kind"] == "create" else ""
        for format_op in journal.ops:
            if (format_op["kind"] == "format"
                    and format_op["params"].get("partition") == partition):
                fs_type = format_op["params"].get("fs_type", "")
                break
        if not fs_type:
            fs_type = discovered.get(partition, {}).get("fstype", "")
        assigned_mountpoints.add(mountpoint)
        assigned_partitions.add(partition)
        mounts.append({
            "partition": partition,
            "mountpoint": mountpoint,
            "fstype": fs_type or "btrfs",
        })
    return mounts


__all__ = [
    "disk_hold", "find_bootcurrent_esp", "get_manual_mounts",
    "has_bios_boot_partition", "is_gpt_disk", "required_guided_space",
    "suggest_windows_resize_target",
]
