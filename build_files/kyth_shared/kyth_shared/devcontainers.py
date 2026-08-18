"""Dev containers preset — devcontainers.toml declarative distrobox."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_DEVCONTAINERS_PATH = Path.home() / ".config" / "kyth" / "devcontainers.toml"

def devcontainers_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"devcontainers.toml"
    return DEFAULT_DEVCONTAINERS_PATH

def load_devcontainers(path: Path | None = None) -> dict[str, dict[str, Any]]:
    p=devcontainers_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    out={}
    for name, e in data.get("containers", {}).items() if isinstance(data.get("containers"), dict) else []:
        if not isinstance(e, dict):
            continue
        out[str(name)]={"image": str(e.get("image", "quay.io/toolbx/ubuntu-toolbox:24.04")), "init": bool(e.get("init", False))}
    return out

def save_devcontainers(containers: dict[str, dict[str, Any]], path: Path | None = None) -> Path:
    p=devcontainers_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth devcontainers — distrobox declarative, offline\n"]
    for name in sorted(containers):
        e=containers[name]
        lines.append(f'[containers."{name}"]')
        lines.append(f'image = "{e.get("image","quay.io/toolbx/ubuntu-toolbox:24.04")}"')
        lines.append(f'init = {str(bool(e.get("init", False))).lower()}')
        lines.append("")
    tmp = p.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(p)
    return p
