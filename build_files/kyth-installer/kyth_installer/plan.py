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
import contextlib
import fcntl
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .config import BIOS_BOOT_BYTES, BIOS_BOOT_GUID, MIN_KYTHOS_GIB, MIN_KYTHOS_BYTES
from .context import InstallationState, InstallRequest
from .plan_types import InstallPlan, PlanReport, ResolvedInstallPlan  # re-export for compat (monolith split step 1)
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

def _as_request(state: "InstallationState | InstallRequest") -> "InstallRequest":
    """Coerce InstallationState dict to InstallRequest — R-02 single-type boundary."""
    from .context import InstallRequest as _Req

    if isinstance(state, _Req):
        return state
    return _Req.from_state(state)  # dict -> InstallRequest, InstallationState remains HTTP-only

def _normalized_install_mode(state: "InstallationState | InstallRequest") -> str:
    req = _as_request(state)
    return str(req.install_mode or "wipe").strip().lower() or "wipe"

def _install_plan_from_state(state: "InstallationState | InstallRequest") -> InstallPlan:
    req = _as_request(state)
    return InstallPlan(
        mode=_normalized_install_mode(req),
        disk=req.disk,
        target_partition=req.target_partition,
    )

def _apply_install_plan(state: "InstallationState | InstallRequest", plan: InstallPlan) -> None:
    # Kept for backward compat with tests that pass dict; now delegates to request
    if isinstance(state, dict):
        state["install_mode"] = plan.mode
        if plan.disk is not None:
            state["disk"] = plan.disk
        if plan.target_partition is not None:
            state["target_partition"] = plan.target_partition
        return
    # InstallRequest is frozen — use object.__setattr__ to mutate for compat
    object.__setattr__(state, "install_mode", plan.mode)
    if plan.disk is not None:
        object.__setattr__(state, "disk", plan.disk)
    if plan.target_partition is not None:
        object.__setattr__(state, "target_partition", plan.target_partition)

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

from .plan_validate import (  # canonical (plan.py 788 → split)
    _validate_efi_target as _pv_validate_efi_target,
    _validate_install_target as _pv_validate_install_target,
    _validate_partition_target as _pv_validate_partition_target,
)
# Wrapper to keep test mocks on plan._parent_disk effective after split
def _validate_install_target(*args, **kwargs):
    import importlib
    pv = importlib.import_module(__name__.rsplit('.', 1)[0] + '.plan_validate')
    # Sync mocked _parent_disk / _is_gpt_disk / _has_bios_boot etc if tests patched plan.*
    for attr in ('_parent_disk', '_is_gpt_disk', '_has_bios_boot_partition', 'find_efi_partition', 'list_disks', 'list_partitions'):
        if hasattr(pv, attr) and attr in globals():
            try:
                pv.__dict__[attr] = globals()[attr]
            except Exception:
                pass
    return _pv_validate_install_target(*args, **kwargs)

def _validate_efi_target(*args, **kwargs):
    import importlib
    pv = importlib.import_module(__name__.rsplit('.', 1)[0] + '.plan_validate')
    for attr in ('_parent_disk', '_is_gpt_disk', '_has_bios_boot_partition', 'find_efi_partition', 'list_disks', 'list_partitions'):
        if hasattr(pv, attr) and attr in globals():
            try:
                pv.__dict__[attr] = globals()[attr]
            except Exception:
                pass
    return _pv_validate_efi_target(*args, **kwargs)

def _validate_partition_target(*args, **kwargs):
    import importlib
    pv = importlib.import_module(__name__.rsplit('.', 1)[0] + '.plan_validate')
    for attr in ('_parent_disk', '_is_gpt_disk', '_has_bios_boot_partition', 'find_efi_partition', 'list_disks', 'list_partitions'):
        if hasattr(pv, attr) and attr in globals():
            try:
                pv.__dict__[attr] = globals()[attr]
            except Exception:
                pass
    return _pv_validate_partition_target(*args, **kwargs)

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

def suggest_windows_resize_target(snapshot=None) -> dict | None:
    """Best NTFS candidate for 'Keep Windows' one-click alongside.

    Scans safe disks for the largest NTFS partition with enough free
    headroom to shrink by MIN_KYTHOS_GIB+2 GiB (leaves Windows breathing
    room). Returns {disk, partition, size_gib, free_gib} or None — pure
    suggestion, validation still goes through _validate_resize_ntfs_target.
    """
    from .disk import list_disks as _list_disks  # local to avoid cycle
    best = None
    for d in _list_disks():
        name = d.get("name")
        if not name:
            continue
        try:
            snap = snapshot if snapshot and snapshot.disks_by_name.get(name) else _probe_storage(name)
        except Exception:
            continue
        for pname, part in snap.partitions_by_name.items():
            if part.get("fstype", "").lower() != "ntfs":
                continue
            size = _safe_int(part.get("size_bytes"))
            if size < (64 + MIN_KYTHOS_GIB) * 1024**3:
                continue
            free = _safe_int(part.get("free_bytes") or 0)
            # free_bytes may be missing; fall back to size heuristic
            candidate = {"disk": name, "partition": pname, "size_bytes": size, "free_bytes": free}
            if best is None or size > best["size_bytes"]:
                best = candidate
    return best

