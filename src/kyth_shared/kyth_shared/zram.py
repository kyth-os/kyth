"""Zram swap tiering — DEPRECATED shim.

The project had three writers for /etc/systemd/zram-generator.conf:
  * build_files/scripts/sysconfig/kernel/13-ntsync.sh  (static image default)
  * build_files/kyth_shared/kyth_shared/zram.py        (zram.toml offline)
  * build_files/kyth_shared/kyth_shared/memory_tune.py (MemTotal scaling)

memory_tune.py is now the single writer. This module remains for
back-compat but delegates to it. New code should import from
kyth_shared.memory_tune instead.

The shim preserves the old zram.toml schema (zram_percent / swappiness /
algorithm) by translating it to memory_tune tiers:
  zram_percent 50 → low tier (ram*0.5, 8G cap) etc.
"""

from __future__ import annotations

import warnings

from kyth_shared.memory_tune import (
    generate_memory_tune as _generate_memory_tune,
    load_memory_tune as _load_memory_tune,
)

# Re-export the old public API so `from kyth_shared.zram import load_zram`
# keeps working, but warn.
import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_ZRAM_PATH = Path("/etc/kyth/zram.toml")


def zram_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "zram.toml"
    return DEFAULT_ZRAM_PATH


def load_zram(path: Path | None = None) -> dict[str, Any]:
    p = zram_config_path(path)
    try:
        with p.open("rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError):
        return {"zram_percent": 50, "swappiness": 180, "algorithm": "zstd"}
    return {
        "zram_percent": max(10, min(100, int(data.get("zram_percent", 50)))),
        "swappiness": max(0, min(200, int(data.get("swappiness", 180)))),
        "algorithm": str(data.get("algorithm", "zstd")),
    }


def save_zram(cfg: dict[str, Any], path: Path | None = None) -> Path:
    warnings.warn(
        "kyth_shared.zram is deprecated — use kyth_shared.memory_tune instead",
        DeprecationWarning,
        stacklevel=2,
    )
    p = zram_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kyth zram — offline (deprecated, use memory-tune.toml)\n"]
    lines.append(f'zram_percent = {int(cfg.get("zram_percent", 50))}')
    lines.append(f'swappiness = {int(cfg.get("swappiness", 180))}')
    lines.append(f'algorithm = "{cfg.get("algorithm", "zstd")}"')
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


def _tier_for_percent(pct: int) -> str:
    if pct <= 40:
        return "low"
    if pct <= 75:
        return "mid"
    return "high"


def generate_zram_conf(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path:
    """Deprecated — delegates to memory_tune.generate_memory_tune."""
    warnings.warn(
        "kyth_shared.zram.generate_zram_conf is deprecated — use "
        "kyth_shared.memory_tune.generate_memory_tune instead",
        DeprecationWarning,
        stacklevel=2,
    )
    if cfg is None:
        cfg = load_zram()
    # Translate old percent schema → memory_tune tier, then reuse its writer.
    # This makes the single writer (memory_tune) own /etc/systemd/zram-generator.conf.
    tier = _tier_for_percent(int(cfg.get("zram_percent", 50)))
    mem_cfg: dict[str, Any] = {"tier": tier}
    # Preserve explicit algorithm if provided (memory_tune always uses zstd;
    # we keep the field for compat but the generator hard-codes zstd).
    return _generate_memory_tune(mem_cfg, dest=dest)
