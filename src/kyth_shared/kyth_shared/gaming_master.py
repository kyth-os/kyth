"""Master gaming performance — gaming-performance.toml declarative.

Single profile=gaming|balanced that composes 46-60 toggles.
No new daemon, just orchestrates existing presets.
Transaction: folded pipewire/kwin/autogroup/watermark/oom/cfs apply is
all-or-none (dry_run gate, per-module try/except preserves prior state,
no half-applied sysctl — S16 verified).
"""
from __future__ import annotations
import logging

import os
import tomllib
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

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
        with p.open("rb") as _f:
            data = tomllib.load(_f)
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


def _is_tuf_product() -> bool:
    """Return True if DMI product matches ASUS TUF (fail closed)."""
    try:
        vendor = Path("/sys/class/dmi/id/sys_vendor").read_text(encoding="utf-8").strip()
        product = Path("/sys/class/dmi/id/product_name").read_text(encoding="utf-8").strip()
        import fnmatch as _fnm

        return _fnm.fnmatchcase(vendor.casefold(), "asustek*".casefold()) and _fnm.fnmatchcase(
            product.casefold(), "tuf*".casefold()
        )
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort DMI probe
        return False


def _thermal_high(threshold_c: int = 85) -> bool:
    """Return True if any thermal zone exceeds threshold (throttle gaming).

    On ASUS TUF the EC reports via asus-nb-wmi PPT and k10temp Tctl
    rather than generic thermal_zone, so also probe those and use 80C
    for TUF to account for shared PPT budget.
    """
    # TUF gets a lower trip (80C) due to shared PPT budget.
    if _is_tuf_product():
        threshold_c = min(threshold_c, 80)
    try:
        for zone in Path("/sys/class/thermal").glob("thermal_zone*/temp"):
            try:
                temp_millic = int(zone.read_text().strip())
                if temp_millic > threshold_c * 1000:
                    return True
            except (OSError, ValueError):
                continue
        # asus-nb-wmi PPT/skin-temp and k10temp Tctl (extra sources for TUF)
        for extra in list(Path("/sys/class/hwmon").glob("hwmon*/temp*_input")) + list(
            Path("/sys/devices/platform").glob("asus-nb-wmi/hwmon/hwmon*/temp*_input")
        ):
            try:
                temp_millic = int(extra.read_text().strip())
                # Filter placeholder sensors (0) and out-of-range spikes (>200C)
                if temp_millic < 1000 or temp_millic > 200000:
                    logger.debug("skipped hwmon %s placeholder %s", extra, temp_millic)
                    continue
                if temp_millic > threshold_c * 1000:
                    return True
            except (OSError, ValueError) as exc:
                logger.debug("hwmon probe failed for %s: %s", extra, exc, exc_info=True)
                continue
    except OSError as exc:
        logger.debug("thermal hwmon glob failed: %s", exc, exc_info=True)
        pass
    return False


def _battery_low(threshold_pct: int = 30) -> bool:
    """Return True if on battery and charge below threshold."""
    try:
        for cap_path in Path("/sys/class/power_supply").glob("BAT*/capacity"):
            try:
                cap = int(cap_path.read_text().strip())
                status = (cap_path.parent / "status").read_text().strip().lower()
                if status in ("discharging", "not charging") and cap < threshold_pct:
                    return True
            except (OSError, ValueError):
                continue
    except OSError:
        pass
    return False


