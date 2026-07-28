"""Partition operation queue with commit, rollback, and filesystem support.

Stages partition operations (create, delete, resize, format, mount) as a
transaction journal. Operations are validated before commit and the original
partition table is backed up for rollback via sgdisk.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Optional

# pylint: disable-next=unused-import
from .config import FILESYSTEM_OPTIONS, _FILESYSTEM  # noqa: F401 — re-exported for server.py
from .disk import (
    _normal_device_path, list_disks, list_partitions, _safe_int, _partition_number,
    _partition_start_bytes, _human_size, _latest_partition_on_disk,
)
from .fsresize import shrink_filesystem
from .services.disk_service import DiskService

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

    def __init__(self, disk: str, disk_service: DiskService | None = None):
        resolved = _normal_device_path(disk)
        if not resolved:
            raise RuntimeError("Invalid disk path for journal.")
        self.disk: str = resolved
        self.ops: list[dict] = []
        self._snapshot_saved = False
        self._committed = False
        self._root_partition: Optional[str] = None
        self._backup_dir: tempfile.TemporaryDirectory[str] | None = None
        self._disk_service = disk_service or DiskService()

    @property
    def committed(self) -> bool:
        return self._committed

    @property
    def root_partition(self) -> Optional[str]:
        return self._root_partition

    def _save_snapshot(self) -> None:
        if not self._disk_service.dry_run:
            _require_sgdisk()
        self._discard_snapshot()
        self._backup_dir = tempfile.TemporaryDirectory(prefix="kyth-partition-")
        backup_path = Path(self._backup_dir.name) / "partition-table.backup"
        backup = str(backup_path)
        self._disk_service.backup_table(self.disk, backup)
        self._snapshot_saved = True

    def _restore_snapshot(self) -> None:
        if not self._snapshot_saved:
            return
        if not self._disk_service.dry_run:
            _require_sgdisk()
        if self._backup_dir is None:
            return
        backup_path = Path(self._backup_dir.name) / "partition-table.backup"
        backup = str(backup_path)
        if not backup_path.exists() and not self._disk_service.dry_run:
            self._discard_snapshot()
            return
        self._disk_service.restore_table(self.disk, backup)
        self._discard_snapshot()

    def _discard_snapshot(self) -> None:
        if self._backup_dir is not None:
            self._backup_dir.cleanup()
            self._backup_dir = None
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
        # A partition created with mountpoint="/" in the same journal (the
        # normal "Create Partition" dialog flow) records its resolved device
        # name onto the create op's own params during commit() — check that
        # first, since the partition doesn't exist for list_partitions() to
        # match against until after the create op has actually run.
        for op in self.ops:
            if op["kind"] == "create" and op["params"].get("mountpoint") == "/":
                name = op["params"].get("partition")
                if name:
                    return name
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

        has_root = False
        allocated: list[tuple[int, int, str]] = []

        # MBR (msdos) tables support at most 4 primary partitions, and this
        # installer does not create extended/logical partitions to work
        # around that limit — fail closed here with a clear message instead
        # of letting a 5th mkpart hit parted's own cryptic error later.
        # Table type starts from whatever the disk currently has unless a
        # new_table op in this journal replaces it.
        disks_by_name = {d["name"]: d for d in list_disks()}
        table_type = (disks_by_name.get(self.disk, {}).get("partition_table") or "").lower()
        primary_count = (
            len([pt for pt in list_partitions(self.disk) if pt.get("name")])
            if table_type == "msdos" else 0
        )

        for op in self.ops:
            kind = op["kind"]
            p = op["params"]

            if kind == "new_table":
                allocated.clear()
                has_root = False
                table_type = (p.get("table_type") or "gpt").lower()
                primary_count = 0

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

                if table_type == "msdos":
                    primary_count += 1
                    if primary_count > 4:
                        errors.append(
                            "MBR (msdos) partition tables support at most 4 primary "
                            "partitions, and this installer does not create extended/"
                            "logical partitions. Use a GPT table instead, or remove a "
                            "partition from this layout."
                        )

                if mount == "/":
                    if fs != "btrfs":
                        errors.append("Root partition (/) must use the Btrfs filesystem.")
                    has_root = True

            elif kind == "delete" and table_type == "msdos":
                primary_count = max(0, primary_count - 1)

        if not has_root:
            errors.append("No root partition (/) configured. Mount at least one partition as '/' with Btrfs.")

        current_parts = list_partitions(self.disk)
        for part in current_parts:
            name = part.get("name")
            if part.get("current") or part.get("in_use"):
                for op in self.ops:
                    kind = op["kind"]
                    params = op["params"]
                    if kind in ("delete", "format", "resize") and params.get("partition") == name:
                        errors.append(f"Cannot modify {name} — it is currently mounted or in use.")
                        break
                    # A set_mountpoint("/", name) op makes this the install's
                    # root partition, which gets reformatted at install time
                    # even though no "format" op was staged for it here — that
                    # eventual mkfs must be rejected too, not just an explicit
                    # format/delete/resize op.
                    if kind == "set_mountpoint" and params.get("partition") == name and params.get("mountpoint") == "/":
                        errors.append(f"Cannot set {name} as the root partition — it is currently mounted or in use.")
                        break

        return errors

    def _commit_new_table(self, p: dict, log) -> None:
        table_type = p.get("table_type", "gpt")
        log(f"Creating new {table_type.upper()} partition table on {self.disk}...")
        self._disk_service.create_label(self.disk, table_type)

    def _commit_create(self, p: dict, log) -> None:
        start = _safe_int(p.get("start_bytes"), 0)
        size = _safe_int(p.get("size_bytes"), 0)
        fs = p.get("fs_type", "btrfs")
        label = p.get("label", "")

        if start <= 0 or size <= 0:
            raise RuntimeError(f"Create partition: invalid start {start} or size {size}.")

        before = set()
        if not self._disk_service.dry_run:
            before = {pt["name"] for pt in list_partitions(self.disk) if pt.get("name")}

        log(f"Creating {_human_size(size)} partition ({fs}) at offset {start}...")
        self._disk_service.create_partition(self.disk, start, size, fs, label)

        if self._disk_service.dry_run:
            created = f"{self.disk}p99"
        else:
            created = _latest_partition_on_disk(self.disk, before)
            if not created:
                raise RuntimeError("Could not find the newly created partition.")
        # Record the resolved device name back onto the op so
        # _find_root_partition() (and anything else inspecting the
        # journal after commit) can tell which real partition this
        # create op produced.
        p["partition"] = created

        if fs != "linux-swap":
            log(f"Formatting {created} as {fs}...")
            self._disk_service.format_filesystem(created, fs, label)

        log(f"Created {created}")

    def _commit_delete(self, p: dict, log) -> None:
        part_name = p.get("partition", "")
        if not part_name:
            raise RuntimeError("Delete: no partition specified.")
        part_num = _partition_number(part_name) if not self._disk_service.dry_run else 99
        log(f"Deleting {part_name}...")
        self._disk_service.delete_partition(self.disk, part_num)

    def _commit_resize(self, p: dict, log) -> None:
        part_name = p.get("partition", "")
        new_size = _safe_int(p.get("new_size_bytes"), 0)
        if not part_name or new_size <= 0:
            raise RuntimeError(f"Resize: invalid partition {part_name} or size {new_size}.")
        if not self._disk_service.dry_run:
            # parted only moves the partition table boundary — it never
            # touches the filesystem inside. Re-read the current fstype
            # right before shrinking (not whatever it was when this op was
            # staged) and shrink the filesystem itself first, or refuse for
            # any type without a safe shrink path. Skipping this would
            # silently corrupt whatever filesystem already lives here.
            current = {pt["name"]: pt for pt in list_partitions(self.disk)}
            part_info = current.get(part_name)
            if not part_info:
                raise RuntimeError(f"Resize: {part_name} was not found on {self.disk}.")
            fstype = (part_info.get("fstype") or "").lower()
            log(f"Shrinking the {fstype or 'unknown'} filesystem on {part_name} "
                "before moving the partition boundary...")
            shrink_filesystem(part_name, fstype, new_size, log)
        part_num = _partition_number(part_name) if not self._disk_service.dry_run else 99
        start = _partition_start_bytes(part_name) if not self._disk_service.dry_run else 1024**2
        log(f"Resizing {part_name} to {_human_size(new_size)}...")
        self._disk_service.resize_partition(self.disk, part_num, start, new_size)

    def _commit_format(self, p: dict, log) -> None:
        part_name = p.get("partition", "")
        fs = p.get("fs_type", "btrfs")
        label = p.get("label", "")
        if not part_name:
            raise RuntimeError("Format: no partition specified.")
        log(f"Formatting {part_name} as {fs}...")
        self._disk_service.format_filesystem(part_name, fs, label)

    def commit(self, log) -> str:
        if not self._disk_service.dry_run:
            _require_parted()
        self._save_snapshot()

        for op in self.ops:
            kind = op["kind"]
            p = op["params"]

            if kind == "new_table":
                self._commit_new_table(p, log)
            elif kind == "create":
                self._commit_create(p, log)
            elif kind == "delete":
                self._commit_delete(p, log)
            elif kind == "resize":
                self._commit_resize(p, log)
            elif kind == "format":
                self._commit_format(p, log)
            # "set_mountpoint" ops are pure journal metadata (consumed by
            # _find_root_partition() below) — no disk operation of their own.

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
    cmd = [info["binary"]] + list(info["args"])
    if label:
        if fstype == "fat32":
            cmd.extend(["-n", label])
        else:
            cmd.extend(["-L", label])
    cmd.append(device)
    return cmd


def get_journal(context) -> Optional[Journal]:
    with context.state_lock:
        return context.journal


def init_journal(disk: str, context) -> Journal:
    with context.state_lock:
        reset_journal(context)
        context.journal = Journal(disk)
        return context.journal


def reset_journal(context) -> None:
    with context.state_lock:
        journal = context.journal
        if journal:
            journal.ops.clear()
            journal._committed = False
            journal._root_partition = None
            journal._discard_snapshot()
        context.journal = None
