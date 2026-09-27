"""Pure parsers for output produced by host/runtime commands."""
from __future__ import annotations

import json
from typing import Any


def parse_json_object(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def parse_lsblk_devices(raw: str) -> list[dict[str, Any]]:
    data = parse_json_object(raw)
    devices = data.get("blockdevices") if data else None
    return devices if isinstance(devices, list) else []


def parse_ntfs_devices(raw: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(devices: list[dict[str, Any]]) -> None:
        for device in devices:
            fstype = str(device.get("fstype") or "").lower()
            if "ntfs" in fstype:
                found.append(device)
            children = device.get("children")
            if isinstance(children, list):
                walk(children)

    walk(parse_lsblk_devices(raw))
    return found


def parse_findmnt_sources(raw: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in raw.splitlines() if line.strip())


def parse_flatpak_apps(raw: str) -> list[dict[str, str]]:
    apps = []
    for line in raw.splitlines():
        parts = [part.strip() for part in line.split("\t")]
        if len(parts) < 4 or not parts[0]:
            continue
        app_id, name, origin, installation = parts[:4]
        apps.append({
            "kind": "flatpak",
            "app_id": app_id,
            "name": name or app_id,
            "origin": origin or "unknown",
            "installation": installation or "system",
        })
    return apps


def count_fwupd_updates(raw: str) -> int:
    return sum(1 for line in raw.splitlines() if line.strip().startswith("Device ID:"))


def parse_secure_boot_state(raw: str) -> str:
    normalized = raw.strip().lower()
    if "secureboot enabled" in normalized:
        return "enabled"
    if "secureboot disabled" in normalized:
        return "disabled"
    return "unknown"


def parse_systemd_state(raw: str) -> str:
    state = raw.strip().lower()
    return state if state in {"active", "activating", "inactive", "failed", "deactivating"} else "unknown"


def parse_nvidia_smi(raw: str) -> tuple[str, str] | None:
    first = next((line.strip() for line in raw.splitlines() if line.strip()), "")
    if not first:
        return None
    parts = [part.strip() for part in first.split(",", 1)]
    return (parts[0], parts[1]) if len(parts) == 2 and all(parts) else None
