"""Kargs perf profile — kargs.toml declarative, offline, revertible.

Keeps base image clean: no kargs are baked in. User opts into
performance/gaming via Hub or `ujust kargs-apply`. Helper handles
rpm-ostree kargs --append/--delete and falls back to marker when
rpm-ostree is unavailable (toolbox/CI).
"""
from __future__ import annotations

import fnmatch
import logging
import os
import tomllib
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_KARGS_PATH = Path("/etc/kyth/kargs.toml")

# Map profile -> kargs to add when enabled. Remove on revert to balanced.
PROFILE_KARGS: dict[str, list[str]] = {
    "balanced": [],
    "performance": [
        "amd_pstate=active",
        "preempt=full",
        "transparent_hugepage=madvise",
    ],
    "gaming": [
        "amd_pstate=active",
        "preempt=full",
        "transparent_hugepage=madvise",
        "mitigations=off",
    ],
}

VALID_PROFILES = {"balanced", "performance", "gaming"}


def kargs_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "kargs.toml"
    return DEFAULT_KARGS_PATH


def load_kargs(path: Path | None = None) -> dict[str, Any]:
    p = kargs_config_path(path)
    try:
        with p.open("rb") as _f:
            data = tomllib.load(_f)
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced", "custom_add": [], "custom_remove": []}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in VALID_PROFILES:
        prof = "balanced"
    add = data.get("custom_add", [])
    rem = data.get("custom_remove", [])
    if not isinstance(add, list):
        add = []
    if not isinstance(rem, list):
        rem = []
    add = [str(x) for x in add if isinstance(x, (str, int, float))]
    rem = [str(x) for x in rem if isinstance(x, (str, int, float))]
    return {"profile": prof, "custom_add": add, "custom_remove": rem}


def save_kargs(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = kargs_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in VALID_PROFILES:
        prof = "balanced"
    add = [str(x) for x in cfg.get("custom_add", []) if isinstance(x, (str, int, float))] if isinstance(cfg.get("custom_add"), list) else []
    rem = [str(x) for x in cfg.get("custom_remove", []) if isinstance(x, (str, int, float))] if isinstance(cfg.get("custom_remove"), list) else []
    lines = ["# Kyth kargs perf profile — offline, revertible\n", f'profile = "{prof}"\n']
    add_repr = ", ".join(f'"{x}"' for x in add)
    rem_repr = ", ".join(f'"{x}"' for x in rem)
    lines.append(f"custom_add = [{add_repr}]\n")
    lines.append(f"custom_remove = [{rem_repr}]\n")
    p.write_text("".join(lines), encoding="utf-8")
    return p


def _is_tuf_amd_cachy() -> bool:
    """Return True if host is ASUS TUF all-AMD and running CachyOS kernel.

    Matches ASUSTeK* + TUF* DMI with Cachy flavor file. Fail closed if
    any probe errors — non-TUF or non-Cachy must retain full gaming kargs.
    """
    try:
        vendor = Path("/sys/class/dmi/id/sys_vendor").read_text(encoding="utf-8").strip()
        product = Path("/sys/class/dmi/id/product_name").read_text(encoding="utf-8").strip()
        if not fnmatch.fnmatchcase(vendor.casefold(), "asustek*".casefold()):
            return False
        if not fnmatch.fnmatchcase(product.casefold(), "tuf*".casefold()):
            return False
        flavor_path = Path("/usr/share/kyth/kernel-flavor")
        flavor = flavor_path.read_text(encoding="utf-8").strip().lower() if flavor_path.exists() else ""
        if flavor in ("cachy", "cachyos"):
            return True
        # Fallback: check cmdline for cachy marker when flavor file missing in toolbox
        cmdline = Path("/proc/cmdline").read_text(encoding="utf-8").strip().lower() if Path("/proc/cmdline").exists() else ""
        return "cachy" in cmdline
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort DMI/flavor probe
        return False


def desired_kargs(cfg: dict[str, Any] | None = None) -> list[str]:
    if cfg is None:
        cfg = load_kargs()
    prof = str(cfg.get("profile", "balanced"))
    base = list(PROFILE_KARGS.get(prof, []))
    for a in cfg.get("custom_add", []) or []:
        if a and a not in base:
            base.append(str(a))
    # ASUS TUF all-AMD on CachyOS lacks asus-armoury.ko — drop the two most
    # aggressive gaming kargs to avoid thermal/boost trip, keep amd_pstate=active.
    if prof == "gaming" and _is_tuf_amd_cachy():
        dropped = []
        for aggressive in ("mitigations=off", "preempt=full"):
            if aggressive in base:
                base.remove(aggressive)
                dropped.append(aggressive)
        if dropped:
            logger.info("TUF stability: dropped %s for ASUSTeK TUF + Cachy", ", ".join(dropped))
    # custom_remove is applied by caller against current cmdline; not filtered here
    return base


def current_cmdline(path: Path = Path("/proc/cmdline")) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def kargs_drift(path: Path | None = None, cmdline_path: Path = Path("/proc/cmdline")) -> dict[str, list[str]]:
    """Return missing/extra vs desired. Dry-run, no root."""
    cfg = load_kargs(path)
    desired = desired_kargs(cfg)
    cmdline = current_cmdline(cmdline_path)
    missing = [k for k in desired if k not in cmdline]
    extra = []
    for r in cfg.get("custom_remove", []) or []:
        if r and r in cmdline:
            extra.append(str(r))
    return {"missing": missing, "extra": extra, "desired": desired, "profile": cfg.get("profile", "balanced")}
