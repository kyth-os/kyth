"""Scheduler arbiter — single writer for CPU placement (SCX vs BORE vs gamemode vs ananicy).

Replaces stacked scheduling: previously scx_rusty + ananicy-cpp pin + gamemode pin_cores=yes
+ kyth-game-boost sched_setaffinity all competed. Arbiter is the single owner:

- Detect scx_rusty active (systemd or pgrep).
- If SCX active: disable ananicy pinning and gamemode pin_cores (SCX already places).
- Else if bore available (kernel-flavor == cachy): allow gamemode pin_cores, ananicy optional.
- Launchers delegate affinity via systemd-run --slice=gaming.slice, not os.sched_setaffinity.

State lives in /etc/kyth/sched-arbiter.toml (profile = auto|scx_rusty|bore|balanced).
Generated flag is /run/kyth/sched-arbiter.json for launchers to consult without parsing TOML.
"""

from __future__ import annotations
import logging

import json
import os
import shutil
import tomllib
from pathlib import Path
from typing import Any

from .commands import run as run_command

logger = logging.getLogger(__name__)

DEFAULT_PATH = Path("/etc/kyth/sched-arbiter.toml")
DEFAULT_FLAG = Path("/run/kyth/sched-arbiter.json")
DEFAULT_GAMEMODE_INI = Path("/etc/gamemode.ini")
KERNEL_FLAVOR_PATH = Path("/usr/share/kyth/kernel-flavor")


def arbiter_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "sched-arbiter.toml"
    return DEFAULT_PATH


def flag_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    if os.environ.get("KYTH_TEST_MODE") == "1" and os.environ.get("XDG_RUNTIME_DIR"):
        return Path(os.environ["XDG_RUNTIME_DIR"]) / "sched-arbiter.json"
    return DEFAULT_FLAG


def detect_scx_active() -> bool:
    # systemd check
    if shutil.which("systemctl"):
        try:
            r = run_command(["systemctl", "is-active", "--quiet", "scx_loader.service"], check=False, timeout=2)
            if r and r.returncode == 0:
                return True
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path  # nosec B110 -- best-effort, failure here is non-fatal by design
            pass
        try:
            r = run_command(["systemctl", "is-active", "--quiet", "scx.service"], check=False, timeout=2)
            if r and r.returncode == 0:
                return True
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    # pgrep fallback
    if shutil.which("pgrep"):
        try:
            r = run_command(["pgrep", "-x", "scx_rusty"], capture_output=True, check=False, timeout=2)
            if r and r.returncode == 0 and getattr(r, "stdout", b"").strip():
                return True
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    # binary present but not active => not active
    return False


def bore_available(flavor_path: Path = KERNEL_FLAVOR_PATH) -> bool:
    try:
        return flavor_path.read_text(encoding="utf-8").strip().lower() in ("cachy", "cachyos")
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        return False


def load_arbiter(path: Path | None = None) -> dict[str, Any]:
    p = arbiter_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"chosen": "auto", "allow_ananicy_pin": False, "gamemode_pin": False}
    chosen = str(data.get("chosen", "auto")).lower()
    if chosen not in ("auto", "scx_rusty", "bore", "balanced", "none"):
        chosen = "auto"
    # normalize legacy "none" -> balanced
    if chosen == "none":
        chosen = "balanced"
    return {
        "chosen": chosen,
        "allow_ananicy_pin": bool(data.get("allow_ananicy_pin", False)),
        "gamemode_pin": bool(data.get("gamemode_pin", False)),
    }


def save_arbiter(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = arbiter_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    chosen = str(cfg.get("chosen", "auto")).lower()
    if chosen not in ("auto", "scx_rusty", "bore", "balanced"):
        chosen = "auto"
    content = (
        f"# Kyth scheduler arbiter — single writer for placement\n"
        f"# chosen: auto (detect SCX), scx_rusty, bore, balanced\n"
        f"chosen = \"{chosen}\"\n"
        f"allow_ananicy_pin = {str(bool(cfg.get('allow_ananicy_pin', False))).lower()}\n"
        f"gamemode_pin = {str(bool(cfg.get('gamemode_pin', False))).lower()}\n"
    )
    p.write_text(content, encoding="utf-8")
    return p


def arbiter_status(flag: Path | None = None) -> str:
    fp = flag_path(flag)
    if fp.is_file():
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            return str(data.get("active", "unknown"))
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    # fallback to config
    cfg = load_arbiter()
    return str(cfg.get("chosen", "auto"))


def _desired_state(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    if cfg is None:
        cfg = load_arbiter()
    chosen = str(cfg.get("chosen", "auto"))
    scx_active = detect_scx_active()
    is_bore = bore_available()
    if chosen == "auto":
        if scx_active:
            active = "scx_rusty"
        elif is_bore:
            active = "bore"
        else:
            active = "balanced"
    else:
        active = chosen
    # SCX owns placement — never pin via ananicy/gamemode when SCX active
    if active == "scx_rusty" or scx_active:
        pin = False
        ananicy_pin = False
    elif active == "bore":
        pin = bool(cfg.get("gamemode_pin", False))
        ananicy_pin = bool(cfg.get("allow_ananicy_pin", False))
    else:
        pin = False
        ananicy_pin = False
    return {
        "chosen": chosen,
        "active": active,
        "scx_active": scx_active,
        "bore_available": is_bore,
        "gamemode_pin": pin,
        "allow_ananicy_pin": ananicy_pin,
    }


def generate_arbiter(cfg: dict[str, Any] | None = None, dest: Path | None = None, gamemode_ini: Path | None = None) -> Path:
    st = _desired_state(cfg)
    dest = flag_path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=2) + "\n", encoding="utf-8")
    tmp.replace(dest)

    # Rewrite gamemode.ini pin_cores to match arbiter (single writer)
    ini = gamemode_ini or DEFAULT_GAMEMODE_INI
    if ini.is_file():
        try:
            text = ini.read_text(encoding="utf-8")
            desired = "yes" if st["gamemode_pin"] else "no"
            # Only touch the [cpu] section pin_cores line
            import re

            # Replace pin_cores line wherever it appears
            new_text, n = re.subn(r"(?m)^\s*pin_cores\s*=.*$", f"pin_cores = {desired}", text)
            if n == 0 and "[cpu]" in text:
                # Insert after [cpu] header
                new_text = text.replace("[cpu]", f"[cpu]\npin_cores = {desired}", 1)
            if new_text != text:
                ini.write_text(new_text, encoding="utf-8")
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
            pass
    return dest


def apply_arbiter() -> dict[str, Any]:
    st = _desired_state()
    generate_arbiter()
    return st
