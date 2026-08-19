"""Plymouth theme preset — plymouth.toml, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_PLYMOUTH_PRESET_PATH = Path("/etc/kyth/plymouth.toml")

def plymouth_preset_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE")=="1":
        return Path(xdg)/"kyth"/"plymouth.toml"
    return DEFAULT_PLYMOUTH_PRESET_PATH

def load_plymouth_preset(path: Path | None = None) -> dict[str, Any]:
    p=plymouth_preset_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"theme": "kyth", "duration": 5}
    return {"theme": str(data.get("theme","kyth")), "duration": max(1, min(30, int(data.get("duration",5))))}

def save_plymouth_preset(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=plymouth_preset_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth Plymouth theme preset\n"]
    lines.append(f'theme = "{cfg.get("theme","kyth")}"')
    lines.append(f'duration = {int(cfg.get("duration",5))}')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p
