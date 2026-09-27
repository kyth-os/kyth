"""Disk execution service for committing partitioning and filesystem creation tasks."""
from __future__ import annotations

import json
import shutil
import subprocess
from ..runner import run_command
from ..system import _as_root, _settle


class DiskService:
    """Manages system execution of disk alteration utilities with a mockable dry-run mode."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self.journal: list[list[str]] = []

    def execute(self, cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
        if self.dry_run:
            self.journal.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        return run_command(cmd, **kwargs)

    def settle(self) -> None:
        if not self.dry_run:
            _settle()

    def _typed_operation(self, payload: dict, *, timeout: int) -> None:
        """Send one typed destructive operation to the root-owned Rust helper."""
        self.execute(
            _as_root(["kyth-installer-exec", "--operation", "disk"]),
            input=json.dumps(payload, separators=(",", ":")),
            text=True,
            check=True,
            timeout=timeout,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

    def backup_table(self, disk: str, backup_path: str) -> None:
        if self.dry_run:
            self.execute(
                _as_root(["sgdisk", "--backup", backup_path, disk]),
                check=True, timeout=30,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
        else:
            self._typed_operation(
                {"operation": "backup_table", "disk": disk, "backup_path": backup_path},
                timeout=30,
            )

    def restore_table(self, disk: str, backup_path: str) -> None:
        if self.dry_run:
            self.execute(
                _as_root(["sgdisk", "--load-backup", backup_path, disk]),
                check=True, timeout=60,
                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            )
        else:
            self._typed_operation(
                {"operation": "restore_table", "disk": disk, "backup_path": backup_path},
                timeout=60,
            )
        self.settle()

    def create_label(self, disk: str, table_type: str) -> None:
        if self.dry_run:
            self.execute(
                _as_root(["parted", "-s", disk, "mklabel", table_type]),
                check=True, timeout=30,
            )
        else:
            self._typed_operation(
                {"operation": "create_label", "disk": disk, "table_type": table_type},
                timeout=30,
            )
        self.settle()

    def create_partition(
        self, disk: str, start: int, size: int, fs: str, label: str
    ) -> None:
        from ..disk import _block_size_bytes
        sector = 512 if self.dry_run else _block_size_bytes(disk)
        if self.dry_run:
            end_byte = start + size - sector
            self.execute(
                _as_root(["parted", "-s", disk, "unit", "B",
                          "mkpart", label or "partition", fs,
                          f"{start}B", f"{end_byte}B"]),
                check=True, timeout=120,
            )
        else:
            self._typed_operation(
                {
                    "operation": "create_partition", "disk": disk,
                    "start": start, "size": size, "fs": fs, "label": label,
                    "sector_size": sector,
                },
                timeout=120,
            )
        self.settle()

    def create_unformatted_partition(self, disk: str, start: int, size: int, label: str) -> None:
        from ..disk import _block_size_bytes
        sector = 512 if self.dry_run else _block_size_bytes(disk)
        if self.dry_run:
            end_byte = start + size - sector
            self.execute(
                _as_root(["parted", "-s", disk, "unit", "B", "mkpart", label,
                          f"{start}B", f"{end_byte}B"]),
                check=True, timeout=120,
            )
        else:
            self._typed_operation(
                {
                    "operation": "create_unformatted_partition", "disk": disk,
                    "start": start, "size": size, "label": label,
                    "sector_size": sector,
                },
                timeout=120,
            )
        self.settle()

    def delete_partition(self, disk: str, part_num: int) -> None:
        if self.dry_run:
            self.execute(
                _as_root(["parted", "-s", disk, "rm", str(part_num)]),
                check=True, timeout=60,
            )
        else:
            self._typed_operation(
                {"operation": "delete_partition", "disk": disk, "part_num": part_num},
                timeout=60,
            )
        self.settle()

    def set_partition_flag(self, disk: str, part_num: int, flag: str, enabled: bool = True) -> None:
        if self.dry_run:
            self.execute(
                _as_root(["parted", "-s", disk, "set", str(part_num), flag, "on" if enabled else "off"]),
                check=True, timeout=60,
            )
        else:
            self._typed_operation(
                {
                    "operation": "set_partition_flag", "disk": disk,
                    "part_num": part_num, "flag": flag, "enabled": enabled,
                },
                timeout=60,
            )
        self.settle()

    def resize_partition(self, disk: str, part_num: int, start: int, new_size: int) -> None:
        if not self.dry_run and not shutil.which("parted"):
            raise RuntimeError("parted is required for partition operations.")
        from ..disk import _block_size_bytes
        sector = 512 if self.dry_run else _block_size_bytes(disk)
        if self.dry_run:
            new_end = start + new_size - sector
            self.execute(
                _as_root(["parted", "---pretend-input-tty", disk,
                          "unit", "B", "resizepart", str(part_num), f"{new_end}B"]),
                input="Yes\n", text=True, check=True, timeout=120,
            )
        else:
            self._typed_operation(
                {
                    "operation": "resize_partition", "disk": disk,
                    "part_num": part_num, "start": start, "new_size": new_size,
                    "sector_size": sector,
                },
                timeout=120,
            )
        self.settle()

    def format_filesystem(self, device: str, fs: str, label: str) -> None:
        from ..partition_ops import _require_mkfs, _mkfs_cmd
        if self.dry_run:
            fmt_cmd = _mkfs_cmd(fs, device, label)
            self.execute(_as_root(fmt_cmd), check=True, timeout=120 if fs != "btrfs" else 300)
        else:
            _require_mkfs(fs)
            self._typed_operation(
                {
                    "operation": "format_filesystem", "device": device,
                    "fs": fs, "label": label,
                },
                timeout=120 if fs != "btrfs" else 300,
            )
