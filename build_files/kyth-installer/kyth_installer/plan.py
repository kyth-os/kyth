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

import shutil
import subprocess
from pathlib import Path
from typing import Callable

from .config import BIOS_BOOT_BYTES, BIOS_BOOT_GUID, MIN_KYTHOS_GIB, MIN_KYTHOS_BYTES
from .context import InstallationState, InstallRequest  # pylint: disable=unused-import
from .plan_types import InstallPlan, PlanReport, ResolvedInstallPlan  # pylint: disable=unused-import
from .plan_request import (
    as_request as _request_as_request,
    install_plan_from_state as _request_install_plan_from_state,
    normalized_install_mode as _request_normalized_install_mode,
    request_with_install_plan as _request_with_install_plan,
)
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

from . import plan_query as _plan_query
from . import plan_commit as _plan_commit


def _commit_dependencies() -> _plan_commit.CommitDependencies:
    """Bind destructive planning to this module's patchable compatibility surface."""
    from .storage_guard import PartitionTableGuard

    return _plan_commit.CommitDependencies(
        is_gpt=_is_gpt_disk,
        has_bios_boot=_has_bios_boot_partition,
        list_partitions=list_partitions,
        block_size=_block_size_bytes,
        latest_partition=_latest_partition_on_disk,
        partition_number=_partition_number,
        human_size=_human_size,
        run_command=run_command,
        as_root=_as_root,
        settle=_settle,
        disk_hold=disk_hold,
        guard_factory=PartitionTableGuard,
        disk_service_factory=DiskService,
    )

def _as_request(state: "InstallationState | InstallRequest") -> "InstallRequest":
    """Coerce InstallationState dict to InstallRequest — R-02 single-type boundary."""
    return _request_as_request(state)

def _normalized_install_mode(state: "InstallationState | InstallRequest") -> str:
    return _request_normalized_install_mode(state)

def _install_plan_from_state(state: "InstallationState | InstallRequest") -> InstallPlan:
    return _request_install_plan_from_state(state)

def request_with_install_plan(
    state: "InstallationState | InstallRequest",
    plan: InstallPlan,
) -> InstallRequest:
    """Return immutable request input updated with resolved storage fields."""
    return _request_with_install_plan(state, plan)

def _probe_storage(
    disk: str,
    *,
    include_partitions: bool = True,
    include_free_space: bool = False,
    disks: tuple | None = None,
) -> StorageSnapshot:
    """Capture all live discovery needed for one planning decision.

    `disks` lets a caller that already has a fresh list_disks() result (e.g.
    one iterating over every disk on the system) pass it straight through
    instead of this re-running the disk scan once per call."""
    return StorageSnapshot(
        disks=tuple(disks) if disks is not None else tuple(list_disks()),
        partitions=tuple(list_partitions(disk)) if include_partitions else (),
        free_regions=tuple(list_free_space(disk)) if include_free_space else (),
        efi_partition=find_efi_partition(disk) if include_partitions else None,
        is_gpt=_is_gpt_disk(disk) if include_partitions else False,
    )

from .plan_validate import (  # canonical (plan.py 788 → split)
    ValidationDependencies,
    _validate_efi_target as _pv_validate_efi_target,
    _validate_install_target as _pv_validate_install_target,
    _validate_partition_target as _pv_validate_partition_target,
)

def _validation_dependencies() -> ValidationDependencies:
    """Bind validation to this module's stable, patchable public boundary."""
    return ValidationDependencies(
        parent_disk=_parent_disk,
        list_partitions=list_partitions,
        probe_storage=_probe_storage,
        get_journal=partition_ops.get_journal,
    )

def _validate_install_target(*args, **kwargs):
    kwargs.setdefault("dependencies", _validation_dependencies())
    return _pv_validate_install_target(*args, **kwargs)

def _validate_efi_target(*args, **kwargs):
    kwargs.setdefault("dependencies", _validation_dependencies())
    return _pv_validate_efi_target(*args, **kwargs)

