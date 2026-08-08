"""Driver helper — driver.toml gpu driver, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_DRIVER_PATH = Path("/etc/kyth/driver.toml")

def driver_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"driver.toml"
    return DEFAULT_DRIVER_PATH

def load_driver(path: Path | None = None) -> dict[str, str]:
    p=driver_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"gpu": "auto", "mesa_git": "off"}
    gpu=str(data.get("gpu","auto"))
    if gpu not in ("auto","nvidia","open","amd"):
        gpu="auto"
    mesa=str(data.get("mesa_git","off"))
    if mesa not in ("on","off"):
        mesa="off"
    return {"gpu": gpu, "mesa_git": mesa}

def save_driver(cfg: dict[str, str], path: Path | None = None) -> Path:
    p=driver_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth driver helper\n"]
    lines.append(f'gpu = "{cfg.get("gpu","auto")}"')
    lines.append(f'mesa_git = "{cfg.get("mesa_git","off")}"')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p
