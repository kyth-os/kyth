"""Install-plan data types and the target-validation + destructive
free-space/NTFS-shrink partition preparation orchestration.

The HTTP route table lives in server.py, the module that actually uses it —
not here.

install_mode invariants:
  "wipe"        — bootc install to-disk. Requires disk in list_disks() (safe-scan
                  passed). Refused against the running system's disk unless
                  _IS_LIVE_SESSION (booting the live ISO), since to-disk wipes
                  whatever partition table is there, live root included.
  "alongside"   — bootc install to-filesystem against an existing empty(-ish)
                  Btrfs partition (list_partitions() alongside_candidate). Needs
                  --acknowledge-destructive alongside --skip-fetch-check because
                  the target mountpoint already has other partitions (e.g. a
                  populated /boot/efi) mounted under it; the partition CLI uses
                  this same code path. Verified in a
                  container repro (loop-mounted GPT disk, foreign-OS ESP content,
                  real bootc) that this flag does not change behavior on a clean
                  target — it exists for parity with the shell fallback, not
                  because it gates a real rejection in current bootc.
  "resize_ntfs" — _validate_resize_ntfs_target() shrinks an NTFS partition,
                  then _prepare_ntfs_resize_target()
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

import logging
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import BIOS_BOOT_BYTES, BIOS_BOOT_GUID, MIN_KYTHOS_GIB, MIN_KYTHOS_BYTES
from .context import InstallRequest
from .disk import (
    _human_size,
    _latest_partition_on_disk,
    _normal_device_path,
    _parent_disk,
    _partition_number,
    _partition_size_bytes,
    _partition_start_bytes,
    _block_size_bytes,
    _safe_int,
    find_efi_partition,
    list_disks,
    list_free_space,
    list_partitions,
)
from . import partition_ops
from .fsresize import shrink_filesystem
from .services.disk_service import DiskService
from .system import _as_root, _settle, unmount_target_disk
from .runner import run_command
from .storage_snapshot import StorageSnapshot

_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InstallPlan:
    mode: str
    disk: Optional[str] = None
    target_partition: Optional[str] = None


@dataclass(frozen=True)
class ResolvedInstallPlan:
    """Complete immutable input consumed by destructive install phases."""

    request: InstallRequest
    storage: InstallPlan
    source_ref: str
    target_ref: str
    source_digest: str = ""
    source_kind: str = "network"
    source_verified: bool = False

    @property
    def mode(self) -> str:
        return self.storage.mode

    @property
    def disk(self) -> str:
        if not self.storage.disk:
            raise RuntimeError("Resolved install plan has no target disk")
        return self.storage.disk

    @property
    def target_partition(self) -> str:
        return self.storage.target_partition or ""

    @property
    def efi_partition(self) -> str:
        return self.request.efi_partition

    @property
    def kernel(self) -> str:
        return self.request.kernel


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


def _probe_storage(
    disk: str,
    *,
    include_partitions: bool = True,
    include_free_space: bool = False,
) -> StorageSnapshot:
    """Capture all live discovery needed for one planning decision."""
    return StorageSnapshot(
        disks=tuple(list_disks()),
        partitions=tuple(list_partitions(disk)) if include_partitions else (),
        free_regions=tuple(list_free_space(disk)) if include_free_space else (),
        efi_partition=find_efi_partition(disk) if include_partitions else None,
        is_gpt=_is_gpt_disk(disk) if include_partitions else False,
    )


def _validate_partition_target(
    disk: str,
    target: str,
    label: str,
    snapshot: StorageSnapshot | None = None,
) -> dict:
    """Validate `target` is a real, unmounted, adequately-sized, non-EFI
    partition on `disk`, using `list_partitions()`'s post-scan state.
    `label` (e.g. "target partition", "root partition") is substituted into
    the error messages. Returns the matching partition dict on success."""
    partitions = (
        snapshot.partitions_by_name
        if snapshot is not None
        else {p["name"]: p for p in list_partitions(disk)}
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
    """Revalidate the exact ESP that the install will mount.

    Discovery may legitimately select an ESP on another internal disk, so the
    selected-disk snapshot alone is insufficient. Re-scan the ESP's own parent
    disk and fail closed if the request names a stale, read-only, non-ESP, or
    root-target partition.
    """
    requested = _normal_device_path(config.get("efi_partition"))
    efi = requested or _normal_device_path(discovered)
    if not efi:
        raise RuntimeError("Alongside installation requires an EFI system partition on the system.")
    if efi == target:
        raise RuntimeError("The EFI system partition and KythOS target partition must be different.")
    # A discovery-produced value came from find_efi_partition() during this
    # same snapshot and has already been checked as an ESP. An explicitly
    # supplied/state-carried value crosses a request or phase boundary and
    # must be re-read from the live device graph below.
    if not requested:
        return efi
    efi_disk = _parent_disk(efi)
    if not efi_disk:
        raise RuntimeError("Could not determine which disk contains the EFI system partition.")
    efi_info = next((part for part in list_partitions(efi_disk) if part.get("name") == efi), None)
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
        if _parent_disk(target) != disk:
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
        if _parent_disk(target) != disk:
            raise RuntimeError("The root partition does not belong to the selected disk.")
        # Re-validate the resolved root partition against the post-commit disk
        # state, same as the "alongside" branch above. journal.root_partition
        # is derived from a set-mountpoint op and is not necessarily the same
        # partition a create/format op in the journal actually touched, so it
        # could point at a pre-existing, still-mounted/in-use partition on the
        # same disk — never trust it without re-checking here.
        _validate_partition_target(disk, target, "root partition", snapshot)
        _validate_efi_target(config, target, snapshot.efi_partition)
        return disk, target

    raise RuntimeError(f"Unsupported install mode: {mode}")


def _is_gpt_disk(disk: str) -> bool:
    try:
        result = run_command(
            ["blkid", "-o", "value", "-s", "PTTYPE", disk],
            capture_output=True, text=True, check=True, timeout=5,
        )
        out = result.stdout
        if out.strip().lower() == "gpt":
            return True
    except Exception:
        _logger.debug("_is_gpt_disk: blkid probe of %s failed", disk, exc_info=True)
    try:
        result = run_command(
            ["parted", "-s", disk, "print"],
            capture_output=True, text=True, check=True, timeout=5,
        )
        out = result.stdout
        return "Partition Table: gpt" in out
    except Exception:
        return False


def _has_bios_boot_partition(disk: str) -> bool:
    return any(
        (part.get("parttype") or "").lower() == BIOS_BOOT_GUID
        for part in list_partitions(disk)
    )


def _required_guided_space(disk: str) -> int:
    if _is_gpt_disk(disk) and not _has_bios_boot_partition(disk):
        return MIN_KYTHOS_BYTES + BIOS_BOOT_BYTES
    return MIN_KYTHOS_BYTES


def _ensure_bios_boot_partition(disk: str, gap_start: int, log) -> int:
    """Create a 1 MiB bios_grub partition at gap_start if the GPT disk lacks
    one, returning the byte offset where the KythOS partition should begin.

    The OS image ships a bootupd BIOS (i386-pc GRUB) component, and bootc's
    bootloader step installs every shipped component. Without a bios_grub
    partition grub2-install falls back to blocklists, which Btrfs rejects —
    "filesystem 'btrfs' doesn't support blocklists" — failing the whole
    install. bootc install to-disk creates this partition itself; the
    alongside paths partition the disk manually, so they must match.
    """
    if not _is_gpt_disk(disk):
        return gap_start
    if _has_bios_boot_partition(disk):
        return gap_start
    before = {p["name"] for p in list_partitions(disk) if p.get("name")}
    sector = _block_size_bytes(disk)
    bios_end = gap_start + BIOS_BOOT_BYTES - sector
    log("Creating BIOS boot partition for GRUB...")
    run_command(_as_root(["parted", "-s", disk, "unit", "B", "mkpart", "biosboot", f"{gap_start}B", f"{bios_end}B"]), check=True, timeout=120)
    _settle()
    created = _latest_partition_on_disk(disk, before)
    if not created:
        raise RuntimeError("The installer could not find the new BIOS boot partition after partitioning.")
    run_command(_as_root(["parted", "-s", disk, "set", str(_partition_number(created)), "bios_grub", "on"]), check=True, timeout=120)
    _settle()
    return bios_end + sector


def _commit_new_kythos_partition(
    disk: str,
    gap_start: int,
    gap_end: int,
    log,
    *,
    before_partition: Callable[[], None] | None = None,
    failure_message: str = "A step failed — restoring the original partition table...",
    restored_message: str = "Partition table restored to its state before this attempt.",
) -> str:
    """Back up `disk`'s partition table, then create a new KythOS Btrfs
    partition spanning [gap_start, gap_end), restoring the backup if
    anything in this scope raises. `before_partition`, if given, runs first
    inside the same backed-up/restored scope (e.g. the NTFS boundary-shrink
    resizepart call) so its failures are covered by the same safety net.
    Returns the new partition's device path."""
    disk_service = DiskService()
    with tempfile.TemporaryDirectory(prefix="kyth-partition-") as backup_dir:
        backup_path = str(Path(backup_dir) / "partition-table.backup")
        log("Backing up the partition table before changing it...")
        disk_service.backup_table(disk, backup_path)
        try:
            if before_partition is not None:
                before_partition()

            btrfs_start = _ensure_bios_boot_partition(disk, gap_start, log)
            sector = _block_size_bytes(disk)
            partition_end = gap_end - sector
            before = {p["name"] for p in list_partitions(disk) if p.get("name")}

            log(f"Creating KythOS Btrfs partition in {_human_size(gap_end - btrfs_start)} of free space...")
            run_command(_as_root(["parted", "-s", disk, "unit", "B", "mkpart", "KythOS", "btrfs", f"{btrfs_start}B", f"{partition_end}B"]), check=True, timeout=120)
            _settle()

            created = _latest_partition_on_disk(disk, before)
            if not created:
                raise RuntimeError("The installer could not find the new KythOS partition after partitioning.")
            run_command(_as_root(["mkfs.btrfs", "-f", "-L", "KythOS", created]), check=True, timeout=300)
            log(f"Created target partition {created}")
        except Exception:
            log(failure_message)
            try:
                disk_service.restore_table(disk, backup_path)
                log(restored_message)
            except Exception as restore_exc:
                log(f"Warning: automatic partition table restore failed: {restore_exc}")
            raise
    return created


