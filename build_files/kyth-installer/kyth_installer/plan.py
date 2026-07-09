"""Install-plan/route-spec data types and the target-validation + destructive
free-space/NTFS-shrink partition preparation orchestration.

install_mode invariants:
  "wipe"        — bootc install to-disk. Requires disk in list_disks() (safe-scan
                  passed). Refused against the running system's disk unless
                  _IS_LIVE_SESSION (booting the live ISO), since to-disk wipes
                  whatever partition table is there, live root included.
  "alongside"   — bootc install to-filesystem against an existing empty(-ish)
                  Btrfs partition (list_partitions() alongside_candidate). Needs
                  --acknowledge-destructive alongside --skip-fetch-check because
                  the target mountpoint already has other partitions (e.g. a
                  populated /boot/efi) mounted under it; kyth-partition-install.sh
                  passes the same flag for the same reason. Verified in a
                  container repro (loop-mounted GPT disk, foreign-OS ESP content,
                  real bootc) that this flag does not change behavior on a clean
                  target — it exists for parity with the shell fallback, not
                  because it gates a real rejection in current bootc.
  "resize_ntfs" — _validate_resize_ntfs_target() shrinks a trailing NTFS
                  partition (must be the last partition on disk, see
                  _partitions_after()), then _prepare_ntfs_resize_target()
                  creates a Btrfs partition in the freed space and REWRITES
                  install_mode to "alongside" (target_partition = new partition)
                  before falling through to the alongside path above.
  "free_space"  — _validate_free_space_target() re-scans list_free_space() right
                  before committing (a stale UI selection must not partition
                  space that's no longer free), then _prepare_free_space_target()
                  creates a Btrfs partition in the chosen gap and likewise
                  rewrites install_mode to "alongside" before falling through.
                  Gaps below MIN_KYTHOS_BYTES (32 GiB) are never surfaced by
                  list_free_space().

Both resize_ntfs and free_space are thin front-ends onto the alongside path:
whatever protections/flags apply to "alongside" (see above) apply to them too.
"""

import shutil
import subprocess
from dataclasses import dataclass
from typing import Optional

from .config import MIN_KYTHOS_GIB, MIN_KYTHOS_BYTES
from .disk import (
    _human_size,
    _latest_partition_on_disk,
    _normal_device_path,
    _parent_disk,
    _partition_number,
    _partition_size_bytes,
    _partition_start_bytes,
    _partitions_after,
    _block_size_bytes,
    _safe_int,
    find_efi_partition,
    list_disks,
    list_free_space,
    list_partitions,
)
from .system import _as_root


@dataclass(frozen=True)
class InstallPlan:
    mode: str
    disk: Optional[str] = None
    target_partition: Optional[str] = None


@dataclass(frozen=True)
class RouteSpec:
    method: str
    path: str
    requires_auth: bool = True
    requires_same_origin: bool = False


ROUTES = {
    "index": RouteSpec("GET", "/", requires_auth=False),
    "config": RouteSpec("GET", "/api/config"),
    "disks": RouteSpec("GET", "/api/disks"),
    "partitions": RouteSpec("GET", "/api/partitions"),
    "free_space": RouteSpec("GET", "/api/free-space"),
    "stream": RouteSpec("GET", "/api/stream"),
    "log": RouteSpec("GET", "/api/log"),
    "timezones": RouteSpec("GET", "/api/timezones"),
    "start": RouteSpec("POST", "/api/start", requires_same_origin=True),
    "reboot": RouteSpec("POST", "/api/reboot", requires_same_origin=True),
}


def _normalized_install_mode(state: dict) -> str:
    return str(state.get("install_mode") or "wipe").strip().lower() or "wipe"


def _install_plan_from_state(state: dict) -> InstallPlan:
    return InstallPlan(
        mode=_normalized_install_mode(state),
        disk=state.get("disk"),
        target_partition=state.get("target_partition"),
    )


def _apply_install_plan(state: dict, plan: InstallPlan) -> None:
    state["install_mode"] = plan.mode
    if plan.disk is not None:
        state["disk"] = plan.disk
    if plan.target_partition is not None:
        state["target_partition"] = plan.target_partition


