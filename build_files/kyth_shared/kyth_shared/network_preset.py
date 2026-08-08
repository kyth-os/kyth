"""Network preset — network.toml declarative DoT + firewalld, offline."""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_NETWORK_PATH = Path("/etc/kyth/network.toml")


def network_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "network.toml"
    return DEFAULT_NETWORK_PATH


def load_network_preset(path: Path | None = None) -> dict[str, Any]:
    p = network_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"dns": "quad9", "doh": True, "firewall_zone": "home"}
    dns = str(data.get("dns", "quad9"))
    if dns not in ("quad9","cloudflare","off","google"):
        dns="quad9"
    doh = bool(data.get("doh", True))
    zone = str(data.get("firewall_zone", "home"))
    if zone not in ("home","public","work"):
        zone="home"
    return {"dns": dns, "doh": doh, "firewall_zone": zone}


def save_network_preset(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = network_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    lines=["# Kyth network preset — DoT + firewalld, offline\n"]
    lines.append(f'dns = "{cfg.get("dns","quad9")}"')
    lines.append(f'doh = {str(bool(cfg.get("doh", True))).lower()}')
    lines.append(f'firewall_zone = "{cfg.get("firewall_zone","home")}"')
    p.write_text("\n".join(lines)+"\n", encoding="utf-8")
    return p


def apply_network_preset(cfg: dict[str, Any] | None = None, root: Path = Path("/")) -> list[Path]:
    if cfg is None:
        cfg=load_network_preset()
    written=[]
    doh = "yes" if cfg.get("doh") else "no"
    dns_ip = {"quad9":"9.9.9.9","cloudflare":"1.1.1.1","google":"8.8.8.8","off":""}.get(cfg.get("dns","quad9"), "9.9.9.9")
    dest = root / "etc/systemd/resolved.conf.d/50-kyth.conf" if str(root) != "/" else Path("/etc/systemd/resolved.conf.d/50-kyth.conf")
    # handle root prefix correctly
    if str(root) != "/":
        dest = root / "etc/systemd/resolved.conf.d/50-kyth.conf"
    else:
        dest = Path("/etc/systemd/resolved.conf.d/50-kyth.conf")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp=dest.with_suffix(".tmp")
    tmp.write_text(f"[Resolve]\nDNS={dns_ip}\nDNSOverTLS={doh}\n", encoding="utf-8")
    tmp.replace(dest)
    written.append(dest)
    try:
        import time
        Path("/run/kyth-network-ttl").write_text(str(int(time.time())+30), encoding="utf-8")
    except Exception:
        pass
    return written
