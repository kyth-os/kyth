"""Update-check helpers (firmware commands + registry re-exports).

Pure API imports without Qt. Worker classes live in ``services.workers.updates``.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable
import time

from kyth_shared.system.bootc_policy import cancel_block_reason, parse_update_phase

_bootc_cancel_block_reason = cancel_block_reason
_parse_update_phase = parse_update_phase

# pylint: disable=unused-import
from .registry import (  # noqa: F401 — re-export pure API for existing imports
    InspectRunner,
    UpdateCheckResult,
    booted_image_digest,
    check_registry_update,
    default_inspect_runner,
    nested_get,
    remote_digest_and_timestamp,
)
# pylint: enable=unused-import


def firmware_check_commands(refresh: bool = True) -> list[list[str]]:
    commands: list[list[str]] = []
    if refresh:
        commands.append(["fwupdmgr", "refresh"])
    commands.append(["fwupdmgr", "get-updates"])
    return commands


@dataclass(frozen=True)
class UpdateOperation:
    mode: str
    label: str
    command: tuple[str, ...]
    inhibit_reason: str


def full_update_operation() -> UpdateOperation:
    return UpdateOperation(
        "full-update",
        "Running KythOS full system update…",
        ("/usr/bin/kyth-full-update",),
        "KythOS is running a full system update",
    )


def image_update_operation(command_factory: Callable[[], list[str]]) -> UpdateOperation:
    return UpdateOperation(
        "update",
        "Downloading the next KythOS OS image…",
        tuple(command_factory()),
        "KythOS is downloading a system update",
    )


def rollback_operation(command_factory: Callable[[], list[str]]) -> UpdateOperation:
    return UpdateOperation(
        "rollback",
        "Staging the previous deployment for next boot…",
        tuple(command_factory()),
        "KythOS is staging a system rollback",
    )


def failed_operation_label(mode: str) -> str:
    return {
        "full-update": "full update",
        "update": "bootc upgrade",
        "rollback": "bootc rollback",
        "switch": "bootc switch",
        "firmware": "fwupdmgr upgrade",
    }.get(mode, "operation")


@dataclass
class UpdateOperationController:
    """UI-independent state machine for a running update operation."""

    mode: str = ""
    phase: str = ""
    started_at: float = 0.0
    last_output_at: float = 0.0
    downloaded: int = 0
    total: int = 0
    final_download_bytes: int = 0
    speed_bps: int = 0
    eta_seconds: int = 0
    low_speed_ticks: int = 0
    staging_write_start: int = 0
    cancel_block_reason: str = ""

    def start(self, mode: str, now: float | None = None) -> None:
        timestamp = time.monotonic() if now is None else now
        self.mode = mode
        self.phase = ""
        self.started_at = timestamp
        self.last_output_at = timestamp
        self.downloaded = 0
        self.total = 0
        self.final_download_bytes = 0
        self.speed_bps = 0
        self.eta_seconds = 0
        self.low_speed_ticks = 0
        self.staging_write_start = 0
        self.cancel_block_reason = ""

    def receive_line(self, text: str, now: float | None = None) -> str:
        self.last_output_at = time.monotonic() if now is None else now
        phase = _parse_update_phase(text.strip(), self.mode)
        if phase:
            self.set_phase(phase)
        return phase

    def set_phase(self, phase: str) -> None:
        self.phase = phase
        reason = _bootc_cancel_block_reason(self.mode, phase)
        if reason:
            self.cancel_block_reason = reason

    @property
    def cancellation_blocked(self) -> bool:
        return bool(self.cancel_block_reason)

    def update_download(
        self,
        downloaded: int,
        total: int,
        speed_bps: int,
        eta_seconds: int,
        *,
        proxy_running: bool,
    ) -> str:
        self.downloaded = downloaded
        self.total = total
        self.speed_bps = speed_bps
        self.eta_seconds = eta_seconds
        self.low_speed_ticks = self.low_speed_ticks + 1 if speed_bps <= 100_000 else 0
        if self.low_speed_ticks >= 10 and downloaded > 0 and not proxy_running:
            self.final_download_bytes = downloaded
            self.set_phase("Download complete — processing image layers…")
            return "complete"
        if speed_bps > 100_000 and downloaded < total:
            self.set_phase("Downloading image layers…")
        return "active"

    def heartbeat_phase(self, now: float | None = None) -> str:
        timestamp = time.monotonic() if now is None else now
        if (
            self.phase == "Downloading image layers…"
            and self.last_output_at
            and timestamp - self.last_output_at > 10
        ):
            self.set_phase("Processing image layers…")
        return self.phase

    def elapsed(self, now: float | None = None) -> int:
        if not self.started_at:
            return 0
        timestamp = time.monotonic() if now is None else now
        return max(0, int(timestamp - self.started_at))
