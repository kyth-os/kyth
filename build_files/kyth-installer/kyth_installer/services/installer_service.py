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
        import re
        import threading
        from kyth_installer.config import _IS_LIVE_SESSION
        from kyth_installer.context import InstallLifecycle, InstallationState
        from kyth_installer.disk import (
            find_efi_partition,
            list_disks,
            list_free_space,
            list_partitions,
            _safe_int,
        )
        from kyth_installer.partition_ops import get_journal
        from kyth_installer.plan import _validate_storage_intent
        from kyth_installer.system import _hash_password, list_timezones
        from kyth_installer import install

        disk = body.get("disk", "")
        disks = {item["name"]: item for item in list_disks()}
        if disk not in disks:
            return {"started": False, "message": "Invalid disk."}

        install_mode = body.get("install_mode", "wipe")
        if install_mode not in ("wipe", "alongside", "resize_ntfs", "free_space", "manual"):
            install_mode = "wipe"
        target_partition = resize_partition = efi_partition = ""
        resize_gib = free_region_start = free_region_end = 0

        if install_mode == "alongside":
            target_partition = body.get("target_partition", "")
            if target_partition not in {part.get("name") for part in list_partitions(disk)}:
                return {"started": False, "message": "Invalid target partition."}
            efi_partition = body.get("efi_partition", "") or find_efi_partition(disk)
        elif install_mode == "resize_ntfs":
            resize_partition = body.get("resize_partition") or body.get("target_partition", "")
            resize_gib = _safe_int(body.get("resize_gib") or body.get("shrink_gib") or 0)
            if resize_partition not in {part.get("name") for part in list_partitions(disk)} or resize_gib < 32:
                return {"started": False, "message": "Invalid NTFS resize target."}
            efi_partition = body.get("efi_partition", "") or find_efi_partition(disk)
        elif install_mode == "free_space":
            free_region_start = _safe_int(body.get("free_region_start"), -1)
            free_region_end = _safe_int(body.get("free_region_end"), -1)
            valid_region = any(
                region["start_bytes"] <= free_region_start
                and region["end_bytes"] >= free_region_end
                for region in list_free_space(disk)
            )
            if free_region_start < 0 or free_region_end <= free_region_start or not valid_region:
                return {"started": False, "message": "Invalid free space region."}
            efi_partition = body.get("efi_partition", "") or find_efi_partition(disk)
        elif install_mode == "manual":
            journal = get_journal(self.context)
            if not journal or not journal.committed:
                return {"started": False, "message": "Partition changes must be committed before starting the install."}
            target_partition = journal.root_partition or ""
            if not target_partition:
                return {"started": False, "message": "No root partition (/) configured in the manual partition layout."}
            efi_partition = body.get("efi_partition", "") or find_efi_partition(disk)
        elif disks[disk].get("current") and not _IS_LIVE_SESSION:
            return {
                "started": False,
                "message": "This is the disk running the current KythOS session.\n\nThe running root filesystem cannot be unmounted, so reinstalling to this disk is only supported from the live ISO.",
            }

        state = {
            "disk": disk, "install_mode": install_mode,
            "target_partition": target_partition, "resize_partition": resize_partition,
            "resize_gib": resize_gib, "free_region_start": free_region_start,
            "free_region_end": free_region_end,
        }
        try:
            _validate_storage_intent(state, self.context)
        except RuntimeError as exc:
            return {"started": False, "message": str(exc)}

        current_ok = install_mode == "alongside" or not disks[disk].get("current") or bool(body.get("confirm_current"))
        if not (body.get("confirm_backup") and body.get("confirm_erase") and current_ok):
            return {"started": False, "message": "Please confirm the on-screen acknowledgements before starting the install."}
        try:
            password_hash = _hash_password(body.get("password", ""))
        except Exception as exc:
            return {"started": False, "message": f"Could not hash password: {exc}"}

        timezone = body.get("timezone", "UTC") or "UTC"
        if timezone not in set(list_timezones()):
            timezone = "UTC"
        username = body.get("username", "")
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,30}", username):
            return {"started": False, "message": "Invalid username."}
        hostname = body.get("hostname", "kyth")
        if not re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?", hostname):
            return {"started": False, "message": "Invalid hostname."}

        if not self.context.install_lock.acquire(blocking=False):
            return {"started": False, "message": "An installation is already running."}
        next_state: InstallationState = {
            **state,
            "efi_partition": efi_partition,
            "hostname": hostname,
            "timezone": timezone,
            "username": username,
            "password_hash": password_hash,
            "kernel": body.get("kernel", "fedora") or "fedora",
            "mok_password": body.get("mok_password", "") or "",
        }
        self.context.replace_state(next_state)
        self.context.transition(InstallLifecycle.VALIDATED)

        def worker() -> None:
            try:
                self.context.transition(InstallLifecycle.INSTALLING)
                install._run_install(self.context)
            finally:
                self.context.install_lock.release()

        threading.Thread(target=worker, daemon=True).start()
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