def _validate_partition_target(*args, **kwargs):
    kwargs.setdefault("dependencies", _validation_dependencies())
    return _pv_validate_partition_target(*args, **kwargs)

def _is_gpt_disk(disk: str) -> bool:
    return _plan_query.is_gpt_disk(disk, run_command=run_command)

def _has_bios_boot_partition(disk: str) -> bool:
    return _plan_query.has_bios_boot_partition(disk, list_partitions=list_partitions)

def suggest_windows_resize_target(snapshot=None) -> dict | None:
    """Best NTFS candidate for 'Keep Windows' one-click alongside.

    Scans safe disks for the largest NTFS partition with enough free
    headroom to shrink by MIN_KYTHOS_GIB+2 GiB (leaves Windows breathing
    room). Returns {disk, partition, size_gib, free_gib} or None — pure
    suggestion, validation still goes through _validate_resize_ntfs_target.
    """
    return _plan_query.suggest_windows_resize_target(
        list_disks=list_disks, probe_storage=_probe_storage, snapshot=snapshot,
    )

def disk_hold(disk: str, log):
    """Hold an exclusive open on the whole disk through partitioning.

    Prevents TOCTOU where a second installer request or udev automount
    reclaims a gap between validate_plan_state and parted mkpart. Best-effort
    on live ISO where the disk may be busy — falls back to advisory warning.

    Delegates to storage_guard.DiskLease so guided and manual paths share one
    flock primitive.
    """
    return _plan_query.disk_hold(disk, log)

def find_bootcurrent_esp() -> str | None:
    """Return ESP device path from BootCurrent via efibootmgr -v, or None."""
    return _plan_query.find_bootcurrent_esp(
        run_command=run_command, as_root=_as_root, which=shutil.which,
    )

def _required_guided_space(disk: str) -> int:
    return _plan_query.required_guided_space(
        disk, is_gpt=_is_gpt_disk, has_bios_boot=_has_bios_boot_partition,
    )

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
    return _plan_commit.ensure_bios_boot_partition(
        disk, gap_start, log, dependencies=_commit_dependencies(),
    )

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
    return _plan_commit.commit_new_kythos_partition(
        disk, gap_start, gap_end, log,
        dependencies=_commit_dependencies(),
        before_partition=before_partition,
        failure_message=failure_message,
        restored_message=restored_message,
    )

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

def _shrink_ntfs_filesystem_guarded(
    partition: str, new_ntfs_size: int, shrink_bytes: int, log
) -> None:
    """Shrink the NTFS filesystem in place, with explicit non-atomic warning.

    This step is **not** covered by the partition-table guard that follows.
    If the filesystem shrink succeeds but the later ``resizepart`` or KythOS
    partition creation fails, ``sgdisk --load-backup`` will restore the table
    but the filesystem stays shrunk. That leaves a partition larger than its
    filesystem — benign and recoverable (Windows Disk Management or
    ``ntfsresize`` can regrow), but not automatically rolled back. Log that
    explicitly so the failure path can surface accurate remediation and so
    tests can assert the boundary between the two durability domains.
    """
    log(f"NTFS resize requested: shrink {partition} by {_human_size(shrink_bytes)}")
    try:
        shrink_filesystem(partition, "ntfs", new_ntfs_size, log)
    except Exception:
        log(
            "NTFS filesystem shrink failed — no partition table change was made. "
            "The NTFS volume is unchanged and the installer made no destructive write."
        )
        raise
    log(
        "NTFS filesystem shrink complete. If the next partition step fails, "
        "the partition table will be restored but this filesystem will remain "
        "at its new smaller size. Windows will see unallocated space after it; "
        "use Windows Disk Management to extend the volume back if you want to undo."
    )
    # Marker to guard against immediate second shrink without regrow/reboot.
    # Filesystem shrink is not covered by the sgdisk guard, so a second attempt
    # in the same live session would shrink an already-small filesystem again.
    try:
        marker_dir = Path("/run/kyth-installer")
        marker_dir.mkdir(parents=True, exist_ok=True)
        safe_name = partition.replace("/", "_")
        marker = marker_dir / f"ntfs-shrunk-{safe_name}"
        marker.write_text(f"{new_ntfs_size}\n")
    except Exception:
        pass


