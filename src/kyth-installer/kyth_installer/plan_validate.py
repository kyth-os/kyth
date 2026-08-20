"""Plan validation — pure checks before any destructive partition work.

Extracted from plan.py 788 monolith (step 2). No disk writes here;
commit path re-runs this as a guard. Keeps PlanReport as single gate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from .config import BIOS_BOOT_BYTES, BIOS_BOOT_GUID, MIN_KYTHOS_BYTES, MIN_KYTHOS_GIB
from .disk import (
    _normal_device_path,
    _safe_int,
)

if TYPE_CHECKING:
    from .context import InstallRequest, InstallerContext
    from .storage_snapshot import StorageSnapshot

from .plan_types import PlanReport

_logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ValidationDependencies:
    """Read-only collaborators required to resolve an install target."""

    parent_disk: Callable[[str], str]
    list_partitions: Callable[[str], list[dict]]
    probe_storage: Callable[..., "StorageSnapshot"]
    get_journal: Callable[["InstallerContext"], object | None]


@dataclass(frozen=True, slots=True)
class GuidedValidationDependencies:
    """Read-only collaborators for guided resize/free-space validation."""

    probe_storage: Callable[..., "StorageSnapshot"]
    parent_disk: Callable[[str], str]
    partition_size: Callable[[str], int]


@dataclass(frozen=True, slots=True)
class ReportDependencies:
    """Pure collaborators needed to build a pre-mutation plan report."""

    as_request: Callable[[object], "InstallRequest"]
    normalized_mode: Callable[[object], str]
    probe_storage: Callable[..., "StorageSnapshot"]
    validate_install: Callable[..., tuple[str, str | None]]
    validate_resize: Callable[..., tuple[str, str, int]]
    validate_free_space: Callable[..., tuple[str, int, int]]


def validate_storage_intent(
    state, context=None, snapshot=None, *, normalized_mode, validate_install,
    validate_resize, validate_free_space,
) -> None:
    """Dispatch review-page validation without changing storage."""
    mode = normalized_mode(state)
    if mode == "resize_ntfs":
        validate_resize(state, snapshot=snapshot)
    elif mode == "free_space":
        validate_free_space(state, snapshot=snapshot)
    else:
        validate_install(state, context, snapshot=snapshot)


def default_validation_dependencies() -> ValidationDependencies:
    """Bind validation directly to production storage implementations."""
    from .disk import _parent_disk, list_partitions
    from .partition_ops import get_journal
    from .plan import _probe_storage

    return ValidationDependencies(
        parent_disk=_parent_disk,
        list_partitions=list_partitions,
        probe_storage=_probe_storage,
        get_journal=get_journal,
    )


def _validate_partition_target(
    disk: str,
    target: str,
    label: str,
    snapshot: StorageSnapshot | None = None,
    *,
    dependencies: ValidationDependencies | None = None,
) -> dict:
    """Validate `target` is a real, unmounted, adequately-sized, non-EFI partition."""
    dependencies = dependencies or default_validation_dependencies()

    partitions = (
        snapshot.partitions_by_name
        if snapshot is not None
        else {p["name"]: p for p in dependencies.list_partitions(disk)}
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


def _validate_efi_target(
    config: dict,
    target: str,
    discovered: str | None,
    *,
    dependencies: ValidationDependencies | None = None,
) -> str:
    """Revalidate the exact ESP that the install will mount."""
    dependencies = dependencies or default_validation_dependencies()

    requested = _normal_device_path(config.get("efi_partition"))
    efi = requested or _normal_device_path(discovered)
    if not efi:
        raise RuntimeError("Alongside installation requires an EFI system partition on the system.")
    if efi == target:
        raise RuntimeError("The EFI system partition and KythOS target partition must be different.")
    if not requested:
        return efi
    efi_disk = dependencies.parent_disk(efi)
    if not efi_disk:
        raise RuntimeError("Could not determine which disk contains the EFI system partition.")
    efi_info = next((part for part in dependencies.list_partitions(efi_disk) if part.get("name") == efi), None)
    if not efi_info or not efi_info.get("efi"):
        raise RuntimeError("The selected EFI partition is no longer a valid EFI System Partition.")
    if efi_info.get("read_only"):
        raise RuntimeError("The selected EFI System Partition is read-only and cannot receive the KythOS bootloader.")
    return efi


def _validate_install_target(
    config: dict,
    context=None,
    snapshot: StorageSnapshot | None = None,
    *,
    dependencies: ValidationDependencies | None = None,
) -> tuple[str, str | None]:
    dependencies = dependencies or default_validation_dependencies()

    mode = str(config.get("install_mode") or "wipe").strip().lower()
    disk = _normal_device_path(config.get("disk"))
    if not disk:
        raise RuntimeError("No target disk was selected.")

    snapshot = snapshot or dependencies.probe_storage(disk, include_partitions=mode != "wipe")
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
        if dependencies.parent_disk(target) != disk:
            raise RuntimeError("The selected partition does not belong to the selected disk.")
        _validate_partition_target(
            disk, target, "target partition", snapshot,
            dependencies=dependencies,
        )
        if snapshot.is_gpt and not snapshot.has_bios_boot_partition(BIOS_BOOT_GUID):
            raise RuntimeError(
                "This GPT disk has no BIOS boot partition required by the KythOS bootloader. "
                "Choose unallocated space, shrink Windows, or erase the disk so the installer can create one."
            )
        _validate_efi_target(
            config, target, snapshot.efi_partition,
            dependencies=dependencies,
        )
        return disk, target

    if mode == "manual":
        if context is None:
            raise RuntimeError("Manual installation requires an installer session context.")
        journal = dependencies.get_journal(context)
        if not journal or not journal.committed:
            raise RuntimeError("Partition changes have not been committed. Return to the disk step and apply your partition layout.")
        target = _normal_device_path(journal.root_partition or config.get("target_partition"))
        if not target:
            raise RuntimeError("No root partition (/) found in the committed partition layout.")
        if dependencies.parent_disk(target) != disk:
            raise RuntimeError("The root partition does not belong to the selected disk.")
        _validate_partition_target(
            disk, target, "root partition", snapshot,
            dependencies=dependencies,
        )
        _validate_efi_target(
            config, target, snapshot.efi_partition,
            dependencies=dependencies,
        )
        return disk, target

    raise RuntimeError(f"Unsupported install mode: {mode}")


def validate_resize_ntfs_target(
    config: dict,
    snapshot: StorageSnapshot | None = None,
    *,
    dependencies: GuidedValidationDependencies,
) -> tuple[str, str, int]:
    """Validate an NTFS shrink request without modifying its filesystem."""
    disk = _normal_device_path(config.get("disk"))
    partition = _normal_device_path(
        config.get("resize_partition") or config.get("target_partition")
    )
    shrink_gib = _safe_int(config.get("resize_gib") or config.get("shrink_gib") or 0)
    if not disk:
        raise RuntimeError("No target disk was selected.")
    if not partition:
        raise RuntimeError("No NTFS partition was selected to shrink.")
    if shrink_gib < MIN_KYTHOS_GIB:
        raise RuntimeError(
            f"NTFS shrink install requires at least {MIN_KYTHOS_GIB} GiB for KythOS."
        )
    snapshot = snapshot or dependencies.probe_storage(disk)
    if disk not in snapshot.disks_by_name:
        raise RuntimeError("The selected disk is not a safe install target.")
    if dependencies.parent_disk(partition) != disk:
        raise RuntimeError("The selected NTFS partition does not belong to the selected disk.")
    part = snapshot.partitions_by_name.get(partition)
    if not part:
        raise RuntimeError("The selected NTFS partition was not found during the final disk scan.")
    if part.get("efi") or part.get("current") or part.get("in_use") or part.get("read_only"):
        raise RuntimeError(
            "The selected partition is mounted, read-only, or reserved and cannot be resized."
        )
    filesystem = (part.get("fstype") or "").lower()
    if filesystem == "bitlocker":
        raise RuntimeError(
            "This partition is BitLocker-encrypted and cannot be resized while locked. "
            "In Windows, suspend or disable BitLocker protection and wait for decryption."
        )
    if filesystem not in ("ntfs", "ntfs3"):
        raise RuntimeError("Only NTFS partitions can be resized by this installer path.")
    if not snapshot.efi_partition:
        raise RuntimeError("NTFS resize installation requires an EFI system partition on the system.")
    shrink_bytes = shrink_gib * 1024**3
    required = (
        MIN_KYTHOS_BYTES + BIOS_BOOT_BYTES
        if snapshot.is_gpt and not snapshot.has_bios_boot_partition(BIOS_BOOT_GUID)
        else MIN_KYTHOS_BYTES
    )
    if shrink_bytes < required:
        raise RuntimeError(
            f"This layout needs at least {MIN_KYTHOS_GIB + 1} GiB of shrink space "
            "to create KythOS and its boot partition."
        )
    current_size = _safe_int(part.get("size_bytes")) or dependencies.partition_size(partition)
    if current_size - shrink_bytes < 64 * 1024**3:
        raise RuntimeError("Refusing to leave the NTFS partition smaller than 64 GiB.")
    return disk, partition, shrink_bytes


def validate_free_space_target(
    config: dict,
    snapshot: StorageSnapshot | None = None,
    *,
    dependencies: GuidedValidationDependencies,
) -> tuple[str, int, int]:
    """Validate that a selected free region remains safe and available."""
    disk = _normal_device_path(config.get("disk"))
    start = _safe_int(config.get("free_region_start"), -1)
    end = _safe_int(config.get("free_region_end"), -1)
    if not disk:
        raise RuntimeError("No target disk was selected.")
    if start < 0 or end <= start:
        raise RuntimeError("No free space region was selected for installation.")
    if end - start < MIN_KYTHOS_BYTES:
        raise RuntimeError(
            f"Free space install requires at least {MIN_KYTHOS_GIB} GiB for KythOS."
        )
    snapshot = snapshot or dependencies.probe_storage(disk, include_free_space=True)
    if disk not in snapshot.disks_by_name:
        raise RuntimeError("The selected disk is not a safe install target.")
    required = (
        MIN_KYTHOS_BYTES + BIOS_BOOT_BYTES
        if snapshot.is_gpt and not snapshot.has_bios_boot_partition(BIOS_BOOT_GUID)
        else MIN_KYTHOS_BYTES
    )
    if end - start < required:
        raise RuntimeError(
            f"This layout needs at least {MIN_KYTHOS_GIB + 1} GiB of free space "
            "to create KythOS and its boot partition."
        )
    if not snapshot.efi_partition:
        raise RuntimeError("Free space installation requires an EFI system partition on the system.")
    if not snapshot.contains_free_region(start, end):
        raise RuntimeError(
            "The selected free space is no longer available. Re-scan the disk and try again."
        )
    return disk, start, end


def build_plan_report(
    state,
    context=None,
    *,
    snapshot: StorageSnapshot | None = None,
    dependencies: ReportDependencies,
) -> PlanReport:
    """Build the complete read-only plan report for every installation mode."""
    request = dependencies.as_request(state)
    mode = dependencies.normalized_mode(request)
    disk = _normal_device_path(request.disk)
    errors: list[str] = []
    warnings: list[str] = []
    efi = ""
    target = ""
    required = MIN_KYTHOS_BYTES
    available = 0
    is_gpt = False
    needs_bios = False
    will_create = mode in ("resize_ntfs", "free_space")
    will_shrink = mode == "resize_ntfs"

    def report(valid: bool) -> PlanReport:
        return PlanReport(
            valid=valid, mode=mode, disk=disk, target_partition=target,
            efi_partition=efi, will_create_partition=will_create,
            will_shrink_filesystem=will_shrink, required_bytes=required,
            available_bytes=available, is_gpt=is_gpt,
            needs_bios_boot=needs_bios, errors=tuple(errors),
            warnings=tuple(warnings),
        )

    try:
        if mode == "resize_ntfs":
            disk, target, required = dependencies.validate_resize(
                state, snapshot=snapshot,
            )
            snapshot = snapshot or dependencies.probe_storage(disk)
            efi = snapshot.efi_partition or ""
            is_gpt = snapshot.is_gpt
            needs_bios = is_gpt and not snapshot.has_bios_boot_partition(BIOS_BOOT_GUID)
            available = required
        elif mode == "free_space":
            disk, start, end = dependencies.validate_free_space(
                state, snapshot=snapshot,
            )
            available = end - start
            snapshot = snapshot or dependencies.probe_storage(
                disk, include_free_space=True,
            )
            efi = snapshot.efi_partition or ""
            is_gpt = snapshot.is_gpt
            needs_bios = is_gpt and not snapshot.has_bios_boot_partition(BIOS_BOOT_GUID)
            required = MIN_KYTHOS_BYTES + (BIOS_BOOT_BYTES if needs_bios else 0)
        else:
            effective = snapshot or dependencies.probe_storage(
                disk, include_partitions=mode != "wipe",
            )
            is_gpt = effective.is_gpt
            needs_bios = (
                is_gpt and not effective.has_bios_boot_partition(BIOS_BOOT_GUID)
                if mode == "alongside" else False
            )
            disk, resolved = dependencies.validate_install(
                request.as_state(), context, snapshot=effective,
            )
            target = resolved or ""
            efi = effective.efi_partition or ""
            if mode == "wipe":
                available = _safe_int(
                    effective.disks_by_name.get(disk, {}).get("size_bytes")
                )
            elif target:
                available = _safe_int(
                    effective.partitions_by_name.get(target, {}).get("size_bytes")
                )
    except RuntimeError as exc:
        errors.append(str(exc))
        return report(False)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
        errors.append(f"Unexpected validation error: {exc}")
        return report(False)

    if needs_bios and mode in ("resize_ntfs", "free_space"):
        warnings.append(
            "A 1 MiB BIOS boot partition will be created for GRUB on this GPT disk."
        )
    if needs_bios and mode == "alongside":
        errors.append(
            "Legacy BIOS on GPT requires a 1 MiB BIOS boot partition for GRUB. "
            "Create a 1 MiB partition with the bios_grub flag in the manual "
            "partition editor, or use free-space/NTFS-shrink install which "
            "creates it automatically. Without it GRUB falls back to "
            "blocklists, which Btrfs rejects."
        )
        return report(False)
    return report(True)
