"""Installer core service for executing installer actions independently of HTTP transport."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kyth_installer.context import InstallerContext


class InstallerService:
    """Encapsulates all installation and disk partitioning business logic."""

    def __init__(self, context: InstallerContext) -> None:
        self.context = context

    def _journal_for(self, body: dict) -> tuple[str | None, object | None, dict | None]:
        from kyth_installer.disk import _normal_device_path
        from kyth_installer.partition_ops import get_journal
        disk = _normal_device_path(body.get("disk", ""))
        if not disk:
            return None, None, {"ok": False, "message": "No disk specified."}
        journal = get_journal(self.context)
        if not journal or journal.disk != disk:
            return None, None, {
                "ok": False,
                "message": "No active partition journal for this disk. Create a new partition table first.",
            }
        return disk, journal, None

    def _partition_for(self, body: dict) -> tuple[str | None, object | None, str | None, dict | None]:
        from kyth_installer.disk import _normal_device_path
        disk, journal, error = self._journal_for(body)
        partition = _normal_device_path(body.get("partition", ""))
        if error or not partition:
            return None, None, None, error or {"ok": False, "message": "Disk and partition are required."}
        return disk, journal, partition, None

    def new_table(self, body: dict) -> dict:
        from kyth_installer.disk import _normal_device_path, list_disks
        from kyth_installer.partition_ops import init_journal
        disk = _normal_device_path(body.get("disk", ""))
        if not disk:
            return {"ok": False, "message": "No disk specified."}
        if disk not in {d["name"] for d in list_disks()}:
            return {"ok": False, "message": "Invalid or unsafe disk."}
        table_type = body.get("table_type", "gpt")
        if table_type not in ("gpt", "msdos"):
            return {"ok": False, "message": "Table type must be 'gpt' or 'msdos'."}
        journal = init_journal(disk, self.context)
        journal.add_op("new_table", {"table_type": table_type})
        return {"ok": True, "pending": len(journal.ops)}

    def create_partition(self, body: dict) -> dict:
        from kyth_installer.disk import _safe_int
        from kyth_installer.partition_ops import FILESYSTEM_OPTIONS
        _disk, journal, error = self._journal_for(body)
        if error:
            return error
        start = _safe_int(body.get("start_bytes"), -1)
        size = _safe_int(body.get("size_bytes"), -1)
        if start < 0 or size < 1:
            return {"ok": False, "message": "Invalid start offset or size."}
        fs_type = body.get("fs_type", "btrfs")
        if not any(item["id"] == fs_type for item in FILESYSTEM_OPTIONS):
            return {"ok": False, "message": f"Unsupported filesystem: {fs_type}"}
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
        from kyth_installer.disk import list_partitions
        disk, journal, partition, error = self._partition_for(body)
        if error:
            return error
        parts = {part["name"]: part for part in list_partitions(disk)}
        if partition not in parts:
            return {"ok": False, "message": f"Partition {partition} not found."}
        if parts[partition].get("current") or parts[partition].get("in_use"):
            return {"ok": False, "message": "Cannot delete a mounted or in-use partition."}
        journal.add_op("delete", {"partition": partition})
        return {"ok": True, "pending": len(journal.ops)}

    def resize_partition(self, body: dict) -> dict:
        from kyth_installer.disk import list_partitions, _safe_int
        disk, journal, partition, error = self._partition_for(body)
        if error:
            return error
        new_size = _safe_int(body.get("new_size_bytes"), -1)
        if new_size < 1:
            return {"ok": False, "message": "A new size is required."}
        parts = {part["name"]: part for part in list_partitions(disk)}
        if partition not in parts:
            return {"ok": False, "message": f"Partition {partition} not found."}
        if new_size >= _safe_int(parts[partition].get("size_bytes")):
            return {"ok": False, "message": "New size must be smaller than current size for resize."}
        journal.add_op("resize", {"partition": partition, "new_size_bytes": new_size})
        return {"ok": True, "pending": len(journal.ops)}

    def format_partition(self, body: dict) -> dict:
        from kyth_installer.partition_ops import FILESYSTEM_OPTIONS
        _disk, journal, partition, error = self._partition_for(body)
        if error:
            return error
        fs_type = body.get("fs_type", "btrfs")
        if not any(item["id"] == fs_type for item in FILESYSTEM_OPTIONS):
            return {"ok": False, "message": f"Unsupported filesystem: {fs_type}"}
        journal.add_op("format", {
            "partition": partition, "fs_type": fs_type, "label": body.get("label", ""),
        })
        return {"ok": True, "pending": len(journal.ops)}

    def set_mountpoint(self, body: dict) -> dict:
        _disk, journal, partition, error = self._partition_for(body)
        if error:
            return error
        mountpoint = body.get("mountpoint", "").strip()
        if mountpoint and not mountpoint.startswith("/"):
            return {"ok": False, "message": "Mount point must be an absolute path (e.g. /, /home)."}
        journal.add_op("set_mountpoint", {"partition": partition, "mountpoint": mountpoint})
        return {"ok": True, "pending": len(journal.ops)}

    def commit_partitions(self, body: dict) -> dict:
        from kyth_installer.context import InstallLifecycle
        _disk, journal, error = self._journal_for(body)
        if error:
            return error
        errors = journal.validate()
        if errors:
            return {"ok": False, "message": "Validation failed.", "errors": errors}
        try:
            self.context.transition(InstallLifecycle.PARTITIONING)
            root_part = journal.commit(
                lambda msg: self.context.events.publish({"type": "log", "text": f"[partition] {msg}"})
            )
            self.context.transition(InstallLifecycle.IDLE)
            return {"ok": True, "root_partition": root_part}
        except RuntimeError as exc:
            journal.rollback(lambda _msg: None)
            self.context.transition(InstallLifecycle.FAILED)
            return {"ok": False, "message": str(exc)}

    def rollback_partitions(self, body: dict) -> dict:
        from kyth_installer.partition_ops import reset_journal
        _disk, journal, error = self._journal_for(body)
        if error:
            return error
        try:
            journal.rollback(lambda _msg: None)
            reset_journal(self.context)
            return {"ok": True}
        except RuntimeError as exc:
            return {"ok": False, "message": str(exc)}

    def start_install(self, body: dict) -> dict:
        from kyth_installer import install
        from kyth_installer.execution import start_installation
        from kyth_installer.validation import InstallRequestError, validate_install_request
        try:
            state = validate_install_request(body, self.context)
        except InstallRequestError as exc:
            return {"started": False, "message": str(exc)}
        if not start_installation(self.context, state, install._run_install):
            return {"started": False, "message": "An installation is already running."}
        return {"started": True}

    def reboot(self, _body: dict) -> dict:
        from kyth_installer.runner import run_command
        from kyth_installer.system import _as_root
        result = run_command(
            _as_root(["systemctl", "reboot"]),
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {"ok": False, "error": result.stderr.strip() or "reboot command failed"}
        return {"ok": True}
