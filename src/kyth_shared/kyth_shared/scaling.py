"""Scaling + ICC — scaling.toml per-output fractional + ICC, offline.

Extends display_hdr EDID path, writes kwinoutputconfig.json + colord ICC deploy.
"""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_SCALING_PATH = Path.home() / ".config" / "kyth" / "scaling.toml"

def scaling_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"scaling.toml"
    return DEFAULT_SCALING_PATH

def load_scaling(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p=scaling_config_path(path)
    try:
        with p.open("rb") as _f:
            data=tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for conn, e in data.get("outputs", {}).items() if isinstance(data.get("outputs"), dict) else []:
        if not isinstance(e, dict):
            continue
        try:
            scale=float(e.get("scale", 1.0))
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            scale=1.0
        scale=max(1.0, min(3.0, scale))
        icc=str(e.get("icc", "")) if e.get("icc") else ""
        out[str(conn)]={"scale": scale, "icc": icc}
    return out

def save_scaling(outputs: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=scaling_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth scaling per-output, offline\n"]
    for conn in sorted(outputs):
        e=outputs[conn]
        lines.append(f'[outputs."{conn}"]')
        lines.append(f'scale = {float(e.get("scale",1.0))}')
        if e.get("icc"):
            lines.append(f'icc = "{e["icc"]}"')
        lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p

def kwin_config_for_scaling(outputs: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    if outputs is None:
        outputs=load_scaling()
    # KWin output config JSON shape simplified
    return {"outputs": [{"name": k, "scale": v["scale"], "icc": v.get("icc","")} for k,v in outputs.items()]}
