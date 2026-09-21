"""Network preset — network.toml declarative DoT + firewalld, offline."""
from __future__ import annotations
import logging

import os
import re
import tomllib
from pathlib import Path
from typing import Any

from .atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

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
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"dns": "quad9", "doh": True, "firewall_zone": "public"}
    dns = str(data.get("dns", "quad9"))
    if dns not in ("quad9","cloudflare","off","google"):
        dns="quad9"
    doh = bool(data.get("doh", True))
    # `block` is the VPN lockdown target: it must round-trip, never be
    # downgraded to a trusting zone. Unknown zones fail closed to `public`,
    # mirroring the Rust preset default.
    zone = str(data.get("firewall_zone", "public"))
    if zone not in ("home","public","work","block"):
        zone="public"
    # Round-trip the Hub VPN opt-ins (and strict DoT): dropping unknown keys
    # here would wipe flags the Rust Hub toggles just persisted.
    return {
        "dns": dns,
        "doh": doh,
        "firewall_zone": zone,
        "dns_strict": bool(data.get("dns_strict", False)),
        "vpn_dns_exclusive": bool(data.get("vpn_dns_exclusive", False)),
        "vpn_fail_closed": bool(data.get("vpn_fail_closed", False)),
    }


def _toml_str(value: Any, default: str = "") -> str:
    """Render a TOML basic string with escaping.

    Saver dicts can carry arbitrary text (drive names, remotes, repos); a
    raw f-string interpolation lets `"` + newline inject whole sections
    the root daemon later parses (rclone remote hijack). Escape controls,
    backslash, and quote.
    """
    text = str(value) if value is not None else default
    if not text:
        text = default
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t") + '"'


def _toml_name(value: Any) -> str:
    """Validate a TOML section/key name (drive names); reject injection."""
    name = str(value or "")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", name):
        raise ValueError(f"refusing unsafe drive name {name!r}")
    return name


def save_network_preset(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = network_config_path(path)
    dns = str(cfg.get("dns", "quad9"))
    if dns not in ("quad9", "cloudflare", "google", "off"):
        dns = "quad9"
    zone = str(cfg.get("firewall_zone", "public"))
    if zone not in ("home", "public", "work", "block"):
        zone = "public"
    lines=["# Kyth network preset — DoT + firewalld, offline\n"]
    lines.append(f'dns = {_toml_str(dns)}')
    lines.append(f'doh = {str(bool(cfg.get("doh", True))).lower()}')
    lines.append(f'firewall_zone = {_toml_str(zone)}')
    lines.append(f'dns_strict = {str(bool(cfg.get("dns_strict", False))).lower()}')
    lines.append(f'vpn_dns_exclusive = {str(bool(cfg.get("vpn_dns_exclusive", False))).lower()}')
    lines.append(f'vpn_fail_closed = {str(bool(cfg.get("vpn_fail_closed", False))).lower()}')
    atomic_write_text(p, "\n".join(lines)+"\n")
    return p


def apply_network_preset(cfg: dict[str, Any] | None = None, root: Path = Path("/")) -> list[Path]:
    if cfg is None:
        cfg=load_network_preset()
    written=[]
    # Corporate DHCP DNS servers commonly do not expose DNS-over-TLS.  Use
    # resolved's opportunistic mode so encrypted DNS remains preferred when
    # available without breaking per-link enterprise resolvers.
    # `dns_strict` is an explicit Hub opt-in (mirrors the Rust renderer):
    # it breaks captive portals, so only set it when the user chose it.
    if cfg.get("dns_strict"):
        doh = "strict"
    else:
        doh = "opportunistic" if cfg.get("doh") else "no"
    dns_ip = {"quad9":"9.9.9.9","cloudflare":"1.1.1.1","google":"8.8.8.8","off":""}.get(cfg.get("dns","quad9"), "9.9.9.9")
    dest = root / "etc/systemd/resolved.conf.d/50-kyth.conf" if str(root) != "/" else Path("/etc/systemd/resolved.conf.d/50-kyth.conf")
    # handle root prefix correctly
    if str(root) != "/":
        dest = root / "etc/systemd/resolved.conf.d/50-kyth.conf"
    else:
        dest = Path("/etc/systemd/resolved.conf.d/50-kyth.conf")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # atomic_write_text (mkstemp + fsync + symlink refusal + rename) replaces
    # the old hand-rolled tmp + backup/rollback: no torn file, no symlink
    # plant at the predictable 50-kyth.tmp path.
    try:
        atomic_write_text(dest, f"[Resolve]\nDNS={dns_ip}\nDNSOverTLS={doh}\n")
        written.append(dest)
    except OSError as exc:
        raise RuntimeError(f"failed to write {dest}: {exc}") from exc
    try:
        import time
        Path("/run/kyth-network-ttl").write_text(str(int(time.time())+30), encoding="utf-8")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass
    return written
