"""Partition operation queue with commit, rollback, and filesystem support.

Stages partition operations (create, delete, resize, format, mount) as a
transaction journal. Operations are validated before commit and the original
partition table is backed up for rollback via sgdisk.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Optional

# pylint: disable-next=unused-import
from .config import FILESYSTEM_OPTIONS, _FILESYSTEM  # noqa: F401 — re-exported for server.py
from .disk import (
    _normal_device_path, list_partitions, _safe_int, _block_size_bytes, _partition_number,
    _partition_start_bytes, _human_size, _latest_partition_on_disk,
)
from .runner import run_command
from .system import _as_root, _settle

_BACKUP_PATH = Path("/tmp/kyth-partition-backup")  # noqa: S108 — unlinked before each write in _save_snapshot
_current_journal: Optional["Journal"] = None


def _require_sgdisk(log=None):
    if not shutil.which("sgdisk"):
        raise RuntimeError("sgdisk (gptfdisk) is required for partition table operations.")


def _require_parted(log=None):
    if not shutil.which("parted"):
        raise RuntimeError("parted is required for partition operations.")


def _require_mkfs(fstype: str, log=None):
    info = _FILESYSTEM.get(fstype)
    if not info:
        raise RuntimeError(f"Unsupported filesystem type: {fstype}")
    if not shutil.which(info["binary"]):
        raise RuntimeError(
            f"{info['binary']} is not available in the live environment. "
            f"Cannot create {fstype} filesystems."
        )


class Journal:
    """Transaction journal for partition operations on a single disk."""

    def __init__(self, disk: str):
        resolved = _normal_device_path(disk)
        if not resolved:
            raise RuntimeError("Invalid disk path for journal.")
        self.disk: str = resolved
        self.ops: list[dict] = []
        self._snapshot_saved = False
        self._committed = False
        self._root_partition: Optional[str] = None

    @property
    def committed(self) -> bool:
        return self._committed

    @property
    def root_partition(self) -> Optional[str]:
        return self._root_partition

    def _save_snapshot(self) -> None:
        _require_sgdisk()
        backup = str(_BACKUP_PATH)
        # sgdisk runs as root and will happily write through a pre-existing
        # symlink at this world-writable-/tmp path — refuse first.
        _BACKUP_PATH.unlink(missing_ok=True)
        run_command(
            _as_root(["sgdisk", "--backup", backup, self.disk]),
            check=True, timeout=30,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        self._snapshot_saved = True

    def _restore_snapshot(self) -> None:
        if not self._snapshot_saved:
            return
        _require_sgdisk()
        backup = str(_BACKUP_PATH)
        if not _BACKUP_PATH.exists():
            return
        run_command(
            _as_root(["sgdisk", "--load-backup", backup, self.disk]),
            check=False, timeout=60,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
        _settle()
        _BACKUP_PATH.unlink(missing_ok=True)
        self._snapshot_saved = False

    def add_op(self, kind: str, params: dict) -> dict:
        op = {
            "kind": kind,
            "params": dict(params),
            "index": len(self.ops),
        }
        self.ops.append(op)
        return op

    def remove_op(self, index: int) -> bool:
        if 0 <= index < len(self.ops):
            self.ops.pop(index)
            return True
        return False

    def clear(self):
        self.ops.clear()

    def pending(self) -> list[dict]:
        return list(self.ops)

    def _find_root_partition(self) -> Optional[str]:
        for part in list_partitions(self.disk):
            name = part.get("name")
            for op in self.ops:
                if op["kind"] == "set_mountpoint" and op["params"].get("mountpoint") == "/":
                    if op["params"].get("partition") == name:
                        return name
        return None

    def validate(self) -> list[str]:
        errors = []

        if not self.ops:
            errors.append("No partition operations have been added.")
            return errors

        gpt = False
        has_efi = False
        has_root = False
        allocated: list[tuple[int, int, str]] = []

        for op in self.ops:
            kind = op["kind"]
            p = op["params"]

            if kind == "new_table":
                table_type = p.get("table_type", "gpt").lower()
                if table_type == "gpt":
                    gpt = True
                allocated.clear()
                has_efi = False
                has_root = False

            elif kind == "create":
                start = _safe_int(p.get("start_bytes"), -1)
                size = _safe_int(p.get("size_bytes"), -1)
                fs = (p.get("fs_type") or "").lower()
                mount = (p.get("mountpoint") or "").lower()

                if start < 0 or size < 0:
                    errors.append("Create partition: invalid start or size.")
                    continue

                end = start + size
                for s, e, n in allocated:
                    if start < e and end > s:
                        errors.append(f"New partition overlaps with existing region ({n}).")
                allocated.append((start, end, fs))

                if mount == "/":
                    if fs != "btrfs":
                        errors.append("Root partition (/) must use the Btrfs filesystem.")
                    has_root = True
                if fs == "fat32" or mount == "/boot/efi":
                    has_efi = True
                if fs == "linux-swap":
                    pass

            elif kind == "delete":
                # Deletion removes the need to track this partition's overlap
                pass

        current_parts = list_partitions(self.disk)
        for part in current_parts:
            name = part.get("name")
            if part.get("efi"):
                has_efi = True
            if part.get("fstype") == "btrfs" and not part.get("current"):
                pass

        if not has_root:
            errors.append("No root partition (/) configured. Mount at least one partition as '/' with Btrfs.")

        for part in current_parts:
            name = part.get("name")
            if part.get("current") or part.get("in_use"):
                for op in self.ops:
                    if op["kind"] in ("delete", "format", "resize") and op["params"].get("partition") == name:
                        errors.append(f"Cannot modify {name} — it is currently mounted or in use.")
                        break

        if gpt and not has_efi:
            pass

        return errors

    def commit(self, log) -> str:
        _require_parted()
        self._save_snapshot()

        for op in self.ops:
            kind = op["kind"]
            p = op["params"]

            if kind == "new_table":
                table_type = p.get("table_type", "gpt")
                log(f"Creating new {table_type.upper()} partition table on {self.disk}...")
                run_command(
                    _as_root(["parted", "-s", self.disk, "mklabel", table_type]),
                    check=True, timeout=30,
                )
                _settle()

            elif kind == "create":
                start = _safe_int(p.get("start_bytes"), 0)
                size = _safe_int(p.get("size_bytes"), 0)
                fs = p.get("fs_type", "btrfs")
                label = p.get("label", "")

                if start <= 0 or size <= 0:
                    raise RuntimeError(f"Create partition: invalid start {start} or size {size}.")

                before = {pt["name"] for pt in list_partitions(self.disk) if pt.get("name")}
                sector = _block_size_bytes(self.disk)
                end_byte = start + size - sector

                fstype_for_parted = fs
                if fstype_for_parted == "linux-swap":
                    fstype_for_parted = "linux-swap"
                elif fstype_for_parted == "fat32":
                    fstype_for_parted = "fat32"

                log(f"Creating {_human_size(size)} partition ({fs}) at offset {start}...")
                run_command(
                    _as_root(["parted", "-s", self.disk, "unit", "B",
                              "mkpart", label or "partition", fstype_for_parted,
                              f"{start}B", f"{end_byte}B"]),
                    check=True, timeout=120,
                )
                _settle()

                created = _latest_partition_on_disk(self.disk, before)
                if not created:
                    raise RuntimeError("Could not find the newly created partition.")

                if fs != "linux-swap":
                    log(f"Formatting {created} as {fs}...")
                    _require_mkfs(fs, log)
                    fmt_cmd = _mkfs_cmd(fs, created, label)
                    run_command(_as_root(fmt_cmd), check=True, timeout=120)

                log(f"Created {created}")

            elif kind == "delete":
                part_name = p.get("partition", "")
                if not part_name:
                    raise RuntimeError("Delete: no partition specified.")
                part_num = _partition_number(part_name)
                log(f"Deleting {part_name}...")
                run_command(
                    _as_root(["parted", "-s", self.disk, "rm", str(part_num)]),
                    check=True, timeout=60,
                )
                _settle()

            elif kind == "resize":
                part_name = p.get("partition", "")
                new_size = _safe_int(p.get("new_size_bytes"), 0)
                if not part_name or new_size <= 0:
                    raise RuntimeError(f"Resize: invalid partition {part_name} or size {new_size}.")
                part_num = _partition_number(part_name)
                start = _partition_start_bytes(part_name)
                new_end = start + new_size - _block_size_bytes(self.disk)
                log(f"Resizing {part_name} to {_human_size(new_size)}...")
                run_command(
                    _as_root(["parted", "---pretend-input-tty", self.disk,
                              "unit", "B", "resizepart", str(part_num), f"{new_end}B"]),
                    input="Yes\n", text=True, check=True, timeout=120,
                )
                _settle()

            elif kind == "format":
                part_name = p.get("partition", "")
                fs = p.get("fs_type", "btrfs")
                label = p.get("label", "")
                if not part_name:
                    raise RuntimeError("Format: no partition specified.")
                log(f"Formatting {part_name} as {fs}...")
                _require_mkfs(fs, log)
                fmt_cmd = _mkfs_cmd(fs, part_name, label)
                run_command(_as_root(fmt_cmd), check=True, timeout=300)

            elif kind == "set_mountpoint":
                pass

        self._root_partition = self._find_root_partition()
        self._committed = True
        log("Partition changes committed successfully.")
        root = self._root_partition or ""
        return root

    def rollback(self, log) -> None:
        if not self._snapshot_saved:
            log("No partition snapshot to restore from.")
            self.ops.clear()
            return
        log("Rolling back partition changes...")
        self._restore_snapshot()
        self.ops.clear()
        self._committed = False
        self._root_partition = None
        log("Partition table restored to previous state.")


def _mkfs_cmd(fstype: str, device: str, label: str = "") -> list[str]:
    info = _FILESYSTEM.get(fstype)
    if not info:
        return []
    cmd = list(info["args"])
    if label:
        if fstype == "fat32":
            cmd.extend(["-n", label])
        else:
            cmd.extend(["-L", label])
    cmd.append(device)
    return cmd


def get_journal() -> Optional[Journal]:
    return _current_journal


def init_journal(disk: str) -> Journal:
    # Single module-level journal for the installer's one active session —
    # get/init/reset above are its whole public API, so `global` here is the
    # deliberate single-owner pattern, not incidental shared mutable state.
    global _current_journal  # noqa: PLW0603
    _current_journal = Journal(disk)
    return _current_journal


def reset_journal() -> None:
    global _current_journal  # noqa: PLW0603
    if _current_journal:
        _current_journal.ops.clear()
        _current_journal._committed = False
        _current_journal._root_partition = None
    _current_journal = None
