"""HDR store — preserve per-output HDR peak across updates, KWin."""
from __future__ import annotations

import os, tomllib
from pathlib import Path
from typing import Any


DEFAULT_HDR_STORE_PATH = Path("/etc/kyth/hdr-store.toml")
KWINRC = Path.home() / ".config/kwinrc"


def hdr_store_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "hdr-store.toml"
    return DEFAULT_HDR_STORE_PATH


def load_hdr_store(path: Path | None = None) -> dict[str, Any]:
    p = hdr_store_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"preserve": True}
    return {"preserve": bool(data.get("preserve", True))}


def save_hdr_store(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = hdr_store_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    pr = bool(cfg.get("preserve", True))
    p.write_text(f"# Kyth HDR store — offline\npreserve = {str(pr).lower()}\n", encoding="utf-8")
    return p


def hdr_store_audit() -> dict[str, Any]:
    try:
        from .display_hdr import load_hdr_config

        cfg = load_hdr_config()
        return {"displays": len(cfg), "peak": {k: v.get("peak_nits") for k, v in cfg.items()}}
    except Exception:
        return {"displays": 0}
