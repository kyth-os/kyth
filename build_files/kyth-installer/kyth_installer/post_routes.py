from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .context import InstallerContext


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
        from .services import InstallerService
        self.installer_service = InstallerService(self.context)
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
        with self.context.state_lock:
            if route_name in self._PARTITION_ROUTES and self.context.install_lock.locked():
                return ApiResponse(
                    {"ok": False, "message": "Partition changes are locked while installation is running."},
                    409,
                )
            return handler(body)

    def new_table(self, body: dict) -> ApiResponse:
        res = self.installer_service.new_table(body)
        status = 200 if res.get("ok") else 400
        return ApiResponse(res, status)

    def create_partition(self, body: dict) -> ApiResponse:
        res = self.installer_service.create_partition(body)
        status = 200 if res.get("ok") else 400
        return ApiResponse(res, status)

    def delete_partition(self, body: dict) -> ApiResponse:
        res = self.installer_service.delete_partition(body)
        status = 200 if res.get("ok") else 400
        return ApiResponse(res, status)

    def resize_partition(self, body: dict) -> ApiResponse:
        res = self.installer_service.resize_partition(body)
        status = 200 if res.get("ok") else 400
        return ApiResponse(res, status)

    def format_partition(self, body: dict) -> ApiResponse:
        res = self.installer_service.format_partition(body)
        status = 200 if res.get("ok") else 400
        return ApiResponse(res, status)

    def set_mountpoint(self, body: dict) -> ApiResponse:
        res = self.installer_service.set_mountpoint(body)
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

    def reboot(self, body: dict) -> ApiResponse:
        res = self.installer_service.reboot(body)
        status = 200 if res.get("ok") else 500
        return ApiResponse(res, status)