def _validate_resize_ntfs_target(
    config: dict,
    snapshot: StorageSnapshot | None = None,
) -> tuple[str, str, int]:
    disk = _normal_device_path(config.get("disk"))
    partition = _normal_device_path(config.get("resize_partition") or config.get("target_partition"))
    shrink_gib = _safe_int(config.get("resize_gib") or config.get("shrink_gib") or 0)

    if not disk:
        raise RuntimeError("No target disk was selected.")
    if not partition:
        raise RuntimeError("No NTFS partition was selected to shrink.")
    if shrink_gib < MIN_KYTHOS_GIB:
        raise RuntimeError(f"NTFS shrink install requires at least {MIN_KYTHOS_GIB} GiB for KythOS.")

    snapshot = snapshot or _probe_storage(disk)
    safe_disks = snapshot.disks_by_name
    if disk not in safe_disks:
        raise RuntimeError("The selected disk is not a safe install target.")
    if _parent_disk(partition) != disk:
        raise RuntimeError("The selected NTFS partition does not belong to the selected disk.")
    parts = snapshot.partitions_by_name
    part = parts.get(partition)
    if not part:
        raise RuntimeError("The selected NTFS partition was not found during the final disk scan.")
    if part.get("efi") or part.get("current") or part.get("in_use") or part.get("read_only"):
        raise RuntimeError("The selected partition is mounted, read-only, or reserved and cannot be resized.")
    part_fstype = (part.get("fstype") or "").lower()
    if part_fstype == "bitlocker":
        raise RuntimeError(
            "This partition is BitLocker-encrypted and cannot be resized while "
            "locked. In Windows, suspend or disable BitLocker protection "
            "(Control Panel > BitLocker Drive Encryption, or 'manage-bde -off "
            "C:'), wait for decryption to finish, then try again."
        )
    if part_fstype not in ("ntfs", "ntfs3"):
        raise RuntimeError("Only NTFS partitions can be resized by this installer path.")
    if not snapshot.efi_partition:
        raise RuntimeError("NTFS resize installation requires an EFI system partition on the system.")

    shrink_bytes = shrink_gib * 1024**3
    required_space = (
        MIN_KYTHOS_BYTES + BIOS_BOOT_BYTES
        if snapshot.is_gpt and not snapshot.has_bios_boot_partition(BIOS_BOOT_GUID)
        else MIN_KYTHOS_BYTES
    )
    if shrink_bytes < required_space:
        raise RuntimeError(
            f"This layout needs at least {MIN_KYTHOS_GIB + 1} GiB of shrink space "
            "to create KythOS and its boot partition."
        )
    current_size = _safe_int(part.get("size_bytes")) or _partition_size_bytes(partition)
    remaining_size = current_size - shrink_bytes
    if remaining_size < 64 * 1024**3:
        raise RuntimeError("Refusing to leave the NTFS partition smaller than 64 GiB.")
    return disk, partition, shrink_bytes


