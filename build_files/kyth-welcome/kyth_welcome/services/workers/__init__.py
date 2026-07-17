"""Qt worker adapters for domain services.

Domain modules under ``services/`` stay pure (no Qt). UI pages import workers
from here, or via lazy re-exports on the domain modules for compatibility.
"""
from __future__ import annotations

__all__ = [
    "ChangelogWorker",
    "FirmwareCheckWorker",
    "FlatpakCheckWorker",
    "HardwareProbeWorker",
    "RcloneAuthorizeWorker",
    "RcloneSyncWorker",
    "SteamCopyWorker",
    "UpdateCheckWorker",
    "UserFilesCopyWorker",
    "VpnConnectWorker",
    "WindowsLibraryWorker",
    "_ProtonDbBatchWorker",
    "_VpnConnectWorker",
]


def __getattr__(name: str):
    if name in {"VpnConnectWorker", "_VpnConnectWorker"}:
        from .vpn import VpnConnectWorker
        return VpnConnectWorker
    if name in {
        "SteamCopyWorker",
        "RcloneAuthorizeWorker",
        "RcloneSyncWorker",
    }:
        from . import cloud_sync as m
        return getattr(m, name)
    if name in {
        "UpdateCheckWorker",
        "FirmwareCheckWorker",
        "ChangelogWorker",
        "FlatpakCheckWorker",
    }:
        from . import updates as m
        return getattr(m, name)
    if name == "HardwareProbeWorker":
        from .hardware import HardwareProbeWorker
        return HardwareProbeWorker
    if name in {"WindowsLibraryWorker", "UserFilesCopyWorker"}:
        from . import windows_migration as m
        return getattr(m, name)
    if name == "_ProtonDbBatchWorker":
        from .protondb import ProtonDbBatchWorker
        return ProtonDbBatchWorker
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
