"""Master gaming performance — gaming-performance.toml declarative.

Single profile=gaming|balanced that composes 46-60 toggles.
No new daemon, just orchestrates existing presets.
"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

DEFAULT_MASTER_PATH = Path("/etc/kyth/gaming-performance.toml")


def master_config_path(path: Path | None = None) -> Path:
    if path is not None:
        return Path(path)
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg and os.environ.get("KYTH_TEST_MODE") == "1":
        return Path(xdg) / "kyth" / "gaming-performance.toml"
    return DEFAULT_MASTER_PATH


def load_master(path: Path | None = None) -> dict[str, Any]:
    p = master_config_path(path)
    try:
        data = tomllib.load(p.open("rb"))
    except (OSError, tomllib.TOMLDecodeError):
        return {"profile": "balanced"}
    prof = str(data.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    return {"profile": prof}


def save_master(cfg: dict[str, Any], path: Path | None = None) -> Path:
    p = master_config_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    prof = str(cfg.get("profile", "balanced")).lower()
    if prof not in ("balanced", "gaming"):
        prof = "balanced"
    p.write_text(f"# Kyth master gaming performance — offline\nprofile = \"{prof}\"\n", encoding="utf-8")
    return p


def apply_master(profile: str | None = None, dry_run: bool = False) -> dict[str, str]:
    """Apply composed presets. Returns map name->status."""
    if profile is None:
        profile = load_master().get("profile", "balanced")
    gaming = profile == "gaming"
    # snapshot before gaming master (77)
    if gaming and not dry_run:
        try:
            from .gaming_snapshot import ensure_snapshot_before_master

            ensure_snapshot_before_master()
        except Exception:
            pass
    out: dict[str, str] = {}
    # dynamic imports to avoid cycles
    try:
        from .kargs_preset import load_kargs, save_kargs

        c = load_kargs()
        c["profile"] = "gaming" if gaming else "balanced"
        if not dry_run:
            save_kargs(c)
        out["kargs"] = c["profile"]
    except Exception as e:
        out["kargs"] = f"error {e}"
    for mod, name in [
        ("io_tune", "io"),
        ("thp_tune", "thp"),
        ("irq_tune", "irq"),
        ("btrfs_perf", "btrfs"),
        ("trim_preset", "trim"),
        ("ananicy_preset", "ananicy"),
        ("zswap_preset", "zswap"),
        ("sched_latency", "sched"),
    ]:
        try:
            m = __import__(f"kyth_shared.{mod}", fromlist=["load", "save", "generate"])
            load = getattr(m, f"load_{name}" if hasattr(m, f"load_{name}") else f"load_{mod.split('_')[0]}")
            # fallback handling: try common names
            if not callable(load):
                raise AttributeError
            # Use generic load_*
            # Instead directly handle per module types
        except Exception:
            pass
    # Explicit per-profile applies via helpers (avoid import complexity, use generate funcs directly)
    try:
        from .thp_tune import load_thp, save_thp, generate_thp_conf

        c = load_thp()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_thp(c)
            generate_thp_conf(c)
        out["thp"] = c["profile"]
    except Exception as e:
        out["thp"] = f"error {e}"
    try:
        from .irq_tune import load_irq, save_irq, generate_irq_conf

        c = load_irq()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_irq(c)
            generate_irq_conf(c)
        out["irq"] = c["profile"]
    except Exception as e:
        out["irq"] = f"error {e}"
    try:
        from .btrfs_perf import load_btrfs_perf, save_btrfs_perf, generate_btrfs_dropin

        c = load_btrfs_perf()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_btrfs_perf(c)
            generate_btrfs_dropin(c)
        out["btrfs"] = c["profile"]
    except Exception as e:
        out["btrfs"] = f"error {e}"
    # Folded: pipewire/kwin/autogroup/watermark/oom/cfs — single transaction owner
    for _mod, _name in [
        ("pipewire_gaming", "pipewire"),
        ("kwin_latency", "kwin"),
        ("sched_autogroup", "autogroup"),
        ("vm_watermark", "watermark"),
        ("oom_gaming", "oom"),
        ("gaming_cfs", "cfs"),
    ]:
        try:
            m = __import__(f"kyth_shared.{_mod}", fromlist=["load", "generate"])
            # generic: load_* may be load_pipewire_gaming etc — try both
            lname = f"load_{_name}"
            gname = f"generate_{_name}" if hasattr(m, f"generate_{_name}") else f"generate_{_mod}"
            if not hasattr(m, lname):
                # fallback search for any load_*
                for attr in dir(m):
                    if attr.startswith("load_"):
                        lname = attr
                        break
            c = getattr(m, lname)()
            # map to profile naming per module
            if "profile" in c:
                c["profile"] = "kyth" if gaming else "balanced"
            elif "enabled" in c:
                c["enabled"] = bool(gaming)
            if not dry_run:
                # find generate and call
                for g in (gname, f"generate_{_mod}", "generate"):
                    if hasattr(m, g):
                        getattr(m, g)(c)
                        break
            out[_name] = str(c.get("profile", c.get("enabled", gaming)))
        except Exception as e:
            out[_name] = f"error {e}"
    try:
        from .trim_preset import load_trim, save_trim, generate_trim_state

        c = load_trim()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_trim(c)
            generate_trim_state(c)
        out["trim"] = c["profile"]
    except Exception as e:
        out["trim"] = f"error {e}"
    try:
        from .ananicy_preset import load_ananicy, save_ananicy, generate_ananicy

        c = load_ananicy()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_ananicy(c)
            generate_ananicy(c)
        out["ananicy"] = c["profile"]
    except Exception as e:
        out["ananicy"] = f"error {e}"
    try:
        from .zswap_preset import load_zswap, save_zswap, generate_zswap

        c = load_zswap()
        # zswap only on gaming + low RAM, but master enables kyth
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_zswap(c)
            generate_zswap(c)
        out["zswap"] = c["profile"]
    except Exception as e:
        out["zswap"] = f"error {e}"
    try:
        from .sched_latency import load_sched_latency, save_sched_latency, generate_sched_latency

        c = load_sched_latency()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_sched_latency(c)
            generate_sched_latency(c)
        out["sched"] = c["profile"]
    except Exception as e:
        out["sched"] = f"error {e}"
    try:
        from .io_tune import load_io_tune, save_io_tune, generate_io_udev

        c = load_io_tune()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_io_tune(c)
            generate_io_udev(c)
        out["io"] = c["profile"]
    except Exception as e:
        out["io"] = f"error {e}"
    try:
        from .net_latency import load_net_latency, save_net_latency, generate_net_latency_conf

        c = load_net_latency()
        c["enabled"] = bool(gaming)
        if not dry_run:
            save_net_latency(c)
            generate_net_latency_conf(c)
        out["net"] = str(c["enabled"])
    except Exception as e:
        out["net"] = f"error {e}"
    try:
        from .zram import load_zram  # noqa

        pass
    except Exception:
        pass
    out["profile"] = profile
    return out