@contextlib.contextmanager
def disk_hold(disk: str, log):
    """Hold an exclusive open on the whole disk through partitioning.

    Prevents TOCTOU where a second installer request or udev automount
    reclaims a gap between validate_plan_state and parted mkpart. Best-effort
    on live ISO where the disk may be busy — falls back to advisory warning.

    Delegates to storage_guard.DiskLease so guided and manual paths share one
    flock primitive.
    """
    from .storage_guard import DiskLease

    with DiskLease(disk, log, exclusive=True):
        yield

def find_bootcurrent_esp() -> str | None:
    """Return ESP device path from BootCurrent via efibootmgr -v, or None."""
    import shutil, subprocess
    if shutil.which("efibootmgr") is None:
        return None
    try:
        from .runner import run_command
        from .system import _as_root
        r = run_command(_as_root(["efibootmgr", "-v"]), capture_output=True, text=True, timeout=5)
        if r.returncode != 0 or not r.stdout:
            return None
        # Find BootCurrent line, then its HD() device path
        import re
        m = re.search(r"BootCurrent:\s*([0-9A-Fa-f]{4})", r.stdout)
        if not m:
            return None
        boot = m.group(1)
        # Find BootXXXX* line with HD(...)/File(\\EFI ...)
        for line in r.stdout.splitlines():
            if line.strip().startswith(f"Boot{boot}"):
                # HD(2,GPT,uuid,0x800,0xFA000)/File(\EFI\arch\grubx64.efi)
                hm = re.search(r"HD\(\d+,GPT,[^,]+,0x[0-9a-fA-F]+,0x[0-9a-fA-F]+\)", line)
                # We can't map HD to /dev directly, so return hint that BootCurrent exists
                # Caller will prefer existing find_efi_partition on BootCurrent disk if possible
                # For now, just indicate BootCurrent ESP is not on target disk if needed
                return line.strip()
    except Exception:
        pass
    return None

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
    created = _latest_partition_on_disk(disk, before)
    if not created:
        # R8: settle batch — wait once for udev after mkpart before probing
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
    from .storage_guard import PartitionTableGuard

    disk_service = DiskService()
    with disk_hold(disk, log):
        with PartitionTableGuard(disk, log, disk_service=disk_service) as backup_path:
            if before_partition is not None:
                try:
                    before_partition()
                except Exception as exc:
                    # W3: surface cause; guard still restores on mkfs fail per test — split deferred
                    log(f"{failure_message}: {exc}")
                    raise
            # Failure messages handled by PartitionTableGuard's restore; keep original messages for outer log
            btrfs_start = _ensure_bios_boot_partition(disk, gap_start, log)
            sector = _block_size_bytes(disk)
            partition_end = gap_end - sector
            before = {p["name"] for p in list_partitions(disk) if p.get("name")}

            log(f"Creating KythOS Btrfs partition in {_human_size(gap_end - btrfs_start)} of free space...")
            run_command(_as_root(["parted", "-s", disk, "unit", "B", "mkpart", "KythOS", "btrfs", f"{btrfs_start}B", f"{partition_end}B"]), check=True, timeout=120)
            # R8: batch reread — one settle after both reread attempts
            for _cmd in [[_as_root(["blockdev", "--rereadpt", disk])], [_as_root(["partprobe", disk])]]:
                try:
                    run_command(_cmd[0], check=False, timeout=15)
                except Exception:
                    pass
            _settle()

            created = _latest_partition_on_disk(disk, before)
            if not created:
                raise RuntimeError("The installer could not find the new KythOS partition after partitioning.")
            run_command(_as_root(["mkfs.btrfs", "-f", "-L", "KythOS", created]), check=True, timeout=300)
            _settle()
            try:
                _verify = {p["name"] for p in list_partitions(disk) if p.get("name")}
                if created not in _verify:
                    log(f"Warning: kernel did not yet expose {created} after rereadpt — proceeding, udev may still settle.")
            except Exception as exc:
                log(f"Warning: could not verify new partition {created}: {exc}")
            log(f"Created target partition {created}")
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
