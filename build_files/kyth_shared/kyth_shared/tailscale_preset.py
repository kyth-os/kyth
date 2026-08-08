"""Tailscale mesh — tailscale.toml tailnet+exit_node, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_TAILSCALE_PATH = Path.home() / ".config" / "kyth" / "tailscale.toml"

def tailscale_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"tailscale.toml"
    return DEFAULT_TAILSCALE_PATH

def load_tailscale(path: Path | None = None) -> dict[str, Any]:
    p=tailscale_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"tailnet": "", "exit_node": "", "accept_routes": False}
    return {"tailnet": str(data.get("tailnet","")), "exit_node": str(data.get("exit_node","")), "accept_routes": bool(data.get("accept_routes", False))}

def save_tailscale(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=tailscale_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth Tailscale mesh, offline hash-gated\n"]
    lines.append(f'tailnet = "{cfg.get("tailnet","")}"')
    lines.append(f'exit_node = "{cfg.get("exit_node","")}"')
    lines.append(f'accept_routes = {str(bool(cfg.get("accept_routes", False))).lower()}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p
