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
import subprocess  # noqa: F401  # pylint: disable=unused-import  # compatibility surface for storage tests/callers
from typing import Callable

from .config import BIOS_BOOT_BYTES, BIOS_BOOT_GUID, MIN_KYTHOS_GIB, MIN_KYTHOS_BYTES  # pylint: disable=unused-import
from .context import InstallationState, InstallRequest  # pylint: disable=unused-import
from .plan_types import InstallPlan, PlanReport, ResolvedInstallPlan  # pylint: disable=unused-import
from .plan_request import (
    as_request as _request_as_request,
    install_plan_from_state as _request_install_plan_from_state,
    normalized_install_mode as _request_normalized_install_mode,
    request_with_install_plan as _request_with_install_plan,
)
from .disk import (  # pylint: disable=unused-import
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

_as_request = _request_as_request
_normalized_install_mode = _request_normalized_install_mode
_install_plan_from_state = _request_install_plan_from_state
request_with_install_plan = _request_with_install_plan

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
    GuidedValidationDependencies,
    ReportDependencies,
    ValidationDependencies,
    build_plan_report as _pv_build_plan_report,
    _validate_efi_target as _pv_validate_efi_target,
    _validate_install_target as _pv_validate_install_target,
    _validate_partition_target as _pv_validate_partition_target,
    validate_free_space_target as _pv_validate_free_space_target,
    validate_resize_ntfs_target as _pv_validate_resize_ntfs_target,
    validate_storage_intent as _pv_validate_storage_intent,
)

def _validate_install_target(*args, **kwargs):
    kwargs.setdefault("dependencies", ValidationDependencies(
        parent_disk=_parent_disk, list_partitions=list_partitions,
        probe_storage=_probe_storage, get_journal=partition_ops.get_journal,
    ))
    return _pv_validate_install_target(*args, **kwargs)

def _validate_efi_target(*args, **kwargs):
    kwargs.setdefault("dependencies", ValidationDependencies(
        parent_disk=_parent_disk, list_partitions=list_partitions,
        probe_storage=_probe_storage, get_journal=partition_ops.get_journal,
    ))
    return _pv_validate_efi_target(*args, **kwargs)

def _validate_partition_target(*args, **kwargs):
    kwargs.setdefault("dependencies", ValidationDependencies(
        parent_disk=_parent_disk, list_partitions=list_partitions,
        probe_storage=_probe_storage, get_journal=partition_ops.get_journal,
    ))
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
    return _pv_validate_resize_ntfs_target(
        config,
        snapshot=snapshot,
        dependencies=GuidedValidationDependencies(
            probe_storage=_probe_storage, parent_disk=_parent_disk,
            partition_size=_partition_size_bytes,
        ),
    )


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
    _plan_commit.shrink_ntfs_filesystem_guarded(
        partition, new_ntfs_size, shrink_bytes, log,
        shrink_filesystem=shrink_filesystem, human_size=_human_size,
    )


def _prepare_ntfs_resize_target(config: dict, log) -> tuple[str, str]:
    return _plan_commit.prepare_ntfs_resize_target(
        config, log,
        normal_device_path=_normal_device_path,
        validate_target=_validate_resize_ntfs_target,
        required_tools=(
            "ntfsresize", "parted", "partprobe", "udevadm", "mkfs.btrfs", "sgdisk",
        ),
        which=shutil.which,
        unmount_target_disk=unmount_target_disk,
        partition_size=_partition_size_bytes,
        partition_number=_partition_number,
        block_size=_block_size_bytes,
        partition_start=_partition_start_bytes,
        shrink_filesystem_guarded=_shrink_ntfs_filesystem_guarded,
        run_command=run_command,
        as_root=_as_root,
        settle=_settle,
        commit_partition=_commit_new_kythos_partition,
    )

def _validate_free_space_target(
    config: dict,
    snapshot: StorageSnapshot | None = None,
) -> tuple[str, int, int]:
    return _pv_validate_free_space_target(
        config,
        snapshot=snapshot,
        dependencies=GuidedValidationDependencies(
            probe_storage=_probe_storage, parent_disk=_parent_disk,
            partition_size=_partition_size_bytes,
        ),
    )


def _prepare_free_space_target(config: dict, log) -> tuple[str, str]:
    return _plan_commit.prepare_free_space_target(
        config, log, validate_target=_validate_free_space_target,
        required_tools=("parted", "partprobe", "udevadm", "mkfs.btrfs", "sgdisk"),
        which=shutil.which, unmount_target_disk=unmount_target_disk,
        commit_partition=_commit_new_kythos_partition,
    )

def _prepare_ntfs_install_plan(state: dict | InstallRequest, log) -> InstallPlan:
    return _plan_commit.prepare_guided_install_plan(
        state, log, validate_target=_validate_resize_ntfs_target,
        prepare_target=_prepare_ntfs_resize_target,
    )

def _prepare_free_space_install_plan(state: dict | InstallRequest, log) -> InstallPlan:
    return _plan_commit.prepare_guided_install_plan(
        state, log, validate_target=_validate_free_space_target,
        prepare_target=_prepare_free_space_target,
    )

def _prepare_explicit_install_plan(
    plan: InstallPlan,
    state: dict | InstallRequest,
    context=None,
) -> InstallPlan:
    return _plan_commit.prepare_explicit_install_plan(
        plan, state, context, validate_target=_validate_install_target,
    )

def validate_plan_state(
    state: "InstallationState | InstallRequest",
    context=None,
    *,
    snapshot: StorageSnapshot | None = None,
) -> PlanReport:
    """Return the canonical read-only report through the compatibility facade."""
    return _pv_build_plan_report(
        state, context, snapshot=snapshot, dependencies=ReportDependencies(
            as_request=_as_request, normalized_mode=_normalized_install_mode,
            probe_storage=_probe_storage, validate_install=_validate_install_target,
            validate_resize=_validate_resize_ntfs_target,
            validate_free_space=_validate_free_space_target,
        ),
    )


def _prepare_install_plan(state: dict | InstallRequest, log, context=None) -> InstallPlan:
    # Explicit validate→commit: fail fast with a structured report before any
    # partition-table backup, ntfsresize, or mkfs is attempted. Mirrors the
    # UI's dry-run validation so the same message is shown in both places.
    return _plan_commit.prepare_install_plan(
        state, log, context,
        validate_report=validate_plan_state,
        plan_from_state=_install_plan_from_state,
        prepare_ntfs=_prepare_ntfs_install_plan,
        prepare_free_space=_prepare_free_space_install_plan,
        prepare_explicit=_prepare_explicit_install_plan,
    )

def _get_manual_mounts(context) -> list[dict]:
    """Return non-root partition mount assignments from the committed journal."""
    return _plan_query.get_manual_mounts(
        context, get_journal=partition_ops.get_journal, list_partitions=list_partitions,
    )

def _validate_storage_intent(state: dict, context=None, snapshot=None) -> None:
    """Validate a review-page storage choice without changing the machine."""
    _pv_validate_storage_intent(
        state, context, snapshot, normalized_mode=_normalized_install_mode,
        validate_install=_validate_install_target,
        validate_resize=_validate_resize_ntfs_target,
        validate_free_space=_validate_free_space_target,
    )
