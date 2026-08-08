"""Fonts & rendering preset — fonts.toml, offline."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any

DEFAULT_FONTS_PATH = Path.home() / ".config" / "kyth" / "fonts.toml"

def fonts_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg=os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg)/"kyth"/"fonts.toml"
    return DEFAULT_FONTS_PATH

def load_fonts(path: Path | None = None) -> dict[str, Any]:
    p=fonts_config_path(path)
    try:
        data=tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"hinting": "full", "antialias": "rgba", "dpi": 96, "family": "Inter"}
    return {"hinting": str(data.get("hinting","full")) if str(data.get("hinting","full")) in ("full","medium","slight","none") else "full",
            "antialias": str(data.get("antialias","rgba")) if str(data.get("antialias","rgba")) in ("rgba","grayscale","none") else "rgba",
            "dpi": max(72, min(300, int(data.get("dpi",96)))), "family": str(data.get("family","Inter"))}

def save_fonts(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p=fonts_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth fonts rendering, offline\n"]
    lines.append(f'hinting = "{cfg.get("hinting","full")}"')
    lines.append(f'antialias = "{cfg.get("antialias","rgba")}"')
    lines.append(f'dpi = {int(cfg.get("dpi",96))}')
    lines.append(f'family = "{cfg.get("family","Inter")}"')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p
