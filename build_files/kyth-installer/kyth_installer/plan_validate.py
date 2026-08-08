"""Plan validation — pure checks before any destructive partition work.

Extracted from plan.py 788 monolith (step 2). No disk writes here;
commit path re-runs this as a guard. Keeps PlanReport as single gate.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .config import BIOS_BOOT_GUID, MIN_KYTHOS_BYTES, MIN_KYTHOS_GIB
from .disk import (
    _normal_device_path,
    _safe_int,
    find_efi_partition,
)
from .plan_types import PlanReport

if TYPE_CHECKING:
    from .storage_snapshot import StorageSnapshot

_logger = logging.getLogger(__name__)


def _validate_partition_target(
    disk: str,
    target: str,
    label: str,
    snapshot: StorageSnapshot | None = None,
) -> dict:
    """Validate `target` is a real, unmounted, adequately-sized, non-EFI partition."""
    # Resolve via plan module so mock.patch.object(plan, "list_partitions") works
    from . import plan as _plan_mod

    partitions = (
        snapshot.partitions_by_name
        if snapshot is not None
        else {p["name"]: p for p in _plan_mod.list_partitions(disk)}
    )
    part = partitions.get(target)
    if not part:
        raise RuntimeError(f"The selected {label} was not found during the final disk scan.")
    if part.get("efi"):
        raise RuntimeError(f"The EFI system partition cannot be used as the KythOS {label}.")
    if part.get("current") or part.get("in_use") or part.get("read_only"):
        raise RuntimeError(f"The selected {label} is mounted, read-only, or has active encrypted/LVM mappings.")
    if _safe_int(part.get("size_bytes")) < MIN_KYTHOS_BYTES:
        raise RuntimeError(f"The {label} is too small. At least {MIN_KYTHOS_GIB} GiB is required.")
    return part


def _validate_efi_target(config: dict, target: str, discovered: str | None) -> str:
    """Revalidate the exact ESP that the install will mount."""
    from . import plan as _plan_mod

    requested = _normal_device_path(config.get("efi_partition"))
    efi = requested or _normal_device_path(discovered)
    if not efi:
        raise RuntimeError("Alongside installation requires an EFI system partition on the system.")
    if efi == target:
        raise RuntimeError("The EFI system partition and KythOS target partition must be different.")
    if not requested:
        return efi
    efi_disk = _plan_mod._parent_disk(efi)
    if not efi_disk:
        raise RuntimeError("Could not determine which disk contains the EFI system partition.")
    efi_info = next((part for part in _plan_mod.list_partitions(efi_disk) if part.get("name") == efi), None)
    if not efi_info or not efi_info.get("efi"):
        raise RuntimeError("The selected EFI partition is no longer a valid EFI System Partition.")
    if efi_info.get("read_only"):
        raise RuntimeError("The selected EFI System Partition is read-only and cannot receive the KythOS bootloader.")
    return efi


def _validate_install_target(
    config: dict,
    context=None,
    snapshot: StorageSnapshot | None = None,
) -> tuple[str, str | None]:
    # Lazy imports to avoid cycle with plan.py + keep mock.patch.object(plan, ...) working
    from . import partition_ops
    from . import plan as _plan_mod
    from .plan import _probe_storage

    mode = str(config.get("install_mode") or "wipe").strip().lower()
    disk = _normal_device_path(config.get("disk"))
    if not disk:
        raise RuntimeError("No target disk was selected.")

    snapshot = snapshot or _probe_storage(disk, include_partitions=mode != "wipe")
    safe_disks = snapshot.disks_by_name
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
        if _plan_mod._parent_disk(target) != disk:
            raise RuntimeError("The selected partition does not belong to the selected disk.")
        _validate_partition_target(disk, target, "target partition", snapshot)
        if snapshot.is_gpt and not snapshot.has_bios_boot_partition(BIOS_BOOT_GUID):
            raise RuntimeError(
                "This GPT disk has no BIOS boot partition required by the KythOS bootloader. "
                "Choose unallocated space, shrink Windows, or erase the disk so the installer can create one."
            )
        _validate_efi_target(config, target, snapshot.efi_partition)
        return disk, target

    if mode == "manual":
        if context is None:
            raise RuntimeError("Manual installation requires an installer session context.")
        journal = partition_ops.get_journal(context)
        if not journal or not journal.committed:
            raise RuntimeError("Partition changes have not been committed. Return to the disk step and apply your partition layout.")
        target = _normal_device_path(journal.root_partition or config.get("target_partition"))
        if not target:
            raise RuntimeError("No root partition (/) found in the committed partition layout.")
        if _plan_mod._parent_disk(target) != disk:
            raise RuntimeError("The root partition does not belong to the selected disk.")
        _validate_partition_target(disk, target, "root partition", snapshot)
        _validate_efi_target(config, target, snapshot.efi_partition)
        return disk, target

    raise RuntimeError(f"Unsupported install mode: {mode}")