def _prepare_ntfs_resize_target(config: dict, log) -> tuple[str, str]:
    # Guard against double-shrink in same session after a prior filesystem
    # shrink succeeded but table restore left FS small. Prevents second shrink
    # of an already-shrunk FS which would fail confusingly or over-shrink.
    try:
        prelim_partition = _normal_device_path(config.get("resize_partition") or config.get("target_partition"))
        if prelim_partition:
            safe_name = prelim_partition.replace("/", "_")
            marker = Path("/run/kyth-installer") / f"ntfs-shrunk-{safe_name}"
            if marker.is_file():
                raise RuntimeError(
                    "This NTFS partition was already shrunk in this installer session "
                    "but the partition table was restored after a later failure. "
                    "The filesystem is already at its new smaller size while the "
                    "partition still describes the old larger size. Reboot, let "
                    "Windows extend the volume back, or reboot the live ISO before "
                    "retrying. Marker: " + str(marker)
                )
    except RuntimeError:
        raise
    except Exception:
        pass
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

    _shrink_ntfs_filesystem_guarded(partition, new_ntfs_size, shrink_bytes, log)

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

def validate_plan_state(
    state: "InstallationState | InstallRequest",
    context=None,
    *,
    snapshot: StorageSnapshot | None = None,
) -> PlanReport:
    """Pure validation — no disk writes, no partition-table backup, no mkfs.

    Returns a structured :class:`PlanReport` that the API route can surface
    before the user confirms destructive work, and that the commit path re-runs
    as a guard before touching the disk. Keeping this separate from
    ``_prepare_*`` (which *does* mutate) makes the validate→commit boundary
    explicit and testable with plain ``StorageSnapshot`` fixtures.

    R-02: InstallationState is HTTP-only; destructive validation consumes
    InstallRequest via _as_request.
    """
    req = _as_request(state)
    mode = _normalized_install_mode(req)
    disk = _normal_device_path(req.disk)
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
    try:
        if mode == "resize_ntfs":
            d, p, shrink_bytes = _validate_resize_ntfs_target(state, snapshot=snapshot)  # type: ignore[arg-type]
            disk, target, required = d, p, shrink_bytes
            snapshot = snapshot or _probe_storage(disk)
            efi = snapshot.efi_partition or ""
            is_gpt = snapshot.is_gpt
            needs_bios = is_gpt and not snapshot.has_bios_boot_partition(BIOS_BOOT_GUID)
            available = shrink_bytes
        elif mode == "free_space":
            d, start, end = _validate_free_space_target(state, snapshot=snapshot)  # type: ignore[arg-type]
            disk, available = d, end - start
            snapshot = snapshot or _probe_storage(disk, include_free_space=True)
            efi = snapshot.efi_partition or ""
            is_gpt = snapshot.is_gpt
            needs_bios = is_gpt and not snapshot.has_bios_boot_partition(BIOS_BOOT_GUID)
            required = MIN_KYTHOS_BYTES + (BIOS_BOOT_BYTES if needs_bios else 0)
        else:
            raw = _as_request(state).as_state()
            eff_snapshot = snapshot or _probe_storage(disk, include_partitions=mode != "wipe")
            is_gpt = eff_snapshot.is_gpt
            needs_bios = is_gpt and not eff_snapshot.has_bios_boot_partition(BIOS_BOOT_GUID) if mode == "alongside" else False
            d, t = _validate_install_target(raw, context, snapshot=eff_snapshot)
            disk, target = d, t or ""
            efi = eff_snapshot.efi_partition or ""
            if mode == "wipe":
                info = eff_snapshot.disks_by_name.get(disk, {})
                available = _safe_int(info.get("size_bytes"))
                required = MIN_KYTHOS_BYTES
            elif target:
                part = eff_snapshot.partitions_by_name.get(target, {})
                available = _safe_int(part.get("size_bytes"))
                required = MIN_KYTHOS_BYTES
    except RuntimeError as exc:
        errors.append(str(exc))
        return PlanReport(valid=False, mode=mode, disk=disk, target_partition=target, efi_partition=efi,
                          will_create_partition=will_create, will_shrink_filesystem=will_shrink,
                          required_bytes=required, available_bytes=available, is_gpt=is_gpt,
                          needs_bios_boot=needs_bios, errors=tuple(errors), warnings=tuple(warnings))
    except Exception as exc:
        errors.append(f"Unexpected validation error: {exc}")
        return PlanReport(valid=False, mode=mode, disk=disk, target_partition=target, efi_partition=efi,
                          will_create_partition=will_create, will_shrink_filesystem=will_shrink,
                          required_bytes=required, available_bytes=available, is_gpt=is_gpt,
                          needs_bios_boot=needs_bios, errors=tuple(errors), warnings=tuple(warnings))

    if needs_bios and mode in ("resize_ntfs", "free_space"):
        warnings.append("A 1 MiB BIOS boot partition will be created for GRUB on this GPT disk.")
    if needs_bios and mode == "alongside":
        errors.append(
            "Legacy BIOS on GPT requires a 1 MiB BIOS boot partition for GRUB. "
            "Create a 1 MiB partition with the bios_grub flag in the manual "
            "partition editor, or use free-space/NTFS-shrink install which "
            "creates it automatically. Without it GRUB falls back to "
            "blocklists, which Btrfs rejects."
        )
        return PlanReport(valid=False, mode=mode, disk=disk, target_partition=target, efi_partition=efi,
                          will_create_partition=will_create, will_shrink_filesystem=will_shrink,
                          required_bytes=required, available_bytes=available, is_gpt=is_gpt,
                          needs_bios_boot=needs_bios, errors=tuple(errors), warnings=tuple(warnings))

    return PlanReport(valid=True, mode=mode, disk=disk, target_partition=target, efi_partition=efi,
                      will_create_partition=will_create, will_shrink_filesystem=will_shrink,
                      required_bytes=required, available_bytes=available, is_gpt=is_gpt,
                      needs_bios_boot=needs_bios, errors=(), warnings=tuple(warnings))