def _validate_install_target(config: dict) -> tuple[str, str | None]:
    mode = str(config.get("install_mode") or "wipe").strip().lower()
    disk = _normal_device_path(config.get("disk"))
    if not disk:
        raise RuntimeError("No target disk was selected.")

    safe_disks = {d["name"]: d for d in list_disks()}
    if disk not in safe_disks:
        raise RuntimeError("The selected disk is not a safe install target. Re-scan disks and choose a non-live, non-mounted disk.")

    if mode == "wipe":
        size_bytes = _safe_int(safe_disks[disk].get("size_bytes"))
        if size_bytes < MIN_KYTHOS_BYTES:
            raise RuntimeError(f"This disk is too small for KythOS. At least {MIN_KYTHOS_GIB} GiB is required.")
        return disk, None

    if mode == "alongside":
        target = _normal_device_path(config.get("target_partition"))
        if not target:
            raise RuntimeError("No target partition was selected for alongside installation.")
        if _parent_disk(target) != disk:
            raise RuntimeError("The selected partition does not belong to the selected disk.")
        partitions = {p["name"]: p for p in list_partitions(disk)}
        part = partitions.get(target)
        if not part:
            raise RuntimeError("The selected partition was not found during the final disk scan.")
        if part.get("efi"):
            raise RuntimeError("The EFI system partition cannot be used as the KythOS target partition.")
        if part.get("current"):
            raise RuntimeError("The selected partition is currently mounted by the live or running system.")
        if (part.get("fstype") or "").lower() != "btrfs":
            raise RuntimeError("Alongside installation requires an existing Btrfs target partition.")
        if not find_efi_partition(disk):
            raise RuntimeError("Alongside installation requires an EFI system partition on the selected disk.")
        return disk, target

    raise RuntimeError(f"Unsupported install mode: {mode}")


