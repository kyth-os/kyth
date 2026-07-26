"""Update-check helpers (firmware commands + registry re-exports).

Pure API imports without Qt. Worker classes live in ``services.workers.updates``.
"""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Callable

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
