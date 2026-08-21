"""Partition table backup/restore guard — single durability primitive."""

from __future__ import annotations

import contextlib
import fcntl
import os
import tempfile
from pathlib import Path


def _allow_unlocked_disk() -> bool:
    return os.environ.get("KYTH_INSTALL_ALLOW_NO_DISK_LOCK", "") == "1"


@contextlib.contextmanager
def DiskLease(disk: str, log, *, exclusive: bool = True):
    """Shared flock primitive for both guided and manual partition paths.

    Guided path (plan._commit_new_kythos_partition) and manual
    Journal.commit both need to serialize against udev/second installer.
    Using one helper avoids duplicate flock logic and accidental
    exclusive-vs-shared mismatch. Fail closed unless
    KYTH_INSTALL_ALLOW_NO_DISK_LOCK=1 (constrained CI).
    """
    fd = -1
    try:
        try:
            fd = os.open(disk, os.O_RDONLY)
            flag = fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH
            try:
                fcntl.flock(fd, flag | fcntl.LOCK_NB)
                kind = "exclusive" if exclusive else "shared"
                log(f"Holding {kind} lock on {disk}...")
            except BlockingIOError:
                raise RuntimeError(
                    f"Another process is using {disk}; close other installers and retry."
                )
        except OSError as err:
            # Hybrid OSError+RuntimeError (tests / rare callers): re-raise as-is.
            # Otherwise fail closed — a missing lock is how two installers race.
            if isinstance(err, RuntimeError):
                raise
            if _allow_unlocked_disk():
                log(f"Warning: could not hold lock on {disk}: {err}")
                fd = -1
            else:
                raise RuntimeError(
                    f"Could not lock {disk} for exclusive use: {err}"
                ) from err
        yield
    finally:
        if fd != -1:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
                pass
            try:
                os.close(fd)
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
                pass


@contextlib.contextmanager
def PartitionTableGuard(disk: str, log, *, disk_service=None, should_restore=None):
    """Back up GPT/MBR, fsync file+dir, yield, restore on exception.

    Consolidates the duplicate `sgdisk --backup`/`--load-backup` + fsync
    pattern from `plan._commit_new_kythos_partition` and
    `partition_ops.Journal._save_snapshot`. Uses `disk_service` if given,
    else lazy `DiskService`.

    *should_restore*, when supplied, is called after a failure; return
    False to skip table restore (format/shrink of an existing filesystem
    cannot be undone by reloading GPT, and reloading after shrink is
    worse than leaving the in-progress table).
    """
    if disk_service is None:
        from .services.disk_service import DiskService as _Concrete

        disk_service = _Concrete()
    # dry_run still needs backup dir for symmetry, but no sgdisk required
    with tempfile.TemporaryDirectory(prefix="kyth-partition-") as backup_dir:
        backup_path = str(Path(backup_dir) / "partition-table.backup")
        log(f"Backing up the partition table before changing it...")
        disk_service.backup_table(disk, backup_path)
        # durability: fsync file + directory
        try:
            with open(backup_path, "rb") as bf:
                os.fsync(bf.fileno())
            dfd = os.open(backup_dir, os.O_DIRECTORY)
            try:
                os.fsync(dfd)
            finally:
                os.close(dfd)
        except OSError as err:
            log(f"Warning: could not fsync partition backup: {err}")
        try:
            yield backup_path
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            restore = True
            if should_restore is not None:
                try:
                    restore = bool(should_restore())
                except (OSError, ValueError, RuntimeError, AttributeError, TypeError, KeyError):
                    restore = True
            if restore:
                try:
                    disk_service.restore_table(disk, backup_path)
                    log("Partition table restored to its state before this attempt.")
                except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as restore_exc:  # noqa: BLE001 -- narrow: best-effort production path
                    log(f"Warning: automatic partition table restore failed: {restore_exc}")
            else:
                log(
                    "Skipped partition-table restore: a format or filesystem "
                    "shrink already completed and cannot be undone."
                )
            raise
