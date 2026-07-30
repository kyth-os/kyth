"""Installer core service for executing installer actions independently of HTTP transport."""
from __future__ import annotations

from typing import TYPE_CHECKING

from kyth_installer import context as context_module
from kyth_installer import disk, execution, partition_ops, runner, system, validation

if TYPE_CHECKING:
    from kyth_installer.context import InstallerContext


def _validate_fs_type(fs_type: str) -> dict | None:
    if not any(item["id"] == fs_type for item in partition_ops.FILESYSTEM_OPTIONS):
        return {"ok": False, "message": f"Unsupported filesystem: {fs_type}"}
    return None


class InstallerService:
    """Encapsulates all installation and disk partitioning business logic."""

    def __init__(self, context: InstallerContext) -> None:
        self.context = context

    def _journal_for(self, body: dict) -> tuple[str | None, object | None, dict | None]:
        disk_path = disk._normal_device_path(body.get("disk", ""))
        if not disk_path:
            return None, None, {"ok": False, "message": "No disk specified."}
        journal = partition_ops.get_journal(self.context)
        if not journal or journal.disk != disk_path:
            return None, None, {
                "ok": False,
                "message": "No active partition journal for this disk. Create a new partition table first.",
            }
        return disk_path, journal, None

    def _partition_for(self, body: dict) -> tuple[str | None, object | None, str | None, dict | None]:
        disk_path, journal, error = self._journal_for(body)
        partition = disk._normal_device_path(body.get("partition", ""))
        if error or not partition:
            return None, None, None, error or {"ok": False, "message": "Disk and partition are required."}
        if disk._parent_disk(partition) != disk_path:
            return None, None, None, {"ok": False, "message": "Partition does not belong to the active disk."}
        return disk_path, journal, partition, None

    def new_table(self, body: dict) -> dict:
        disk_path = disk._normal_device_path(body.get("disk", ""))
        if not disk_path:
            return {"ok": False, "message": "No disk specified."}
        if disk_path not in {d["name"] for d in disk.list_disks()}:
            return {"ok": False, "message": "Invalid or unsafe disk."}
        table_type = body.get("table_type", "gpt")
        if table_type not in ("gpt", "msdos"):
            return {"ok": False, "message": "Table type must be 'gpt' or 'msdos'."}
        journal = partition_ops.init_journal(disk_path, self.context)
        journal.add_op("new_table", {"table_type": table_type})
        return {"ok": True, "pending": len(journal.ops)}

    def create_partition(self, body: dict) -> dict:
        _disk, journal, error = self._journal_for(body)
        if error:
            return error
        start = disk._safe_int(body.get("start_bytes"), -1)
        size = disk._safe_int(body.get("size_bytes"), -1)
        if start < 0 or size < 1:
            return {"ok": False, "message": "Invalid start offset or size."}
        fs_type = body.get("fs_type", "btrfs")
        fs_error = _validate_fs_type(fs_type)
        if fs_error:
            return fs_error
        journal.add_op("create", {
            "start_bytes": start,
            "size_bytes": size,
            "fs_type": fs_type,
            "label": body.get("label", ""),
            "mountpoint": body.get("mountpoint", ""),
        })
        errors = journal.validate()
        return {"ok": not errors, "pending": len(journal.ops), "errors": errors}

    def delete_partition(self, body: dict) -> dict:
        disk_path, journal, partition, error = self._partition_for(body)
        if error:
            return error
        parts = {part["name"]: part for part in disk.list_partitions(disk_path)}
        if partition not in parts:
            return {"ok": False, "message": f"Partition {partition} not found."}
        if parts[partition].get("current") or parts[partition].get("in_use"):
            return {"ok": False, "message": "Cannot delete a mounted or in-use partition."}
        journal.add_op("delete", {"partition": partition})
        return {"ok": True, "pending": len(journal.ops)}

    def resize_partition(self, body: dict) -> dict:
        disk_path, journal, partition, error = self._partition_for(body)
        if error:
            return error
        new_size = disk._safe_int(body.get("new_size_bytes"), -1)
        if new_size < 1:
            return {"ok": False, "message": "A new size is required."}
        parts = {part["name"]: part for part in disk.list_partitions(disk_path)}
        if partition not in parts:
            return {"ok": False, "message": f"Partition {partition} not found."}
        if new_size >= disk._safe_int(parts[partition].get("size_bytes")):
            return {"ok": False, "message": "New size must be smaller than current size for resize."}
        journal.add_op("resize", {"partition": partition, "new_size_bytes": new_size})
        return {"ok": True, "pending": len(journal.ops)}

    def format_partition(self, body: dict) -> dict:
        _disk, journal, partition, error = self._partition_for(body)
        if error:
            return error
        fs_type = body.get("fs_type", "btrfs")
        fs_error = _validate_fs_type(fs_type)
        if fs_error:
            return fs_error
        journal.add_op("format", {
            "partition": partition, "fs_type": fs_type, "label": body.get("label", ""),
        })
        return {"ok": True, "pending": len(journal.ops)}

    def set_mountpoint(self, body: dict) -> dict:
        _disk, journal, partition, error = self._partition_for(body)
        if error:
            return error
        mountpoint = body.get("mountpoint", "").strip()
        if mountpoint and mountpoint != "swap" and not mountpoint.startswith("/"):
            return {"ok": False, "message": "Mount point must be an absolute path (e.g. /, /home)."}
        journal.add_op("set_mountpoint", {"partition": partition, "mountpoint": mountpoint})
        return {"ok": True, "pending": len(journal.ops)}

    def commit_partitions(self, body: dict) -> dict:
        _disk, journal, error = self._journal_for(body)
        if error:
            return error
        errors = journal.validate()
        if errors:
            return {"ok": False, "message": "Validation failed.", "errors": errors}
        try:
            self.context.transition(context_module.InstallLifecycle.PARTITIONING)
            root_part = journal.commit(
                lambda msg: self.context.events.publish({"type": "log", "text": f"[partition] {msg}"})
            )
            self.context.transition(context_module.InstallLifecycle.IDLE)
            return {"ok": True, "root_partition": root_part}
        except RuntimeError as exc:
            journal.rollback(lambda _msg: None)
            self.context.transition(context_module.InstallLifecycle.FAILED)
            return {"ok": False, "message": str(exc)}

    def rollback_partitions(self, body: dict) -> dict:
        _disk, journal, error = self._journal_for(body)
        if error:
            return error
        try:
            journal.rollback(lambda _msg: None)
            partition_ops.reset_journal(self.context)
            return {"ok": True}
        except RuntimeError as exc:
            return {"ok": False, "message": str(exc)}

    def start_install(self, body: dict) -> dict:
        # install.py is imported lazily here, not at module level: it pulls in
        # plan.py, which imports partition_ops.get_journal by name — a real
        # circular import when this module is reached via partition_ops.py's
        # own `from .services.disk_service import DiskService` (partition_ops
        # -> services/__init__.py -> installer_service.py -> install.py ->
        # plan.py -> back into the still-initializing partition_ops.py).
        from kyth_installer import install
        try:
            state = validation.validate_install_request(body, self.context)
        except validation.InstallRequestError as exc:
            return {"started": False, "message": str(exc)}
        if not execution.start_installation(self.context, state, install._run_install):
            return {"started": False, "message": "An installation is already running."}
        return {"started": True}

    def reboot(self, _body: dict) -> dict:
        result = runner.run_command(
            system._as_root(["systemctl", "reboot"]),
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip() or "reboot command failed"}
        return {"ok": True}