def _settle_block_devices():
    subprocess.run(_as_root(["partprobe"]), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    subprocess.run(["udevadm", "settle"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)


def _validate_resize_ntfs_target(config: dict) -> tuple[str, str, int]:
    disk = _normal_device_path(config.get("disk"))
    partition = _normal_device_path(config.get("resize_partition") or config.get("target_partition"))
    shrink_gib = _safe_int(config.get("resize_gib") or config.get("shrink_gib") or 0)

    if not disk:
        raise RuntimeError("No target disk was selected.")
    if not partition:
        raise RuntimeError("No NTFS partition was selected to shrink.")
    if shrink_gib < MIN_KYTHOS_GIB:
        raise RuntimeError(f"NTFS shrink install requires at least {MIN_KYTHOS_GIB} GiB for KythOS.")

    safe_disks = {d["name"]: d for d in list_disks()}
    if disk not in safe_disks:
        raise RuntimeError("The selected disk is not a safe install target.")
    if _parent_disk(partition) != disk:
        raise RuntimeError("The selected NTFS partition does not belong to the selected disk.")
    if _partitions_after(disk, partition):
        raise RuntimeError("This NTFS partition is not the last partition on the disk. Shrinking it would not create contiguous space for KythOS.")

    parts = {p["name"]: p for p in list_partitions(disk)}
    part = parts.get(partition)
    if not part:
        raise RuntimeError("The selected NTFS partition was not found during the final disk scan.")
    if part.get("efi") or part.get("current"):
        raise RuntimeError("The selected partition is currently mounted or reserved and cannot be resized.")
    if (part.get("fstype") or "").lower() not in ("ntfs", "ntfs3"):
        raise RuntimeError("Only NTFS partitions can be resized by this installer path.")
    if not find_efi_partition(disk):
        raise RuntimeError("NTFS resize installation requires an EFI system partition on the selected disk.")

    shrink_bytes = shrink_gib * 1024**3
    current_size = _safe_int(part.get("size_bytes")) or _partition_size_bytes(partition)
    remaining_size = current_size - shrink_bytes
    if remaining_size < 64 * 1024**3:
        raise RuntimeError("Refusing to leave the NTFS partition smaller than 64 GiB.")
    return disk, partition, shrink_bytes


def _prepare_ntfs_resize_target(config: dict, log) -> tuple[str, str]:
    disk, partition, shrink_bytes = _validate_resize_ntfs_target(config)
    missing = [cmd for cmd in ("ntfsresize", "parted", "partprobe", "udevadm", "mkfs.btrfs") if shutil.which(cmd) is None]
    if missing:
        raise RuntimeError(f"Required NTFS resize tools are missing from the live environment: {', '.join(missing)}")
    current_size = _partition_size_bytes(partition)
    new_ntfs_size = current_size - shrink_bytes
    part_num = _partition_number(partition)
    sector = _block_size_bytes(disk)
    new_end = _partition_start_bytes(partition) + new_ntfs_size - sector
    before = {p["name"] for p in list_partitions(disk) if p.get("name")}

    log(f"NTFS resize requested: shrink {partition} by {_human_size(shrink_bytes)}")
    log("Checking NTFS resize safety...")
    info = subprocess.run(["ntfsresize", "--info", partition], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=120)
    if info.returncode != 0:
        raise RuntimeError("NTFS partition is not clean enough to resize. Boot Windows, disable Fast Startup/hibernation, run chkdsk, and try again.")

    size_arg = str(new_ntfs_size)
    dry = subprocess.run(
        ["ntfsresize", "--no-action", "--size", size_arg, partition],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=240,
    )
    if dry.returncode != 0:
        raise RuntimeError("NTFS resize dry-run failed. Boot Windows, shrink the volume there, then return to the installer.")

    log("Shrinking NTFS filesystem...")
    subprocess.run(
        _as_root(["ntfsresize", "--force", "--size", size_arg, partition]),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
        timeout=1800,
    )

    log("Shrinking partition boundary...")
    subprocess.run(_as_root(["parted", "-s", disk, "unit", "B", "resizepart", str(part_num), f"{new_end}B"]), check=True, timeout=120)
    _settle_block_devices()

    log("Creating KythOS Btrfs partition in freed space...")
    subprocess.run(_as_root(["parted", "-s", disk, "mkpart", "KythOS", "btrfs", f"{new_end + sector}B", "100%"]), check=True, timeout=120)
    _settle_block_devices()

    created = _latest_partition_on_disk(disk, before)
    if not created:
        raise RuntimeError("The installer could not find the new KythOS partition after resizing.")
    subprocess.run(_as_root(["mkfs.btrfs", "-f", "-L", "KythOS", created]), check=True, timeout=300)
    log(f"Created target partition {created}")
    return disk, created


def _validate_free_space_target(config: dict) -> tuple[str, int, int]:
    disk = _normal_device_path(config.get("disk"))
    start = _safe_int(config.get("free_region_start"), -1)
    end = _safe_int(config.get("free_region_end"), -1)

    if not disk:
        raise RuntimeError("No target disk was selected.")
    if start < 0 or end <= start:
        raise RuntimeError("No free space region was selected for installation.")
    if end - start < MIN_KYTHOS_BYTES:
        raise RuntimeError(f"Free space install requires at least {MIN_KYTHOS_GIB} GiB for KythOS.")

    safe_disks = {d["name"]: d for d in list_disks()}
    if disk not in safe_disks:
        raise RuntimeError("The selected disk is not a safe install target.")
    if not find_efi_partition(disk):
        raise RuntimeError("Free space installation requires an EFI system partition on the selected disk.")

    # Re-scan right before committing so a stale UI selection can't partition
    # space that's no longer actually free.
    current_regions = list_free_space(disk)
    if not any(r["start_bytes"] <= start and r["end_bytes"] >= end for r in current_regions):
        raise RuntimeError("The selected free space is no longer available. Re-scan the disk and try again.")

    return disk, start, end


def _prepare_free_space_target(config: dict, log) -> tuple[str, str]:
    disk, start, end = _validate_free_space_target(config)
    missing = [cmd for cmd in ("parted", "partprobe", "udevadm", "mkfs.btrfs") if shutil.which(cmd) is None]
    if missing:
        raise RuntimeError(f"Required partitioning tools are missing from the live environment: {', '.join(missing)}")

    before = {p["name"] for p in list_partitions(disk) if p.get("name")}

    log(f"Creating KythOS Btrfs partition in {_human_size(end - start)} of free space...")
    subprocess.run(_as_root(["parted", "-s", disk, "unit", "B", "mkpart", "KythOS", "btrfs", f"{start}B", f"{end}B"]), check=True, timeout=120)
    _settle_block_devices()

    created = _latest_partition_on_disk(disk, before)
    if not created:
        raise RuntimeError("The installer could not find the new KythOS partition after partitioning.")
    subprocess.run(_as_root(["mkfs.btrfs", "-f", "-L", "KythOS", created]), check=True, timeout=300)
    log(f"Created target partition {created}")
    return disk, created


def _prepare_install_plan(state: dict, log) -> InstallPlan:
    plan = _install_plan_from_state(state)
    if plan.mode == "resize_ntfs":
        disk, target_partition = _prepare_ntfs_resize_target(state, log)
        plan = InstallPlan("alongside", disk=disk, target_partition=target_partition)
    elif plan.mode == "free_space":
        disk, target_partition = _prepare_free_space_target(state, log)
        plan = InstallPlan("alongside", disk=disk, target_partition=target_partition)
    _apply_install_plan(state, plan)
    return plan

