"""Network identity — single view for VPN / SMB / cloud (R8-4).

The transitional Python service package historically gave separate ownership
of VPN, network-share, and cloud-sync state. The supported Tauri/Rust Hub now
uses one native read boundary instead of asking three places whether “am I
connected for work”.

This module is the single Hub import that merges those three into one
`NetworkIdentity` via the unified ProbeService, so the Hub can render one
banner (VPN connected / SMB mounted / cloud synced) without triple `lspci`
or triple `rclone config` spawns. Write paths stay in the existing
services — this is read/merge only.
"""

from __future__ import annotations
import logging

import json
from dataclasses import dataclass
from pathlib import Path

from kyth_shared.system.probe import probe_cached

logger = logging.getLogger(__name__)

_VPN_STATUS_TTL = 30.0
_SMB_STATUS_TTL = 30.0
_CLOUD_STATUS_TTL = 30.0


@dataclass(frozen=True, slots=True)
class NetworkIdentity:
    vpn_connected: bool = False
    vpn_name: str = ""
    smb_mounts: int = 0
    cloud_providers: tuple[str, ...] = ()
    detail: str = ""


def _vpn_status() -> tuple[bool, str]:
    # Lightweight: parse `nmcli connection show --active` if available,
    # otherwise fall back to `ip route` / `wg show` heuristics.
    # Keep no Qt here — caller runs this in a ProbeService fetch.
    try:
        from kyth_shared.commands import run_text

        res = run_text(["nmcli", "connection", "show", "--active"], timeout=5)
        if res and res.stdout:
            for line in res.stdout.splitlines():
                low = line.lower()
                if "vpn" in low or "wireguard" in low or "globalprotect" in low:
                    name = line.split()[0] if line.split() else "VPN"
                    return True, name
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass
    return False, ""


def _smb_mounts() -> int:
    try:
        text = Path("/proc/mounts").read_text(encoding="utf-8", errors="ignore")
        return sum(1 for line in text.splitlines() if " cifs " in line)
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        return 0


def _cloud_providers() -> tuple[str, ...]:
    cfg = Path.home() / ".config" / "kyth-cloud-sync.json"
    providers: list[str] = []
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
        if isinstance(data.get("onedrive"), dict):
            providers.append("onedrive")
        if isinstance(data.get("gdrive"), dict):
            providers.append("gdrive")
        if isinstance(data.get("dropbox"), dict):
            providers.append("dropbox")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass
    return tuple(providers)


def get_network_identity() -> NetworkIdentity:
    def _fetch() -> NetworkIdentity:
        vpn_connected, vpn_name = _vpn_status()
        smb = _smb_mounts()
        providers = _cloud_providers()
        detail_parts = []
        if vpn_connected:
            detail_parts.append(f"VPN {vpn_name} connected")
        if smb:
            detail_parts.append(f"{smb} SMB mount(s)")
        if providers:
            detail_parts.append(f"cloud: {', '.join(providers)}")
        return NetworkIdentity(
            vpn_connected=vpn_connected,
            vpn_name=vpn_name,
            smb_mounts=smb,
            cloud_providers=providers,
            detail="; ".join(detail_parts) or "No active work network",
        )

    # Memory-only key: the typed NetworkIdentity cannot round-trip through the
    # JSON cache file, so the disk-backed projection lives under
    # DISK_TTL["network-summary"] and this 60s memo mirrors its age.
    return probe_cached("network-identity", 60.0, _fetch)
