from __future__ import annotations

from dataclasses import dataclass
from functools import partial
from typing import Callable

from .context import InstallerContext
from .services import InstallerService


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
        "remove_pending",
        "commit_partitions",
        "rollback_partitions",
    }

    # Routes whose handler is just "call the same-named InstallerService
    # method and map ok/not-ok to 200/400" -- see _simple().
    _SIMPLE_ROUTES = (
        "new_table",
        "create_partition",
        "delete_partition",
        "resize_partition",
        "format_partition",
        "set_mountpoint",
        "remove_pending",
    )

    def __init__(self, context: InstallerContext):
        self.context = context
        self.installer_service = InstallerService(self.context)
        self.handlers: dict[str, Callable[[dict], ApiResponse]] = {
            name: partial(self._simple, name) for name in self._SIMPLE_ROUTES
        }
        self.handlers.update({
            "commit_partitions": self.commit_partitions,
            "rollback_partitions": self.rollback_partitions,
            "start": self.start,
            "cancel": self.cancel,
            "reboot": self.reboot,
            "rescue_logs_to_usb": self.rescue_logs_to_usb,
        })

    def dispatch(self, route_name: str, body: dict) -> ApiResponse:
        handler = self.handlers.get(route_name)
        if handler is None:
            return ApiResponse({"ok": False, "message": "Route not found."}, 404)
        with self.context.state_lock:
            if route_name in self._PARTITION_ROUTES and self.context.install_lock.locked():
                return ApiResponse(
                    {"ok": False, "message": "Partition changes are locked while installation is running."},
                    409,
                )
            return handler(body)

    def _simple(self, service_method_name: str, body: dict) -> ApiResponse:
        res = getattr(self.installer_service, service_method_name)(body)
        status = 200 if res.get("ok") else 400
        return ApiResponse(res, status)

    def commit_partitions(self, body: dict) -> ApiResponse:
        res = self.installer_service.commit_partitions(body)
        status = 200 if res.get("ok") else (400 if "errors" in res else 500)
        return ApiResponse(res, status)

    def rollback_partitions(self, body: dict) -> ApiResponse:
        res = self.installer_service.rollback_partitions(body)
        status = 200 if res.get("ok") else 500
        return ApiResponse(res, status)

    def start(self, body: dict) -> ApiResponse:
        res = self.installer_service.start_install(body)
        if res.get("started"):
            return ApiResponse(res, 200)
        message = res.get("message", "")
        if "already running" in message or "running the current KythOS session" in message or "already exists" in message:
            return ApiResponse(res, 409)
        return ApiResponse(res, 400)

    def cancel(self, body: dict) -> ApiResponse:
        res = self.installer_service.cancel_install(body)
        status = 200 if res.get("ok") else 409
        return ApiResponse(res, status)

    def reboot(self, body: dict) -> ApiResponse:
        res = self.installer_service.reboot(body)
        status = 200 if res.get("ok") else 500
        return ApiResponse(res, status)

    def rescue_logs_to_usb(self, body: dict) -> ApiResponse:
        # Body may contain {"usb_mount": "/run/media/liveuser/USB"}
        # Best-effort: find first removable mount under /run/media if not given.
        import os
        from pathlib import Path
        from .config import LOG_FILE, TRANSACTION_FILE, FAILURE_SUMMARY_FILE
        from .runner import run_command
        from .system import _as_root

        target = (body.get("usb_mount") or "").strip()
        if not target:
            # Auto-detect first USB mount
            try:
                candidates = [p for p in Path("/run/media").rglob("*") if p.is_dir()]
                for c in candidates:
                    try:
                        if run_command(["findmnt", "-n", str(c)], capture_output=True, timeout=3).returncode == 0:
                            target = str(c)
                            break
                    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B112 -- best-effort per-item skip, failure here is non-fatal by design
                        continue
            except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
                pass
        if not target or not os.path.isdir(target):
            return ApiResponse({"ok": False, "message": "No USB drive found. Insert a USB stick and try again."}, 400)
        try:
            dest = Path(target) / "kyth-installer-logs"
            run_command(_as_root(["mkdir", "-p", str(dest)]), check=False)
            copied = []
            for src in (LOG_FILE, TRANSACTION_FILE, FAILURE_SUMMARY_FILE):
                if src.is_file() and not src.is_symlink():
                    run_command(_as_root(["cp", "-a", str(src), str(dest / src.name)]), check=False)
                    # Also ensure world-readable on FAT USB
                    run_command(_as_root(["chmod", "644", str(dest / src.name)]), check=False)
                    copied.append(src.name)
            if not copied:
                return ApiResponse({"ok": False, "message": "No installer logs found to copy."}, 500)
            return ApiResponse({"ok": True, "dest": str(dest), "copied": copied}, 200)
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            return ApiResponse({"ok": False, "message": str(exc)}, 500)