def _prepare_ntfs_resize_target(config: dict, log) -> tuple[str, str]:
    disk, partition, shrink_bytes = _validate_resize_ntfs_target(config)
    missing = [cmd for cmd in ("ntfsresize", "parted", "partprobe", "udevadm", "mkfs.btrfs", "sgdisk") if shutil.which(cmd) is None]
    if missing:
        raise RuntimeError(f"Required NTFS resize tools are missing from the live environment: {', '.join(missing)}")
    unmount_target_disk(disk, log)
    disk, partition, shrink_bytes = _validate_resize_ntfs_target(config)
    current_size = _partition_size_bytes(partition)
    new_ntfs_size = current_size - shrink_bytes
    part_num = _partition_number(partition)
    sector = _block_size_bytes(disk)
    partition_start = _partition_start_bytes(partition)
    old_end = partition_start + current_size - sector
    new_end = partition_start + new_ntfs_size - sector

    log(f"NTFS resize requested: shrink {partition} by {_human_size(shrink_bytes)}")
    shrink_filesystem(partition, "ntfs", new_ntfs_size, log)

    def _shrink_partition_boundary() -> None:
        log("Shrinking partition boundary...")
        # parted >= 3.3 refuses to shrink a partition in script mode (-s):
        # it asks "Shrinking a partition can cause data loss, are you
        # sure?" and exits 1 when it cannot prompt. ---pretend-input-tty
        # with "Yes" piped on stdin is the documented way to answer that
        # prompt non-interactively.
        run_command(
            _as_root(["parted", "---pretend-input-tty", disk, "unit", "B", "resizepart", str(part_num), f"{new_end}B"]),
            input="Yes\n", text=True, stdout=subprocess.DEVNULL, check=True, timeout=120,
        )
        _settle()
        actual_size = _partition_size_bytes(partition)
        if abs(actual_size - new_ntfs_size) > sector:
            raise RuntimeError(
                "The partition tool did not produce the requested NTFS boundary. "
                "No KythOS partition was created; the original partition table will be restored."
            )

    # The NTFS filesystem was already shrunk above (that step cannot be
    # undone by a table restore, and doesn't need to be — a partition table
    # describing more space than the filesystem inside it uses is a benign,
    # expected intermediate state, not corruption). Restoring the table just
    # undoes the boundary move / new-partition creation that failed here.
    created = _commit_new_kythos_partition(
        disk, new_end + sector, old_end + sector, log,
        before_partition=_shrink_partition_boundary,
        failure_message="A step after the NTFS shrink failed — restoring the original partition table...",
        restored_message=(
            "Partition table restored. The NTFS filesystem itself was "
            "already shrunk and remains intact and usable — Windows may "
            "offer to grow it back to fill the partition, or you can "
            "leave it as-is and try the install again."
        ),
    )
    return disk, created


