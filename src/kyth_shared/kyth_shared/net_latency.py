"""Net latency preset — net-latency.toml declarative, offline.

When enabled, writes sysctl drop-in 99-kyth-net-latency.conf with
BBR+FQ + tcp_fastopen + rmem tweaks. Off removes it. Base image ships
BBR via 99-kyth-network.conf — this is additive, gaming/latency opt-in.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_NET_LATENCY_PATH = Path("/etc/kyth/net-latency.toml")
DEFAULT_LATENCY_CONF = Path("/etc/sysctl.d/99-kyth-net-latency.conf")


def net_latency_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "net-latency.toml"
    return DEFAULT_NET_LATENCY_PATH


def load_net_latency(path: Path | None = None) -> dict[str, Any]:
    p = net_latency_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"enabled": False, "tcp_fastopen": 3, "bbr": True}
    return {
        "enabled": bool(data.get("enabled", False)),
        "tcp_fastopen": max(0, min(3, int(data.get("tcp_fastopen", 3)))),
        "bbr": bool(data.get("bbr", True)),
    }


def save_net_latency(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = net_latency_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    en = bool(cfg.get("enabled", False))
    tfo = max(0, min(3, int(cfg.get("tcp_fastopen", 3))))
    bbr = bool(cfg.get("bbr", True))
    lines = [
        "# Kyth net latency — offline, gaming opt-in\n",
        f"enabled = {str(en).lower()}\n",
        f"tcp_fastopen = {tfo}\n",
        f"bbr = {str(bbr).lower()}\n",
    ]
    p.write_text("".join(lines), encoding="utf-8")
    return p


def generate_net_latency_conf(cfg: dict[str, Any] | None = None, dest: Path | None = None) -> Path | None:
    if cfg is None:
        cfg = load_net_latency()
    dest = dest or DEFAULT_LATENCY_CONF
    if not cfg.get("enabled"):
        try:
            if dest.exists():
                dest.unlink()
        except OSError:
            pass
        return None
    tfo = int(cfg.get("tcp_fastopen", 3))
    bbr = bool(cfg.get("bbr", True))
    lines = ["# Kyth net latency — generated, remove by disabling net-latency.toml\n"]
    if bbr:
        lines.append("net.ipv4.tcp_congestion_control = bbr\n")
        lines.append("net.core.default_qdisc = fq\n")
    lines.append(f"net.ipv4.tcp_fastopen = {tfo}\n")
    lines.append("net.ipv4.tcp_ecn = 1\n")
    lines.append("net.ipv4.tcp_slow_start_after_idle = 0\n")
    lines.append("net.core.rmem_max = 16777216\n")
    lines.append("net.core.wmem_max = 16777216\n")
    lines.append("net.ipv4.tcp_rmem = 4096 87380 16777216\n")
    lines.append("net.ipv4.tcp_wmem = 4096 65536 16777216\n")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text("".join(lines), encoding="utf-8")
    tmp.replace(dest)
    return dest


def net_latency_status(conf: Path = DEFAULT_LATENCY_CONF) -> bool:
    return conf.exists()
