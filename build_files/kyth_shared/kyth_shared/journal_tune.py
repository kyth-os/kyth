"""Journal slim — journal.toml declarative, offline.

Default base caps at 500M/128M (28-journald-size-cap.sh). This preset
slims to 200M/64M + ForwardToSyslog=no + MaxRetentionSec=14day when
enabled (opt-in perf). Off restores stock cap (removes perf drop-in).
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_JOURNAL_PATH = Path("/etc/kyth/journal.toml")
DEFAULT_PERF_CONF = Path("/etc/systemd/journald.conf.d/99-kyth-perf.conf")
BASE_CONF = Path("/etc/systemd/journald.conf.d/99-kyth.conf")


def journal_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "journal.toml"
    return DEFAULT_JOURNAL_PATH


def load_journal(path: Path | None = None) -> dict[str, Any]:
    p = journal_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"perf": False, "system_max_use": "500M", "runtime_max_use": "128M"}
    perf = bool(data.get("perf", False))
    smu = str(data.get("system_max_use", "200M" if perf else "500M"))
    rmu = str(data.get("runtime_max_use", "64M" if perf else "128M"))
    # sanitize simple size
    if not smu or len(smu) > 16:
        smu = "200M" if perf else "500M"
    if not rmu or len(rmu) > 16:
        rmu = "64M" if perf else "128M"
    return {"perf": perf, "system_max_use": smu, "runtime_max_use": rmu}


def save_journal(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = journal_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    perf = bool(cfg.get("perf", False))
    smu = str(cfg.get("system_max_use", "200M" if perf else "500M"))
    rmu = str(cfg.get("runtime_max_use", "64M" if perf else "128M"))
    lines = ["# Kyth journal slim — offline\n", f"perf = {str(perf).lower()}\n", f'system_max_use = "{smu}"\n', f'runtime_max_use = "{rmu}"\n']
    p.write_text("".join(lines), encoding="utf-8")
    return p


def generate_journal_conf(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_journal()
    dest = dest or DEFAULT_PERF_CONF
    if not cfg.get("perf"):
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    smu = str(cfg.get("system_max_use", "200M"))
    rmu = str(cfg.get("runtime_max_use", "64M"))
    content = (
        "# Kyth journal perf — generated, disable via journal.toml perf=false\n"
        "[Journal]\n"
        f"SystemMaxUse={smu}\n"
        f"RuntimeMaxUse={rmu}\n"
        "MaxRetentionSec=14day\n"
        "ForwardToSyslog=no\n"
        "Compress=yes\n"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def journal_status(perf_conf: Path = DEFAULT_PERF_CONF) -> bool:
    return perf_conf.exists()