def _prepare_install_plan(state: dict | InstallRequest, log, context=None) -> InstallPlan:
    # Explicit validate→commit: fail fast with a structured report before any
    # partition-table backup, ntfsresize, or mkfs is attempted. Mirrors the
    # UI's dry-run validation so the same message is shown in both places.
    report = validate_plan_state(state, context)
    if not report.valid:
        raise RuntimeError(report.errors[0] if report.errors else "Install plan validation failed")
    plan = _install_plan_from_state(state)
    if plan.mode == "resize_ntfs":
        return _prepare_ntfs_install_plan(state, log)
    if plan.mode == "free_space":
        return _prepare_free_space_install_plan(state, log)
    return _prepare_explicit_install_plan(plan, state, context)

def _get_manual_mounts(context) -> list[dict]:
    """Return non-root partition mount assignments from the committed journal."""
    return _plan_query.get_manual_mounts(
        context, get_journal=partition_ops.get_journal, list_partitions=list_partitions,
    )

def _validate_storage_intent(state: dict, context=None, snapshot=None) -> None:
    """Validate a review-page storage choice without changing the machine."""
    mode = _normalized_install_mode(state)
    if mode == "resize_ntfs":
        _validate_resize_ntfs_target(state, snapshot=snapshot)
    elif mode == "free_space":
        _validate_free_space_target(state, snapshot=snapshot)
    elif mode == "manual":
        _validate_install_target(state, context, snapshot=snapshot)
    else:
        _validate_install_target(state, context, snapshot=snapshot)
