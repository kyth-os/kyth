"""Flatpak permission presets — flatpak-overrides.toml declarative.

Offline, hash-gated. Persists to ~/.config/kyth/flatpak-overrides.toml like
preset.toml/gaming-per-game.toml. Generates `flatpak override --user` idempotently.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_OVERRIDES_PATH = Path.home() / ".config" / "kyth" / "flatpak-overrides.toml"


def overrides_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "kyth" / "flatpak-overrides.toml"
    return DEFAULT_OVERRIDES_PATH


def load_overrides(path: Path | None = None) -> dict[str, dict[str, Any]]:
    cfg_path = overrides_path(path)
    try:
        data = tomllib.load(cfg_path.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    raw = data.get("overrides", {})
    if not isinstance(raw, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for appid, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        # Keep only known keys, normalize
        filesys = entry.get("filesystem", "")
        sockets = entry.get("sockets", "")
        devices = entry.get("devices", "")
        out[str(appid)] = {
            "filesystem": str(filesys) if filesys else "",
            "sockets": str(sockets) if sockets else "",
            "devices": str(devices) if devices else "",
        }
    return out


def save_overrides(overrides: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    cfg_path = overrides_path(path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kyth flatpak overrides — offline declarative\n"]
    for appid in sorted(overrides):
        e = overrides[appid]
        lines.append(f'[overrides."{appid}"]')
        if e.get("filesystem"):
            lines.append(f'filesystem = "{e["filesystem"]}"')
        if e.get("sockets"):
            lines.append(f'sockets = "{e["sockets"]}"')
        if e.get("devices"):
            lines.append(f'devices = "{e["devices"]}"')
        lines.append("")
    cfg_path.write_text("\n".join(lines), encoding="utf-8")
    return cfg_path


def get_override(appid: str, path: Path | None = None) -> dict[str, Any]:
    return load_overrides(path).get(appid, {"filesystem": "", "sockets": "", "devices": ""})


def set_override(appid: str, filesystem: str = "", sockets: str = "", devices: str = "", path: Path | None = None) -> Path:
    cfg = load_overrides(path)
    cfg[str(appid)] = {"filesystem": filesystem, "sockets": sockets, "devices": devices}
    return save_overrides(cfg, path)


def flatpak_override_args(appid: str, entry: dict[str, Any]) -> list[str]:
    args: list[str] = []
    if entry.get("filesystem"):
        args += [f"--filesystem={entry['filesystem']}"]
    if entry.get("sockets"):
        for s in str(entry["sockets"]).split(";"):
            s = s.strip()
            if s:
                args += [f"--socket={s}"]
    if entry.get("devices"):
        for d in str(entry["devices"]).split(";"):
            d = d.strip()
            if d:
                args += [f"--device={d}"]
    return args
