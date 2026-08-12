"""Perf audit — collects 46-140 status + systemd-analyze + probe (consolidated base for system_audit)."""
from __future__ import annotations

import time
from typing import Any

from .commands import run as _run

# Pre-warm these modules into sys.modules so the fresh `from .x import y`
# re-imports done deeper in this file (avoiding 50 dynamic imports per Hub
# page open, per the cache below) resolve from the import cache instead of
# re-reading from disk. The bound names themselves are intentionally unused
# here — the import is for its sys.modules side effect only.
try:
    from .gaming_master import load_master  # noqa: F401  # pylint: disable=unused-import
    from .boot_loader import load_loader, loader_status  # noqa: F401  # pylint: disable=unused-import
    from .oom_gaming import load_oom_gaming, oom_gaming_status  # noqa: F401  # pylint: disable=unused-import
    from .shader_tmpfs import load_shader_tmpfs, shader_tmpfs_status  # noqa: F401  # pylint: disable=unused-import
    from .gaming_cfs import load_gaming_cfs, gaming_cfs_status  # noqa: F401  # pylint: disable=unused-import
except Exception:
    pass


# Simple TTL cache for probe/audit — avoids 50 dynamic imports per Hub page open
_AUDIT_CACHE: dict[str, Any] | None = None
_AUDIT_CACHE_TS: float = 0
_AUDIT_TTL = 30.0  # seconds


def collect_audit(force: bool = False) -> dict[str, Any]:
    global _AUDIT_CACHE, _AUDIT_CACHE_TS
    if not force and _AUDIT_CACHE is not None and (time.time() - _AUDIT_CACHE_TS) < _AUDIT_TTL:
        return dict(_AUDIT_CACHE)
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
        ("vm_watermark", "vm_watermark", "watermark_status"),
        ("tcp_notsent", "tcp_notsent", "tcp_notsent_status"),
        ("max_map_count", "max_map_count", "max_map_count_status"),
        ("dirty_ratio", "dirty_ratio", "dirty_ratio_status"),
        ("vfs_cache", "vfs_cache_pressure", "vfs_cache_status"),
        ("tcp_ecn", "tcp_ecn", "tcp_ecn_status"),
        ("tcp_slow_start", "tcp_slow_start", "tcp_slow_start_status"),
        ("autogroup", "sched_autogroup", "autogroup_status"),
        ("nr_migrate", "sched_nr_migrate", "nr_migrate_status"),
        ("page_cluster", "page_cluster", "page_cluster_status"),
        ("tcp_retries2", "tcp_retries2", "tcp_retries2_status"),
        ("tcp_keepalive", "tcp_keepalive", "tcp_keepalive_status"),
        ("sched_child", "sched_child", "sched_child_status"),
        ("vm_stat", "vm_stat", "vm_stat_status"),
        ("numa_balancing", "numa_balancing", "numa_balancing_status"),
        ("tcp_fastopen", "tcp_fastopen", "tcp_fastopen_status"),
        ("tcp_mtu_probing", "tcp_mtu_probing", "tcp_mtu_probing_status"),
        ("dirty_expire", "dirty_expire", "dirty_expire_status"),
        ("file_max", "file_max", "file_max_status"),
        ("perf_cpu", "perf_cpu", "perf_cpu_status"),
        ("swappiness", "swappiness", "swappiness_status"),
        ("tcp_fin_timeout", "tcp_fin_timeout", "tcp_fin_timeout_status"),
        ("somaxconn", "somaxconn", "somaxconn_status"),
        ("inotify_watches", "inotify_watches", "inotify_watches_status"),
        ("min_free_kbytes", "min_free_kbytes", "min_free_kbytes_status"),
        ("rmem_max", "rmem_max", "rmem_max_status"),
        ("wmem_max", "wmem_max", "wmem_max_status"),
        ("aio_max", "aio_max", "aio_max_status"),
        ("overcommit_memory", "overcommit_memory", "overcommit_memory_status"),
        ("netdev_budget", "netdev_budget", "netdev_budget_status"),
        ("rmem_default", "rmem_default", "rmem_default_status"),
        ("wmem_default", "wmem_default", "wmem_default_status"),
        ("tcp_window_scaling", "tcp_window_scaling", "tcp_window_scaling_status"),
        ("tcp_sack", "tcp_sack", "tcp_sack_status"),
        ("tcp_timestamps", "tcp_timestamps", "tcp_timestamps_status"),
        ("busy_read", "busy_read", "busy_read_status"),
        ("busy_poll", "busy_poll", "busy_poll_status"),
        ("tcp_no_metrics_save", "tcp_no_metrics_save", "tcp_no_metrics_save_status"),
        ("tcp_retries1", "tcp_retries1", "tcp_retries1_status"),
        ("tcp_orphan_retries", "tcp_orphan_retries", "tcp_orphan_retries_status"),
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
        from .telemetry import load_sessions  # noqa  # pylint: disable=unused-import
        out["telemetry"] = "ok"
    except Exception:
        out["telemetry"] = "unknown"
    out["ts"] = int(time.time())
    _AUDIT_CACHE = dict(out)
    _AUDIT_CACHE_TS = time.time()
    return dict(out)


def format_audit(a: dict[str, Any]) -> str:
    lines = ["# Kyth perf audit — 46-140"]
    for k in ("master", "loader", "oom_gaming", "shader_tmpfs", "gaming_cfs", "thp", "irq", "btrfs", "trim", "ananicy", "zswap", "sched", "wine", "kwin", "pipewire_gaming", "vm_watermark", "tcp_notsent", "max_map_count", "dirty_ratio", "vfs_cache", "tcp_ecn", "tcp_slow_start", "autogroup", "nr_migrate", "page_cluster", "tcp_retries2", "tcp_keepalive", "sched_child", "vm_stat", "numa_balancing", "tcp_fastopen", "tcp_mtu_probing", "dirty_expire", "file_max", "perf_cpu", "swappiness", "tcp_fin_timeout", "somaxconn", "inotify_watches", "min_free_kbytes", "rmem_max", "wmem_max", "aio_max", "overcommit_memory", "netdev_budget", "rmem_default", "wmem_default", "tcp_window_scaling", "tcp_sack", "tcp_timestamps", "busy_read", "busy_poll", "tcp_no_metrics_save", "tcp_retries1", "tcp_orphan_retries"):
        lines.append(f"{k}: {a.get(k)}")
    lines.append(f"systemd-analyze: {a.get('systemd_analyze')}")
    return "\n".join(lines) + "\n"