def _validate_free_space_target(
    config: dict,
    snapshot: StorageSnapshot | None = None,
) -> tuple[str, int, int]:
    disk = _normal_device_path(config.get("disk"))
    start = _safe_int(config.get("free_region_start"), -1)
    end = _safe_int(config.get("free_region_end"), -1)

    if not disk:
        raise RuntimeError("No target disk was selected.")
    if start < 0 or end <= start:
        raise RuntimeError("No free space region was selected for installation.")
    if end - start < MIN_KYTHOS_BYTES:
        raise RuntimeError(f"Free space install requires at least {MIN_KYTHOS_GIB} GiB for KythOS.")

    snapshot = snapshot or _probe_storage(disk, include_free_space=True)
    safe_disks = snapshot.disks_by_name
    if disk not in safe_disks:
        raise RuntimeError("The selected disk is not a safe install target.")
    required_space = (
        MIN_KYTHOS_BYTES + BIOS_BOOT_BYTES
        if snapshot.is_gpt and not snapshot.has_bios_boot_partition(BIOS_BOOT_GUID)
        else MIN_KYTHOS_BYTES
    )
    if end - start < required_space:
        raise RuntimeError(
            f"This layout needs at least {MIN_KYTHOS_GIB + 1} GiB of free space "
            "to create KythOS and its boot partition."
        )
    if not snapshot.efi_partition:
        raise RuntimeError("Free space installation requires an EFI system partition on the system.")

    # Re-scan right before committing so a stale UI selection can't partition
    # space that's no longer actually free.
    if not snapshot.contains_free_region(start, end):
        raise RuntimeError("The selected free space is no longer available. Re-scan the disk and try again.")

    return disk, start, end


