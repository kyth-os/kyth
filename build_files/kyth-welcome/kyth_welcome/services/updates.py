"""Update-check helpers (firmware commands + registry re-exports).

Pure API imports without Qt. Worker classes live in ``services.workers.updates``.
"""
from __future__ import annotations

from .bootc import REGISTRY, _bootc_image_digest, _bootc_status_data, _current_branch
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


# Re-export bootc symbols that pages historically imported via updates
_bootc_image_digest = _bootc_image_digest
_current_branch = _current_branch
REGISTRY = REGISTRY
_bootc_status_data = _bootc_status_data


def __getattr__(name: str):
    if name in {
        "UpdateCheckWorker",
        "FirmwareCheckWorker",
        "ChangelogWorker",
        "FlatpakCheckWorker",
    }:
        from .workers import updates as m
        return getattr(m, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
