"""VRR + Night color — vrr.toml per-output store with KWin apply path.

VRR is applied per-output via ``kscreen-doctor`` (``output.<name>.vrrpolicy.*``)
so unlisted panels keep the compositor default. The global ``[Wayland]
VrrPolicy`` default (Automatic) is owned by the image sysconfig fragment, not
by this per-user tool. NightColor is only touched when the user explicitly
enables it in vrr.toml — the mode selector is never forced, so a user's
location-based schedule is left alone.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tomllib
from pathlib import Path
from typing import Any

from kyth_shared.atomic_io import atomic_write_text as _atomic_write_text
from kyth_shared.commands import run
from kyth_shared.guardian_actions import parse_kscreen_outputs

logger = logging.getLogger(__name__)

DEFAULT_VRR_PATH = Path.home() / ".config" / "kyth" / "vrr.toml"
_OUTPUT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")

_VRR_TO_POLICY = {"never": "0", "adaptive": "1", "always": "2"}
_POLICY_TO_VRR = {v: k for k, v in _VRR_TO_POLICY.items()}


def vrr_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "kyth" / "vrr.toml"
    return DEFAULT_VRR_PATH


def load_vrr(path: Path | None = None) -> dict[str, Any]:
    p = vrr_config_path(path)
    try:
        with p.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {"outputs": {}, "night": {"enabled": False, "temperature": 4500}}
    outs: dict[str, dict[str, str]] = {}
    raw_outs = data.get("outputs", {})
    if isinstance(raw_outs, dict):
        for conn, entry in raw_outs.items():
            if not isinstance(entry, dict):
                continue
            vrr = str(entry.get("vrr", "adaptive"))
            if vrr not in _VRR_TO_POLICY:
                vrr = "adaptive"
            outs[str(conn)] = {"vrr": vrr}
    night = data.get("night", {})
    if not isinstance(night, dict):
        night = {}
    enabled = bool(night.get("enabled", False))
    try:
        temp = int(night.get("temperature", 4500))
    except (TypeError, ValueError):
        temp = 4500
    temp = max(2000, min(6500, temp))
    return {"outputs": outs, "night": {"enabled": enabled, "temperature": temp}}


def save_vrr(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = vrr_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kyth VRR + night color\n"]
    for conn in sorted(cfg.get("outputs", {})):
        lines.append(f'[outputs."{conn}"]')
        lines.append(f'vrr = "{cfg["outputs"][conn].get("vrr", "adaptive")}"')
        lines.append("")
    night = cfg.get("night", {})
    lines.append("[night]")
    lines.append(f'enabled = {str(bool(night.get("enabled", False))).lower()}')
    lines.append(f'temperature = {int(night.get("temperature", 4500))}')
    _atomic_write_text(p, "\n".join(lines) + "\n", encoding="utf-8")
    return p


def _kwriteconfig_bin() -> str | None:
    return shutil.which("kwriteconfig6") or shutil.which("kwriteconfig5") or shutil.which("kwriteconfig")


def _reconfigure_kwin() -> None:
    for name in ("qdbus6", "qdbus-qt6", "qdbus"):
        if not shutil.which(name):
            continue
        try:
            run(
                [name, "org.kde.KWin", "/KWin", "reconfigure"],
                capture_output=True,
                timeout=5,
                check=False,
            )
            return
        except (OSError, ValueError):
            logger.debug("kwin reconfigure via %s failed", name, exc_info=True)


def _write_kwin_key(group: str, key: str, value: str, *, value_type: str | None = None) -> bool:
    bin_name = _kwriteconfig_bin()
    if not bin_name:
        return False
    args = [bin_name, "--file", "kwinrc", "--group", group, "--key", key]
    if value_type:
        args.extend(["--type", value_type])
    args.append(value)
    try:
        res = run(args, capture_output=True, timeout=5, check=False)
        return res.returncode == 0
    except (OSError, ValueError):
        return False


def _apply_per_output_vrr(outputs: dict[str, dict[str, str]]) -> list[str]:
    if not outputs:
        return ["no per-output VRR entries"]
    if not shutil.which("kscreen-doctor"):
        return ["kscreen-doctor unavailable: per-output VRR not applied"]
    listed = run(["kscreen-doctor", "-o"], capture_output=True, timeout=8, check=False)
    if listed.returncode != 0:
        return ["kscreen-doctor -o failed"]
    connected = {
        str(o.get("name") or "")
        for o in parse_kscreen_outputs(listed.stdout or "")
        if o.get("connected") and _OUTPUT_NAME_RE.fullmatch(str(o.get("name") or ""))
    }
    notes: list[str] = []
    # kscreen-doctor uses vrrpolicy.never|always|automatic
    doctor_map = {"never": "never", "always": "always", "adaptive": "automatic"}
    for conn, entry in outputs.items():
        if conn not in connected:
            notes.append(f"{conn}: not connected")
            continue
        mode = doctor_map.get(entry.get("vrr", "adaptive"), "automatic")
        res = run(
            ["kscreen-doctor", f"output.{conn}.vrrpolicy.{mode}"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if res.returncode == 0:
            notes.append(f"{conn}.vrrpolicy.{mode}")
        else:
            notes.append(f"{conn}.vrrpolicy failed")
    return notes


def apply_vrr(cfg: dict[str, Any] | None = None) -> list[str]:
    """Apply vrr.toml per-output VRR + opt-in NightColor. Returns applied notes."""
    if cfg is None:
        cfg = load_vrr()
    applied: list[str] = []
    outputs = cfg.get("outputs") or {}

    # Per-output VRR only: no global Wayland VrrPolicy write. The system-wide
    # Automatic default lives in /etc/xdg/kwinrc (image sysconfig); writing it
    # from here would stomp multi-monitor setups where panels disagree.
    applied.extend(_apply_per_output_vrr(outputs))

    # NightColor is opt-in only: with enabled=false (the default) leave the
    # user's Active/Mode/Temperature exactly as they are. In particular never
    # force Mode (constant-temperature) over a location-based schedule.
    night = cfg.get("night") or {}
    if bool(night.get("enabled", False)):
        try:
            temp = int(night.get("temperature", 4500))
        except (TypeError, ValueError):
            temp = 4500
        temp = max(2000, min(6500, temp))
        if _write_kwin_key("NightColor", "Active", "true", value_type="bool"):
            applied.append("NightColor.Active=True")
        if _write_kwin_key("NightColor", "NightTemperature", str(temp)):
            applied.append(f"NightColor.NightTemperature={temp}")

    _reconfigure_kwin()
    try:
        import time

        _atomic_write_text(Path("/run/kyth-vrr-ttl"), str(int(time.time()) + 30), encoding="utf-8")
    except OSError:
        pass
    return applied
