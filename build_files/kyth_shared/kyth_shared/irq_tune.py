"""IRQ affinity — irq.toml declarative, offline.

Pins GPU/NVMe/NIC IRQs off X3D CCD0 / isolated cores when enabled.
Balanced leaves irqbalance defaults.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_IRQ_PATH = Path("/etc/kyth/irq.toml")
DEFAULT_CONF = Path("/etc/systemd/system/irqbalance.service.d/99-kyth-irq.conf")


def irq_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "irq.toml"
    return DEFAULT_IRQ_PATH


def load_irq(path: Path | None = None) -> dict[str, Any]:
    p = irq_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "isolated_cpus": ""}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    cpus = str(data.get("isolated_cpus", "")).strip()
    # sanitize: only digits, commas, dashes
    if cpus and not all(ch in "0123456789,-" for ch in cpus):
        cpus = ""
    return {"profile": prof, "isolated_cpus": cpus}


def save_irq(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = irq_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "kyth"):
        prof = "balanced"
    cpus = str(cfg.get("isolated_cpus", "")).strip()
    lines = ["# Kyth IRQ affinity — offline\n", f'profile = "{prof}"\n', f'isolated_cpus = "{cpus}"\n']
    p.write_text("".join(lines), encoding="utf-8")
    return p


def generate_irq_conf(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_irq()
    dest = dest or DEFAULT_CONF
    if str(cfg.get("profile", "balanced")) != "kyth":
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    cpus = str(cfg.get("isolated_cpus", "")).strip()
    # autodetect CCD0 via performance helper if not set
    if not cpus:
        try:
            from .performance import get_amd_ccd0_cpus, get_intel_pcores

            c = get_amd_ccd0_cpus() or get_intel_pcores() or ""
            if c:
                cpus = c
        except Exception:
            pass
    banned = cpus or "1"
    content = (
        "# Kyth IRQ affinity — generated\n"
        "[Service]\n"
        f"ExecStart=\nExecStart=/usr/sbin/irqbalance --banirq=0 --banned-cpus={banned}\n"
    )
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(dest)
    return dest


def irq_status(conf: Path = DEFAULT_CONF) -> str:
    return "kyth" if conf.exists() else "balanced"
