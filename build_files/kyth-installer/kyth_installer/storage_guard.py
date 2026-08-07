"""Partition table backup/restore guard — single durability primitive."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


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