def _prepare_free_space_target(config: dict, log) -> tuple[str, str]:
    disk, start, end = _validate_free_space_target(config)
    missing = [cmd for cmd in ("parted", "partprobe", "udevadm", "mkfs.btrfs", "sgdisk") if shutil.which(cmd) is None]
    if missing:
        raise RuntimeError(f"Required partitioning tools are missing from the live environment: {', '.join(missing)}")
    unmount_target_disk(disk, log)
    disk, start, end = _validate_free_space_target(config)

    created = _commit_new_kythos_partition(disk, start, end, log)
    return disk, created


def _prepare_ntfs_install_plan(state: dict | InstallRequest, log) -> InstallPlan:
    _validate_resize_ntfs_target(state)
    disk, target_partition = _prepare_ntfs_resize_target(state, log)
    return InstallPlan("alongside", disk=disk, target_partition=target_partition)


def _prepare_free_space_install_plan(state: dict | InstallRequest, log) -> InstallPlan:
    _validate_free_space_target(state)
    disk, target_partition = _prepare_free_space_target(state, log)
    return InstallPlan("alongside", disk=disk, target_partition=target_partition)


def _prepare_explicit_install_plan(
    plan: InstallPlan,
    state: dict | InstallRequest,
    context=None,
) -> InstallPlan:
    disk, target_partition = _validate_install_target(state, context)
    return InstallPlan(plan.mode, disk=disk, target_partition=target_partition)


def _prepare_install_plan(state: dict | InstallRequest, log, context=None) -> InstallPlan:
    plan = _install_plan_from_state(state)
    if plan.mode == "resize_ntfs":
        return _prepare_ntfs_install_plan(state, log)
    if plan.mode == "free_space":
        return _prepare_free_space_install_plan(state, log)
    return _prepare_explicit_install_plan(plan, state, context)


def _get_manual_mounts(context) -> list[dict]:
    """Return non-root partition mount assignments from the committed journal."""
    journal = partition_ops.get_journal(context)
    if not journal or not journal.committed:
        return []
    mounts: list[dict] = []
    for op in journal.ops:
        if op["kind"] in ("create", "set_mountpoint"):
            mountpoint = op["params"].get("mountpoint", "").strip()
            partition = op["params"].get("partition", "")
            if mountpoint and mountpoint not in ("/", "/boot/efi") and partition:
                fs_type = op["params"].get("fs_type", "") if op["kind"] == "create" else ""
                for fmt_op in journal.ops:
                    if (fmt_op["kind"] == "format" and
                        fmt_op["params"].get("partition") == partition):
                        fs_type = fmt_op["params"].get("fs_type", "")
                        break
                if not fs_type:
                    parts = list_partitions(journal.disk)
                    for p in parts:
                        if p.get("name") == partition:
                            fs_type = p.get("fstype", "")
                            break
                mounts.append({
                    "partition": partition,
                    "mountpoint": mountpoint,
                    "fstype": fs_type or "btrfs",
                })
    return mounts


def _validate_storage_intent(state: dict, context=None) -> None:
    """Validate a review-page storage choice without changing the machine."""
    mode = _normalized_install_mode(state)
    if mode == "resize_ntfs":
        _validate_resize_ntfs_target(state)
    elif mode == "free_space":
        _validate_free_space_target(state)
    elif mode == "manual":
        _validate_install_target(state, context)
    else:
        _validate_install_target(state, context)
