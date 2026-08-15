"""Owned runtime state for one installer server session."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING
from typing import TypedDict

from .mount_registry import MountRegistry

if TYPE_CHECKING:
    from .partition_ops import Journal
    from .plan import ResolvedInstallPlan


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
    locale: str
    keymap: str
    username: str
    password_hash: str
    kernel: str
    mok_password: str


@dataclass(frozen=True)
class InstallRequest:
    """Validated, immutable input for one installation attempt.

    ``InstallationState`` remains as the HTTP/compatibility representation,
    but destructive installer phases consume this object so request fields
    cannot be added, removed, or rewritten while an install is running.
    """

    disk: str = ""
    install_mode: str = "wipe"
    target_partition: str = ""
    resize_partition: str = ""
    resize_gib: int = 0
    free_region_start: int = 0
    free_region_end: int = 0
    efi_partition: str = ""
    hostname: str = "kyth"
    timezone: str = "UTC"
    locale: str = "en_US.UTF-8"
    keymap: str = "us"
    username: str = ""
    password_hash: str = ""
    kernel: str = "fedora"
    mok_password: str = ""

    @classmethod
    def from_state(cls, state: InstallationState | dict) -> "InstallRequest":
        defaults = default_installation_state()
        values = {key: state.get(key, default) for key, default in defaults.items()}
        return cls(**values)

    def as_state(self) -> InstallationState:
        return InstallationState(
            disk=self.disk,
            install_mode=self.install_mode,
            target_partition=self.target_partition,
            resize_partition=self.resize_partition,
            resize_gib=self.resize_gib,
            free_region_start=self.free_region_start,
            free_region_end=self.free_region_end,
            efi_partition=self.efi_partition,
            hostname=self.hostname,
            timezone=self.timezone,
            locale=self.locale,
            keymap=self.keymap,
            username=self.username,
            password_hash=self.password_hash,
            kernel=self.kernel,
            mok_password=self.mok_password,
        )

    def __getitem__(self, key: str):
        """Provide read-only compatibility for callers migrating from dict state."""
        if key not in self.__dataclass_fields__:
            raise KeyError(key)
        return getattr(self, key)

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def without_secrets(self) -> "InstallRequest":
        from dataclasses import replace

        return replace(self, password_hash="", mok_password="")


class InstallLifecycle(str, Enum):
    IDLE = "idle"
    VALIDATED = "validated"
    PARTITIONING = "partitioning"
    INSTALLING = "installing"
    DONE = "done"
    FAILED = "failed"


class InstallPhase(str, Enum):
    PREPARE = "prepare"
    STORAGE = "storage"
    IMAGE = "image"
    CONFIGURE = "configure"
    SECURE_BOOT = "secure_boot"
    COMPLETE = "complete"


_LIFECYCLE_TRANSITIONS: dict[InstallLifecycle, frozenset[InstallLifecycle]] = {
    InstallLifecycle.IDLE: frozenset({
        InstallLifecycle.VALIDATED,
        InstallLifecycle.PARTITIONING,
        InstallLifecycle.FAILED,
    }),
    InstallLifecycle.VALIDATED: frozenset({InstallLifecycle.INSTALLING, InstallLifecycle.FAILED}),
    InstallLifecycle.PARTITIONING: frozenset({InstallLifecycle.IDLE, InstallLifecycle.FAILED}),
    InstallLifecycle.INSTALLING: frozenset({InstallLifecycle.DONE, InstallLifecycle.FAILED}),
    InstallLifecycle.DONE: frozenset(),
    InstallLifecycle.FAILED: frozenset(),
}

_PHASE_ORDER = {
    InstallPhase.PREPARE: 0,
    InstallPhase.STORAGE: 1,
    InstallPhase.IMAGE: 2,
    InstallPhase.CONFIGURE: 3,
    InstallPhase.SECURE_BOOT: 4,
    InstallPhase.COMPLETE: 5,
}


def default_installation_state() -> InstallationState:
    return InstallationState(
        disk="",
        install_mode="wipe",
        target_partition="",
        efi_partition="",
        hostname="kyth",
        timezone="UTC",
        locale="en_US.UTF-8",
        keymap="us",
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
    request: InstallRequest | None = None
    plan: "ResolvedInstallPlan | None" = None
    events: EventBroker = field(default_factory=EventBroker)
    install_lock: threading.Lock = field(default_factory=threading.Lock)
    state_lock: threading.RLock = field(default_factory=threading.RLock)
    journal: "Journal | None" = None
    lifecycle: InstallLifecycle = InstallLifecycle.IDLE
    phase: InstallPhase = InstallPhase.PREPARE
    cleanup_mounts: list[str] = field(default_factory=list)
    mount_registry: MountRegistry = field(default_factory=MountRegistry)
    transaction_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    assurance_checks: list[dict[str, str]] = field(default_factory=list)
    # Destructive partition steps, appended as they start and again as they
    # finish. This is the only record of how far a wipe got if the machine
    # loses power mid-commit: the coarse transaction statuses jump straight
    # from "prepared" to "image_installed" across the whole storage phase.
    partition_steps: list[dict[str, str]] = field(default_factory=list)
    cancel_requested: threading.Event = field(default_factory=threading.Event)

    def transition(self, lifecycle: InstallLifecycle) -> None:
        with self.state_lock:
            if lifecycle == self.lifecycle:
                return
            allowed = _LIFECYCLE_TRANSITIONS[self.lifecycle]
            if lifecycle not in allowed:
                raise RuntimeError(
                    f"Invalid installer lifecycle transition: {self.lifecycle.value} -> {lifecycle.value}"
                )
            self.lifecycle = lifecycle

    def replace_state(self, state: InstallationState) -> None:
        self.replace_request(InstallRequest.from_state(state))

    def replace_request(self, request: InstallRequest) -> None:
        with self.state_lock:
            if self.lifecycle in (InstallLifecycle.DONE, InstallLifecycle.FAILED):
                self.lifecycle = InstallLifecycle.IDLE
                self.transaction_id = uuid.uuid4().hex
                self.assurance_checks.clear()
                self.partition_steps.clear()
            self.request = request
            self.state = request.as_state()
            self.plan = None
            self.phase = InstallPhase.PREPARE
            self.cancel_requested.clear()

    def clear_secrets(self) -> None:
        with self.state_lock:
            if self.request is not None:
                self.request = self.request.without_secrets()
            self.state["password_hash"] = ""
            self.state["mok_password"] = ""

    def set_plan(self, plan: "ResolvedInstallPlan") -> None:
        with self.state_lock:
            self.plan = plan

    def enter_phase(self, phase: InstallPhase) -> None:
        with self.state_lock:
            # IDLE is allowed for focused phase unit tests and recovery tools
            # that invoke a phase helper directly. A live transaction must be
            # in INSTALLING before it can advance phases.
            if self.lifecycle not in (
                InstallLifecycle.IDLE,
                InstallLifecycle.INSTALLING,
                InstallLifecycle.FAILED,
            ):
                raise RuntimeError(
                    f"Cannot enter installer phase {phase.value} while lifecycle is {self.lifecycle.value}"
                )
            if _PHASE_ORDER[phase] < _PHASE_ORDER[self.phase]:
                raise RuntimeError(
                    f"Installer phase cannot move backwards: {self.phase.value} -> {phase.value}"
                )
            self.phase = phase
            # Publish phase as first-class SSE event (R-05) — keep pct for bar, phase for label
            try:
                self.events.publish({"type": "phase", "phase": phase.value})
            except Exception:
                pass

    def record_partition_step(self, kind: str, status: str, target: str = "") -> dict[str, str]:
        """Append one destructive partition step and return the record."""
        with self.state_lock:
            step = {
                "index": str(len(self.partition_steps)),
                "kind": kind,
                "status": status,
                "target": target,
            }
            self.partition_steps.append(step)
            return step

    def register_mount(self, mountpoint: str) -> None:
        with self.state_lock:
            if mountpoint not in self.cleanup_mounts:
                self.cleanup_mounts.append(mountpoint)
            self.mount_registry.register(mountpoint)

    def release_mount(self, mountpoint: str) -> None:
        with self.state_lock:
            if mountpoint in self.cleanup_mounts:
                self.cleanup_mounts.remove(mountpoint)
            self.mount_registry.release(mountpoint)
