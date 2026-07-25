"""Behavioral handlers for authenticated installer POST routes."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Callable

from . import install
from .config import _IS_LIVE_SESSION
from .context import InstallLifecycle, InstallationState, InstallerContext
from .disk import (
    _normal_device_path,
    _safe_int,
    find_efi_partition,
    list_disks,
    list_free_space,
    list_partitions,
)
from .partition_ops import (
    FILESYSTEM_OPTIONS,
    get_journal,
    init_journal,
    reset_journal,
)
from .plan import _validate_storage_intent
from .runner import run_command
from .system import _as_root, _hash_password, list_timezones


@dataclass(frozen=True)
class ApiResponse:
    payload: object
    status: int = 200


class PostRouteService:
    """Validate and execute POST requests independently of HTTP transport."""

    _PARTITION_ROUTES = {
        "new_table",
        "create_partition",
        "delete_partition",
        "resize_partition",
        "format_partition",
        "set_mountpoint",
        "commit_partitions",
        "rollback_partitions",
    }

    def __init__(self, context: InstallerContext):
        self.context = context
        self.handlers: dict[str, Callable[[dict], ApiResponse]] = {
            "new_table": self.new_table,
            "create_partition": self.create_partition,
            "delete_partition": self.delete_partition,
            "resize_partition": self.resize_partition,
            "format_partition": self.format_partition,
            "set_mountpoint": self.set_mountpoint,
            "commit_partitions": self.commit_partitions,
            "rollback_partitions": self.rollback_partitions,
            "start": self.start,
            "reboot": self.reboot,
        }

    def dispatch(self, route_name: str, body: dict) -> ApiResponse:
        handler = self.handlers.get(route_name)
        if handler is None:
            return ApiResponse({"ok": False, "message": "Route not found."}, 404)
        # POST handlers mutate session state and, for partitioning, a single
        # transaction journal. Serialize them per server session so concurrent
        # browser requests cannot interleave validation and commit operations.
        with self.context.state_lock:
            if route_name in self._PARTITION_ROUTES and self.context.install_lock.locked():
                return ApiResponse(
                    {"ok": False, "message": "Partition changes are locked while installation is running."},
                    409,
                )
            return handler(body)

    def _journal_for(self, body: dict):
        disk = _normal_device_path(body.get("disk", ""))
        if not disk:
            return None, None, ApiResponse({"ok": False, "message": "No disk specified."}, 400)
        journal = get_journal(self.context)
        if not journal or journal.disk != disk:
            return None, None, ApiResponse({
                "ok": False,
                "message": "No active partition journal for this disk. Create a new partition table first.",
            }, 400)
        return disk, journal, None

    def _partition_for(self, body: dict):
        """Resolve (disk, journal, partition) from a request body's "disk"
        and "partition" fields. Returns (None, None, None, error_response)
        if the journal can't be resolved or "partition" is missing."""
        disk, journal, error = self._journal_for(body)
        partition = _normal_device_path(body.get("partition", ""))
        if error or not partition:
            return None, None, None, error or ApiResponse(
                {"ok": False, "message": "Disk and partition are required."}, 400
            )
        return disk, journal, partition, None

    def new_table(self, body: dict) -> ApiResponse:
        disk = _normal_device_path(body.get("disk", ""))
        if not disk:
            return ApiResponse({"ok": False, "message": "No disk specified."}, 400)
        if disk not in {d["name"] for d in list_disks()}:
            return ApiResponse({"ok": False, "message": "Invalid or unsafe disk."}, 400)
        table_type = body.get("table_type", "gpt")
        if table_type not in ("gpt", "msdos"):
            return ApiResponse({"ok": False, "message": "Table type must be 'gpt' or 'msdos'."}, 400)
        journal = init_journal(disk, self.context)
        journal.add_op("new_table", {"table_type": table_type})
        return ApiResponse({"ok": True, "pending": len(journal.ops)})

    def create_partition(self, body: dict) -> ApiResponse:
        _disk, journal, error = self._journal_for(body)
        if error:
            return error
        start = _safe_int(body.get("start_bytes"), -1)
        size = _safe_int(body.get("size_bytes"), -1)
        if start < 0 or size < 1:
            return ApiResponse({"ok": False, "message": "Invalid start offset or size."}, 400)
        fs_type = body.get("fs_type", "btrfs")
        if not any(item["id"] == fs_type for item in FILESYSTEM_OPTIONS):
            return ApiResponse({"ok": False, "message": f"Unsupported filesystem: {fs_type}"}, 400)
        journal.add_op("create", {
            "start_bytes": start,
            "size_bytes": size,
            "fs_type": fs_type,
            "label": body.get("label", ""),
            "mountpoint": body.get("mountpoint", ""),
        })
        errors = journal.validate()
        return ApiResponse({"ok": not errors, "pending": len(journal.ops), "errors": errors})

    def delete_partition(self, body: dict) -> ApiResponse:
        disk, journal, partition, error = self._partition_for(body)
        if error:
            return error
        parts = {part["name"]: part for part in list_partitions(disk)}
        if partition not in parts:
            return ApiResponse({"ok": False, "message": f"Partition {partition} not found."}, 400)
        if parts[partition].get("current") or parts[partition].get("in_use"):
            return ApiResponse({"ok": False, "message": "Cannot delete a mounted or in-use partition."}, 400)
        journal.add_op("delete", {"partition": partition})
        return ApiResponse({"ok": True, "pending": len(journal.ops)})

    def resize_partition(self, body: dict) -> ApiResponse:
        disk, journal, partition, error = self._partition_for(body)
        if error:
            return error
        new_size = _safe_int(body.get("new_size_bytes"), -1)
        if new_size < 1:
            return ApiResponse({"ok": False, "message": "A new size is required."}, 400)
        parts = {part["name"]: part for part in list_partitions(disk)}
        if partition not in parts:
            return ApiResponse({"ok": False, "message": f"Partition {partition} not found."}, 400)
        if new_size >= _safe_int(parts[partition].get("size_bytes")):
            return ApiResponse({"ok": False, "message": "New size must be smaller than current size for resize."}, 400)
        journal.add_op("resize", {"partition": partition, "new_size_bytes": new_size})
        return ApiResponse({"ok": True, "pending": len(journal.ops)})

    def format_partition(self, body: dict) -> ApiResponse:
        _disk, journal, partition, error = self._partition_for(body)
        if error:
            return error
        fs_type = body.get("fs_type", "btrfs")
        if not any(item["id"] == fs_type for item in FILESYSTEM_OPTIONS):
            return ApiResponse({"ok": False, "message": f"Unsupported filesystem: {fs_type}"}, 400)
        journal.add_op("format", {
            "partition": partition, "fs_type": fs_type, "label": body.get("label", ""),
        })
        return ApiResponse({"ok": True, "pending": len(journal.ops)})

    def set_mountpoint(self, body: dict) -> ApiResponse:
        _disk, journal, partition, error = self._partition_for(body)
        if error:
            return error
        mountpoint = body.get("mountpoint", "").strip()
        if mountpoint and not mountpoint.startswith("/"):
            return ApiResponse({"ok": False, "message": "Mount point must be an absolute path (e.g. /, /home)."}, 400)
        journal.add_op("set_mountpoint", {"partition": partition, "mountpoint": mountpoint})
        return ApiResponse({"ok": True, "pending": len(journal.ops)})

    def commit_partitions(self, body: dict) -> ApiResponse:
        _disk, journal, error = self._journal_for(body)
        if error:
            return error
        errors = journal.validate()
        if errors:
            return ApiResponse({"ok": False, "message": "Validation failed.", "errors": errors}, 400)
        try:
            self.context.transition(InstallLifecycle.PARTITIONING)
            root_part = journal.commit(
                lambda msg: self.context.events.publish({"type": "log", "text": f"[partition] {msg}"})
            )
            self.context.transition(InstallLifecycle.IDLE)
            return ApiResponse({"ok": True, "root_partition": root_part})
        except RuntimeError as exc:
            journal.rollback(lambda _msg: None)
            self.context.transition(InstallLifecycle.FAILED)
            return ApiResponse({"ok": False, "message": str(exc)}, 500)

    def rollback_partitions(self, body: dict) -> ApiResponse:
        _disk, journal, error = self._journal_for(body)
        if error:
            return error
        try:
            journal.rollback(lambda _msg: None)
            reset_journal(self.context)
            return ApiResponse({"ok": True})
        except RuntimeError as exc:
            return ApiResponse({"ok": False, "message": str(exc)}, 500)

    def start(self, body: dict) -> ApiResponse:
        disk = body.get("disk", "")
        disks = {item["name"]: item for item in list_disks()}
        if disk not in disks:
            return ApiResponse({"started": False, "message": "Invalid disk."}, 400)

        install_mode = body.get("install_mode", "wipe")
        if install_mode not in ("wipe", "alongside", "resize_ntfs", "free_space", "manual"):
            install_mode = "wipe"
        target_partition = resize_partition = efi_partition = ""
        resize_gib = free_region_start = free_region_end = 0

        if install_mode == "alongside":
            target_partition = body.get("target_partition", "")
            if target_partition not in {part.get("name") for part in list_partitions(disk)}:
                return ApiResponse({"started": False, "message": "Invalid target partition."}, 400)
            efi_partition = body.get("efi_partition", "") or find_efi_partition(disk)
        elif install_mode == "resize_ntfs":
            resize_partition = body.get("resize_partition") or body.get("target_partition", "")
            resize_gib = _safe_int(body.get("resize_gib") or body.get("shrink_gib") or 0)
            if resize_partition not in {part.get("name") for part in list_partitions(disk)} or resize_gib < 32:
                return ApiResponse({"started": False, "message": "Invalid NTFS resize target."}, 400)
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
                return ApiResponse({"started": False, "message": "Invalid free space region."}, 400)
            efi_partition = body.get("efi_partition", "") or find_efi_partition(disk)
        elif install_mode == "manual":
            journal = get_journal(self.context)
            if not journal or not journal.committed:
                return ApiResponse({"started": False, "message": "Partition changes must be committed before starting the install."}, 400)
            target_partition = journal.root_partition or ""
            if not target_partition:
                return ApiResponse({"started": False, "message": "No root partition (/) configured in the manual partition layout."}, 400)
            efi_partition = body.get("efi_partition", "") or find_efi_partition(disk)
        elif disks[disk].get("current") and not _IS_LIVE_SESSION:
            return ApiResponse({
                "started": False,
                "message": "This is the disk running the current KythOS session.\n\nThe running root filesystem cannot be unmounted, so reinstalling to this disk is only supported from the live ISO.",
            }, 409)

        state = {
            "disk": disk, "install_mode": install_mode,
            "target_partition": target_partition, "resize_partition": resize_partition,
            "resize_gib": resize_gib, "free_region_start": free_region_start,
            "free_region_end": free_region_end,
        }
        try:
            _validate_storage_intent(state, self.context)
        except RuntimeError as exc:
            return ApiResponse({"started": False, "message": str(exc)}, 409)

        current_ok = install_mode == "alongside" or not disks[disk].get("current") or bool(body.get("confirm_current"))
        if not (body.get("confirm_backup") and body.get("confirm_erase") and current_ok):
            return ApiResponse({"started": False, "message": "Please confirm the on-screen acknowledgements before starting the install."}, 400)
        try:
            password_hash = _hash_password(body.get("password", ""))
        except Exception as exc:
            return ApiResponse({"started": False, "message": f"Could not hash password: {exc}"}, 500)

        timezone = body.get("timezone", "UTC") or "UTC"
        if timezone not in set(list_timezones()):
            timezone = "UTC"
        username = body.get("username", "")
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,30}", username):
            return ApiResponse({"started": False, "message": "Invalid username."}, 400)
        hostname = body.get("hostname", "kyth")
        if not re.fullmatch(r"[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?", hostname):
            return ApiResponse({"started": False, "message": "Invalid hostname."}, 400)

        if not self.context.install_lock.acquire(blocking=False):
            return ApiResponse({"started": False, "message": "An installation is already running."}, 409)
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
        return ApiResponse({"started": True})

    def reboot(self, _body: dict) -> ApiResponse:
        result = run_command(
            _as_root(["systemctl", "reboot"]),
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return ApiResponse({"ok": False, "error": result.stderr.strip() or "reboot command failed"}, 500)
        return ApiResponse({"ok": True})
