"""Owned runtime state for one installer server session."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from typing import TypedDict

if TYPE_CHECKING:
    from .partition_ops import Journal


class InstallationState(TypedDict, total=False):
    disk: str
    install_mode: str
    target_partition: str
    resize_partition: str
    resize_gib: int
    free_region_start: int
    free_region_end: int
    efi_partition: str
    hostname: str
    timezone: str
    username: str
    password_hash: str
    kernel: str
    mok_password: str


class InstallLifecycle(str, Enum):
    IDLE = "idle"
    VALIDATED = "validated"
    PARTITIONING = "partitioning"
    INSTALLING = "installing"
    DONE = "done"
    FAILED = "failed"


def default_installation_state() -> InstallationState:
    return InstallationState(
        disk="",
        install_mode="wipe",
        target_partition="",
        efi_partition="",
        hostname="kyth",
        timezone="UTC",
        username="",
        password_hash="",
        kernel="fedora",
        mok_password="",
    )


@dataclass
class EventBroker:
    events: list[dict] = field(default_factory=list)
    condition: threading.Condition = field(
        default_factory=lambda: threading.Condition(threading.Lock())
    )

    def publish(self, event: dict) -> None:
        with self.condition:
            self.events.append(event)
            self.condition.notify_all()

    def clear(self) -> None:
        with self.condition:
            self.events.clear()


@dataclass
class InstallerContext:
    state: InstallationState = field(default_factory=default_installation_state)
    events: EventBroker = field(default_factory=EventBroker)
    install_lock: threading.Lock = field(default_factory=threading.Lock)
    state_lock: threading.RLock = field(default_factory=threading.RLock)
    journal: "Journal | None" = None
    lifecycle: InstallLifecycle = InstallLifecycle.IDLE

    def transition(self, lifecycle: InstallLifecycle) -> None:
        with self.state_lock:
            self.lifecycle = lifecycle

    def replace_state(self, state: InstallationState) -> None:
        with self.state_lock:
            self.state = state
