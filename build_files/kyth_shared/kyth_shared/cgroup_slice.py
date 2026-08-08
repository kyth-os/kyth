"""Declarative cgroup gaming slice — gaming.slice + toml.

Offline, hash-gated. Generates systemd gaming.slice resource policy from hardware_policy caps (CPUWeight, MemoryMax, IOWeight, AllowedCPUs). Mirrors preset.toml style.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_CGROUP_PATH = Path("/etc/kyth/gaming-slice.toml")
DEFAULT_SLICE_PATH = Path("/etc/systemd/system/gaming.slice.d/50-kyth.conf")


def cgroup_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    # system path wins; XDG for tests
    if xdg and "test" in str(path or ""):
        return Path(xdg) / "kyth" / "gaming-slice.toml"
    return DEFAULT_CGROUP_PATH


def load_cgroup_config(path: Path | None = None) -> dict[str, Any]:
    cfg_path = cgroup_config_path(path)
    try:
        data = tomllib.load(cfg_path.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"cpu_weight": 300, "memory_max": "80%", "io_weight": 200, "allowed_cpus": ""}
    out = {
        "cpu_weight": int(data.get("cpu_weight", 300)),
        "memory_max": str(data.get("memory_max", "80%")),
        "io_weight": int(data.get("io_weight", 200)),
        "allowed_cpus": str(data.get("allowed_cpus", "")),
    }
    out["cpu_weight"] = max(1, min(1000, out["cpu_weight"]))
    out["io_weight"] = max(1, min(1000, out["io_weight"]))
    return out


def save_cgroup_config(cfg: dict[str, Any], path: Path | None = None) -> Path:
    cfg_path = cgroup_config_path(path)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# Kyth cgroup gaming slice — declarative, offline\n"]
    lines.append(f'cpu_weight = {int(cfg.get("cpu_weight", 300))}')
    lines.append(f'memory_max = "{cfg.get("memory_max", "80%")}"')
    lines.append(f'io_weight = {int(cfg.get("io_weight", 200))}')
    lines.append(f'allowed_cpus = "{cfg.get("allowed_cpus", "")}"')
    cfg_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cfg_path


def generate_slice_conf(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path:
    if cfg is None:
        cfg = load_cgroup_config()
    dest = dest or DEFAULT_SLICE_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    allowed = cfg.get("allowed_cpus", "")
    lines = ["[Slice]", f"CPUWeight={cfg.get('cpu_weight', 300)}", f"MemoryMax={cfg.get('memory_max', '80%')}", f"IOWeight={cfg.get('io_weight', 200)}"]
    if allowed:
        lines.append(f"AllowedCPUs={allowed}")
    # Gaming: high priority, allow overcommit within slice
    lines.append("CPUAccounting=yes")
    lines.append("MemoryAccounting=yes")
    tmp = dest.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(dest)
    return dest
