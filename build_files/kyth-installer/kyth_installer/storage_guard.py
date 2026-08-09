"""Partition table backup/restore guard — single durability primitive."""

from __future__ import annotations

import contextlib
import fcntl
import os
import tempfile
from pathlib import Path


@contextlib.contextmanager
def DiskLease(disk: str, log, *, exclusive: bool = True):
    """Shared flock primitive for both guided and manual partition paths.

    Guided path (plan._commit_new_kythos_partition) and manual
    Journal.commit both need to serialize against udev/second installer.
    Using one helper avoids duplicate flock logic and accidental
    exclusive-vs-shared mismatch. Best-effort on live ISO where disk may be
    busy — falls back to warning instead of failing.
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
        except OSError as exc:
            # Re-raise the BlockingIOError wrapped as RuntimeError, otherwise warn
            if isinstance(exc, RuntimeError):
                raise
            log(f"Warning: could not hold lock on {disk}: {exc}")
            fd = -1
        yield
    finally:
        if fd != -1:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except Exception:
                pass
            try:
                os.close(fd)
            except Exception:
                pass


@contextlib.contextmanager
def PartitionTableGuard(disk: str, log, *, disk_service=None):
    """Back up GPT/MBR, fsync file+dir, yield, restore on exception.

    Consolidates the duplicate `sgdisk --backup`/`--load-backup` + fsync
    pattern from `plan._commit_new_kythos_partition` and
    `partition_ops.Journal._save_snapshot`. Uses `disk_service` if given,
    else lazy `DiskService`.
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
        except OSError as exc:
            log(f"Warning: could not fsync partition backup: {exc}")
        try:
            yield backup_path
        except Exception:
            # restore on any exception inside the guarded scope
            try:
                disk_service.restore_table(disk, backup_path)
                log("Partition table restored to its state before this attempt.")
            except Exception as restore_exc:
                log(f"Warning: automatic partition table restore failed: {restore_exc}")
            raise