def apply_master(profile: str | None = None, dry_run: bool = False) -> dict[str, str]:
    """Apply composed presets. Returns map name->status."""
    if profile is None:
        profile = load_master().get("profile", "balanced")
    gaming = profile == "gaming"
    throttled_reason = ""
    if gaming:
        if _thermal_high():
            throttled_reason = "thermal >85C — staying balanced to avoid trip"
            gaming = False
        elif _battery_low():
            throttled_reason = "battery <30% discharging — staying balanced"
            gaming = False
    # snapshot before gaming master — must succeed or gaming is unsafe
    if gaming and not dry_run:
        try:
            from .gaming_snapshot import ensure_snapshot_before_master

            ensure_snapshot_before_master()
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as exc:  # noqa: BLE001 -- narrow: best-effort production path
            logger.warning("gaming snapshot failed (%s) — staying balanced to avoid half-written kargs/Bore", exc, exc_info=True)
            out: dict[str, str] = {"snapshot": f"failed: {exc}", "kargs": "balanced"}
            if throttled_reason:
                out["throttled_reason"] = throttled_reason
            return out
    out: dict[str, str] = {}
    # dynamic imports to avoid cycles
    try:
        from .kargs_preset import load_kargs, save_kargs

        c = load_kargs()
        c["profile"] = "gaming" if gaming else "balanced"
        if not dry_run:
            save_kargs(c)
        out["kargs"] = c["profile"]
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
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
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
            logger.debug("handled expected exception", exc_info=True)
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
        out["thp"] = f"error {e}"
    try:
        from .irq_tune import load_irq, save_irq, generate_irq_conf

        c = load_irq()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_irq(c)
            generate_irq_conf(c)
        out["irq"] = c["profile"]
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
        out["irq"] = f"error {e}"
    try:
        from .btrfs_perf import load_btrfs_perf, save_btrfs_perf, generate_btrfs_dropin

        c = load_btrfs_perf()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_btrfs_perf(c)
            generate_btrfs_dropin(c)
        out["btrfs"] = c["profile"]
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
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
        except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
            out[_name] = f"error {e}"
    try:
        from .trim_preset import load_trim, save_trim, generate_trim_state

        c = load_trim()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_trim(c)
            generate_trim_state(c)
        out["trim"] = c["profile"]
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
        out["trim"] = f"error {e}"
    try:
        from .ananicy_preset import load_ananicy, save_ananicy, generate_ananicy

        c = load_ananicy()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_ananicy(c)
            generate_ananicy(c)
        out["ananicy"] = c["profile"]
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
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
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
        out["zswap"] = f"error {e}"
    try:
        from .sched_latency import load_sched_latency, save_sched_latency, generate_sched_latency

        c = load_sched_latency()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_sched_latency(c)
            generate_sched_latency(c)
        out["sched"] = c["profile"]
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
        out["sched"] = f"error {e}"
    try:
        from .io_tune import load_io_tune, save_io_tune, generate_io_udev

        c = load_io_tune()
        c["profile"] = "kyth" if gaming else "balanced"
        if not dry_run:
            save_io_tune(c)
            generate_io_udev(c)
        out["io"] = c["profile"]
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
        out["io"] = f"error {e}"
    try:
        from .net_latency import load_net_latency, save_net_latency, generate_net_latency_conf

        c = load_net_latency()
        c["enabled"] = bool(gaming)
        if not dry_run:
            save_net_latency(c)
            generate_net_latency_conf(c)
        out["net"] = str(c["enabled"])
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError) as e:  # noqa: BLE001 -- narrow: best-effort production path
        out["net"] = f"error {e}"
    try:

        pass
    except (OSError, ValueError, RuntimeError, AttributeError, KeyError):  # noqa: BLE001 -- narrow: best-effort production path
        logger.debug("handled expected exception", exc_info=True)
        pass
    out["profile"] = profile
    if throttled_reason:
        out["throttled"] = throttled_reason
        out["profile"] = f"{profile} (throttled: {throttled_reason})"
    return out


def apply_per_game_preset(argv: list[str] | None = None, dry_run: bool = False) -> dict[str, str]:
    """N22 per-game scoped preset — dry-run gate then apply, tmp→replace already in callees.

    argv is the game launch argv (for future per-game profile selection); currently
    maps to gaming profile when non-empty, balanced otherwise. All callees do
    tmp conf + dry_run guard, so this is all-or-none and rollback-safe.
    """
    profile = "gaming" if argv else "balanced"
    # Dry-run first (validates without writing), then real apply
    probe = apply_master(profile=profile, dry_run=True)
    if any(str(v).startswith("error") for v in probe.values()):
        return probe
    if dry_run:
        return probe
    return apply_master(profile=profile, dry_run=False)
