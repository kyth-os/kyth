"""Update-check helpers (firmware commands + registry re-exports).

Pure API imports without Qt. Worker classes live in ``services.workers.updates``.
"""
from __future__ import annotations

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

