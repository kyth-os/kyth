"""I/O tune — io.toml declarative, offline.

Writes udev rules for NVMe (none) + SATA (mq-deadline) + read_ahead tuning.
Opt-in: default balanced leaves kernel defaults. kyth profile enables
scheduler=none for NVMe, read_ahead_kb tuning, wbt off. Revert removes rule.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_IO_TUNE_PATH = Path("/etc/kyth/io.toml")
DEFAULT_RULE_PATH = Path("/etc/udev/rules.d/61-kyth-io-tune.rules")

VALID_PROFILES = {"balanced", "kyth"}


def io_tune_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "io.toml"
    return DEFAULT_IO_TUNE_PATH


def load_io_tune(path: Path | None = None) -> dict[str, Any]:
    p = io_tune_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "read_ahead_kb": 128}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in VALID_PROFILES:
        prof = "balanced"
    try:
        ra = int(data.get("read_ahead_kb", 128))
    except (TypeError, ValueError):
        ra = 128
    ra = max(8, min(4096, ra))
    return {"profile": prof, "read_ahead_kb": ra}


def save_io_tune(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = io_tune_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in VALID_PROFILES:
        prof = "balanced"
    try:
        ra = int(cfg.get("read_ahead_kb", 128))
    except (TypeError, ValueError):
        ra = 128
    ra = max(8, min(4096, ra))
    lines = ["# Kyth I/O tune — offline\n", f'profile = "{prof}"\n', f"read_ahead_kb = {ra}\n"]
    p.write_text("".join(lines), encoding="utf-8")
    return p


def generate_io_udev(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_io_tune()
    dest = dest or DEFAULT_RULE_PATH
    if str(cfg.get("profile", "balanced")) != "kyth":
        # revert: remove rule if present
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    ra = int(cfg.get("read_ahead_kb", 2048))
    # NVMe kyth profile: none scheduler + read_ahead + wbt off; SATA fallback mq-deadline
    content = (
        "# Kyth I/O tune — generated, remove with ujust io-tune default\n"
        'ACTION=="add|change", KERNEL=="nvme[0-9]*n[0-9]*", ATTR{queue/scheduler}="none"\n'
        f'ACTION=="add|change", KERNEL=="nvme[0-9]*n[0-9]*", ATTR{{queue/read_ahead_kb}}="{ra}"\n'
        'ACTION=="add|change", KERNEL=="nvme[0-9]*n[0-9]*", ATTR{queue/wbt_lat_usec}="0"\n'
        'ACTION=="add|change", KERNEL=="sd[a-z]*", ATTR{queue/scheduler}="mq-deadline"\n'
        'ACTION=="add|change", KERNEL=="sd[a-z]*", ATTR{queue/read_ahead_kb}="1024"\n'
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def io_status(rule_path: Path = DEFAULT_RULE_PATH) -> str:
    return "kyth" if rule_path.exists() else "balanced"
