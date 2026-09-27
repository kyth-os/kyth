"""Scaling + ICC — scaling.toml per-output fractional scale with kscreen apply."""
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

DEFAULT_SCALING_PATH = Path.home() / ".config" / "kyth" / "scaling.toml"
_OUTPUT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def scaling_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "kyth" / "scaling.toml"
    return DEFAULT_SCALING_PATH


def load_scaling(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p = scaling_config_path(path)
    try:
        with p.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    raw = data.get("outputs", {})
    if not isinstance(raw, dict):
        return {}
    for conn, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        try:
            scale = float(entry.get("scale", 1.0))
        except (TypeError, ValueError):
            scale = 1.0
        scale = max(1.0, min(3.0, scale))
        icc = str(entry.get("icc", "")) if entry.get("icc") else ""
        out[str(conn)] = {"scale": scale, "icc": icc}
    return out


def save_scaling(outputs: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p = scaling_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kyth scaling per-output\n"]
    for conn in sorted(outputs):
        entry = outputs[conn]
        lines.append(f'[outputs."{conn}"]')
        lines.append(f'scale = {float(entry.get("scale", 1.0))}')
        if entry.get("icc"):
            lines.append(f'icc = "{entry["icc"]}"')
        lines.append("")
    _atomic_write_text(p, "\n".join(lines), encoding="utf-8")
    return p


def kwin_config_for_scaling(outputs: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if outputs is None:
        outputs = load_scaling()
    return {
        "outputs": [
            {"name": name, "scale": entry["scale"], "icc": entry.get("icc", "")}
            for name, entry in outputs.items()
        ]
    }


def apply_scaling(outputs: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Apply scaling.toml via kscreen-doctor. Returns applied notes."""
    if outputs is None:
        outputs = load_scaling()
    if not outputs:
        return []
    if not shutil.which("kscreen-doctor"):
        return ["kscreen-doctor unavailable"]

    listed = run(["kscreen-doctor", "-o"], capture_output=True, timeout=8, check=False)
    if listed.returncode != 0:
        return ["kscreen-doctor -o failed"]
    connected = {
        str(o.get("name") or "")
        for o in parse_kscreen_outputs(listed.stdout or "")
        if o.get("connected") and _OUTPUT_NAME_RE.fullmatch(str(o.get("name") or ""))
    }

    applied: list[str] = []
    for conn, entry in outputs.items():
        if conn not in connected:
            applied.append(f"{conn}: not connected")
            continue
        scale = float(entry.get("scale", 1.0))
        # kscreen-doctor accepts fractional scales like 1.25
        scale_str = f"{scale:.2f}".rstrip("0").rstrip(".")
        res = run(
            ["kscreen-doctor", f"output.{conn}.scale.{scale_str}"],
            capture_output=True,
            timeout=10,
            check=False,
        )
        if res.returncode == 0:
            applied.append(f"{conn}.scale={scale_str}")
        else:
            applied.append(f"{conn}.scale failed")
        icc = str(entry.get("icc") or "").strip()
        if icc and Path(icc).is_file():
            # Best-effort: copy into system kyth ICC dir when writable; otherwise note path.
            dest_dir = Path("/usr/share/color/icc/kyth")
            try:
                if dest_dir.is_dir() and os.access(dest_dir, os.W_OK):
                    dest = dest_dir / Path(icc).name
                    dest.write_bytes(Path(icc).read_bytes())
                    applied.append(f"{conn}.icc={dest}")
                else:
                    applied.append(f"{conn}.icc={icc} (not deployed — needs root icc dir)")
            except OSError as exc:
                applied.append(f"{conn}.icc failed: {exc}")
    try:
        import time

        _atomic_write_text(Path("/run/kyth-scaling-ttl"), str(int(time.time()) + 30), encoding="utf-8")
    except OSError:
        pass
    return applied
