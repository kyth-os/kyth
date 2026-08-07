"""Perf audit — collects 46-70 status + systemd-analyze + probe."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .commands import run as _run

try:
    from .gaming_master import load_master
    from .boot_loader import load_loader, loader_status
    from .oom_gaming import load_oom_gaming, oom_gaming_status
    from .shader_tmpfs import load_shader_tmpfs, shader_tmpfs_status
    from .gaming_cfs import load_gaming_cfs, gaming_cfs_status
except Exception:
    pass


def collect_audit() -> dict[str, Any]:
    out: dict[str, Any] = {}
    try:
        from .gaming_master import load_master

        out["master"] = load_master().get("profile")
    except Exception:
        out["master"] = "unknown"
    for name, mod, fn in [
        ("loader", "boot_loader", "loader_status"),
        ("oom_gaming", "oom_gaming", "oom_gaming_status"),
        ("shader_tmpfs", "shader_tmpfs", "shader_tmpfs_status"),
        ("gaming_cfs", "gaming_cfs", "gaming_cfs_status"),
        ("thp", "thp_tune", "thp_status"),
        ("irq", "irq_tune", "irq_status"),
        ("btrfs", "btrfs_perf", "btrfs_perf_status"),
        ("trim", "trim_preset", "trim_status"),
        ("ananicy", "ananicy_preset", "ananicy_status"),
        ("zswap", "zswap_preset", "zswap_status"),
        ("sched", "sched_latency", "sched_latency_status"),
        ("wine", "wine_sync", "wine_sync_status"),
        ("kwin", "kwin_latency", "kwin_latency_status"),
        ("pipewire_gaming", "pipewire_gaming", "pipewire_gaming_status"),
    ]:
        try:
            m = __import__(f"kyth_shared.{mod}", fromlist=[fn])
            out[name] = getattr(m, fn)()
        except Exception:
            out[name] = "unknown"
    # systemd-analyze
    try:
        r = _run(["systemd-analyze"], capture_output=True, text=True, timeout=5)
        out["systemd_analyze"] = r.stdout.strip().splitlines()[0] if r and r.stdout else ""
    except Exception:
        out["systemd_analyze"] = "unavailable (not booted with systemd)"
    # probe count
    try:
        from .telemetry import load_sessions  # noqa
        out["telemetry"] = "ok"
    except Exception:
        out["telemetry"] = "unknown"
    out["ts"] = int(time.time())
    return out


def format_audit(a: dict[str, Any]) -> str:
    lines = ["# Kyth perf audit — 46-70"]
    for k in ("master", "loader", "oom_gaming", "shader_tmpfs", "gaming_cfs", "thp", "irq", "btrfs", "trim", "ananicy", "zswap", "sched", "wine", "kwin", "pipewire_gaming"):
        lines.append(f"{k}: {a.get(k)}")
    lines.append(f"systemd-analyze: {a.get('systemd_analyze')}")
    return "\n".join(lines) + "\n"
