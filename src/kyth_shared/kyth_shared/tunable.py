"""Generic tunable registry — dispatches kyth-* wrappers to kyth_shared modules.

Slice 2 of the tunable registry refactor: introduces a single source of
truth for the 94 thin bash wrappers. The registry maps wrapper suffix
(e.g. ``swappiness`` for ``kyth-swappiness``) to its Python module and
kind (``sysctl`` vs ``other``). Generic ``load/save/generate/status``
helpers delegate to the underlying module by discovering its
``load_*/save_*/generate_*/ *_status`` callables via naming heuristics,
so existing modules remain the implementation until Slices 3-4 migrate
sysctl emitters into ``sysctl_compose`` tiers.

``build_files/config/tunables.toml`` is the declarative source when
present; the hard-coded ``_BUILTIN_TUNABLES`` dict is the fallback
(and the authorative list for tests/CI without a checkout).
"""

from __future__ import annotations

import importlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib  # py311+
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]

_BUILTIN_TUNABLES: dict[str, dict[str, str]] = {
    "aio-max": {"module": "aio_max", "kind": "sysctl"},
    "ananicy": {"module": "ananicy_preset", "kind": "other"},
    "boot-timeout": {"module": "boot_loader", "kind": "other"},
    "bore": {"module": "bore_tune", "kind": "sysctl"},
    "btrfs-autotune": {"module": "btrfs_autotune", "kind": "other"},
    "btrfs-tune": {"module": "btrfs_perf", "kind": "other"},
    "busy-poll": {"module": "busy_poll", "kind": "sysctl"},
    "busy-read": {"module": "busy_read", "kind": "sysctl"},
    "compaction": {"module": "compaction_tune", "kind": "sysctl"},
    "dirty-expire": {"module": "dirty_expire", "kind": "sysctl"},
    "dirty-ratio": {"module": "dirty_ratio", "kind": "sysctl"},
    "distrobox-cache": {"module": "distrobox_cache", "kind": "other"},
    "epp-ac": {"module": "epp_ac", "kind": "other"},
    "fcitx-latency": {"module": "fcitx_latency", "kind": "other"},
    "file-max": {"module": "file_max", "kind": "sysctl"},
    "flatpak-prefetch": {"module": "flatpak_prefetch", "kind": "other"},
    "flatpak-trim": {"module": "flatpak_trim", "kind": "other"},
    "fscache": {"module": "fscache_tune", "kind": "other"},
    "gaming-audit": {"module": "perf_audit", "kind": "other"},
    "gaming-cfs": {"module": "gaming_cfs", "kind": "other"},
    "gaming-master": {"module": "gaming_master", "kind": "other"},
    "gpu-power": {"module": "gpu_power", "kind": "other"},
    "hdr-per-game": {"module": "hdr_per_game", "kind": "other"},
    "hdr-store": {"module": "hdr_store", "kind": "other"},
    "inotify-watches": {"module": "inotify_watches", "kind": "sysctl"},
    "io-tune": {"module": "io_tune", "kind": "other"},
    "irq-tune": {"module": "irq_tune", "kind": "other"},
    "journal-tune": {"module": "journal_tune", "kind": "other"},
    "kargs-apply": {"module": "kargs_preset", "kind": "other"},
    "kwin-latency": {"module": "kwin_latency", "kind": "other"},
    "max-map-count": {"module": "max_map_count", "kind": "sysctl"},
    "mimalloc": {"module": "mimalloc_preset", "kind": "other"},
    "mimalloc-run": {"module": "mimalloc_preset", "kind": "other"},
    "min-free-kbytes": {"module": "min_free_kbytes", "kind": "sysctl"},
    "net-backlog": {"module": "net_backlog", "kind": "sysctl"},
    "net-tune": {"module": "net_latency", "kind": "sysctl"},
    "netdev-budget": {"module": "netdev_budget", "kind": "sysctl"},
    "numa": {"module": "numa_tune", "kind": "other"},
    "numa-balancing": {"module": "numa_balancing", "kind": "sysctl"},
    "oom-gaming": {"module": "oom_gaming", "kind": "other"},
    "overcommit-memory": {"module": "overcommit_memory", "kind": "sysctl"},
    "page-cluster": {"module": "page_cluster", "kind": "sysctl"},
    "pcie": {"module": "pcie_aspm", "kind": "other"},
    "perf-cpu": {"module": "perf_cpu", "kind": "sysctl"},
    "perf-gate": {"module": "perf_gate", "kind": "other"},
    "pipewire-gaming": {"module": "pipewire_gaming", "kind": "other"},
    "podman-btrfs": {"module": "podman_btrfs", "kind": "other"},
    "podman-overlay": {"module": "overlay_tune", "kind": "other"},
    "psi-gaming": {"module": "psi_gaming", "kind": "other"},
    "psi-poll": {"module": "psi_poll", "kind": "sysctl"},
    "readahead": {"module": "readahead_preset", "kind": "other"},
    "rmem-default": {"module": "rmem_default", "kind": "sysctl"},
    "rmem-max": {"module": "rmem_max", "kind": "sysctl"},
    "sccache": {"module": "sccache_preset", "kind": "other"},
    "sched-arbiter": {"module": "sched_arbiter", "kind": "other"},
    "sched-autogroup": {"module": "sched_autogroup", "kind": "sysctl"},
    "sched-child": {"module": "sched_child", "kind": "sysctl"},
    "sched-latency": {"module": "sched_latency", "kind": "sysctl"},
    "sched-nr-migrate": {"module": "sched_nr_migrate", "kind": "sysctl"},
    "selinux-gaming": {"module": "selinux_gaming", "kind": "other"},
    "shader-cache-size": {"module": "shader_cache_size", "kind": "other"},
    "shader-tmpfs": {"module": "shader_tmpfs", "kind": "other"},
    "somaxconn": {"module": "somaxconn", "kind": "sysctl"},
    "steam-deadzone": {"module": "steam_deadzone", "kind": "other"},
    "swappiness": {"module": "swappiness", "kind": "sysctl"},
    "system-audit": {"module": "system_audit", "kind": "other"},
    "tcp-ecn": {"module": "tcp_ecn", "kind": "sysctl"},
    "tcp-fastopen": {"module": "tcp_fastopen", "kind": "sysctl"},
    "tcp-fin-timeout": {"module": "tcp_fin_timeout", "kind": "sysctl"},
    "tcp-keepalive": {"module": "tcp_keepalive", "kind": "sysctl"},
    "tcp-mtu-probing": {"module": "tcp_mtu_probing", "kind": "sysctl"},
    "tcp-no-metrics-save": {"module": "tcp_no_metrics_save", "kind": "sysctl"},
    "tcp-notsent": {"module": "tcp_notsent", "kind": "sysctl"},
    "tcp-orphan-retries": {"module": "tcp_orphan_retries", "kind": "sysctl"},
    "tcp-retries1": {"module": "tcp_retries1", "kind": "sysctl"},
    "tcp-retries2": {"module": "tcp_retries2", "kind": "sysctl"},
    "tcp-sack": {"module": "tcp_sack", "kind": "sysctl"},
    "tcp-slow-start": {"module": "tcp_slow_start", "kind": "sysctl"},
    "tcp-timestamps": {"module": "tcp_timestamps", "kind": "sysctl"},
    "tcp-window-scaling": {"module": "tcp_window_scaling", "kind": "sysctl"},
    "telemetry-opt": {"module": "telemetry_opt", "kind": "other"},
    "thp-collapse": {"module": "thp_collapse", "kind": "sysctl"},
    "thp-tune": {"module": "thp_tune", "kind": "sysctl"},
    "trim-tune": {"module": "trim_preset", "kind": "other"},
    "uksmd": {"module": "uksmd_preset", "kind": "other"},
    "vfs-cache": {"module": "vfs_cache_pressure", "kind": "sysctl"},
    "vm-stat": {"module": "vm_stat", "kind": "sysctl"},
    "vm-watermark": {"module": "vm_watermark", "kind": "sysctl"},
    "windows-verify": {"module": "windows_verify", "kind": "other"},
    "wine-sync": {"module": "wine_sync", "kind": "other"},
    "wmem-default": {"module": "wmem_default", "kind": "sysctl"},
    "wmem-max": {"module": "wmem_max", "kind": "sysctl"},
    "work-cache": {"module": "work_cache", "kind": "other"},
    "zswap": {"module": "zswap_preset", "kind": "sysctl"},
}


@dataclass(frozen=True, slots=True)
class TunableSpec:
    name: str
    module: str
    kind: str  # "sysctl" | "other"
    wrapper: str = ""  # e.g. kyth-swappiness


def _config_dir() -> Path | None:
    candidates = [
        Path(__file__).resolve().parents[2] / "config",
        Path("/ctx/config"),
        Path("/usr/share/kyth/config"),
        Path("build_files/config"),
    ]
    for p in candidates:
        if (p / "tunables.toml").is_file():
            return p
    return None


def load_registry(config_dir: Path | None = None) -> dict[str, TunableSpec]:
    """Return {name: TunableSpec} from TOML if present, else builtin."""
    toml_path: Path | None = None
    if config_dir is not None:
        toml_path = Path(config_dir) / "tunables.toml"
    else:
        d = _config_dir()
        if d is not None:
            toml_path = d / "tunables.toml"

    if toml_path is not None and toml_path.is_file():
        try:
            with toml_path.open("rb") as f:
                data = tomllib.load(f)
        except Exception:
            data = {}
        tunables = data.get("tunables", {})
        if isinstance(tunables, dict) and tunables:
            out: dict[str, TunableSpec] = {}
            for name, spec in tunables.items():
                if not isinstance(spec, dict):
                    continue
                out[str(name)] = TunableSpec(
                    name=str(name),
                    module=str(spec.get("module", "")),
                    kind=str(spec.get("kind", "other")),
                    wrapper=str(spec.get("wrapper", f"kyth-{name}")),
                )
            if out:
                return out

    # fallback to builtin
    return {
        name: TunableSpec(name=name, module=v["module"], kind=v["kind"], wrapper=f"kyth-{name}")
        for name, v in _BUILTIN_TUNABLES.items()
    }


# Module-level registry (lazy but cached for callers that don't pass config_dir)
_REGISTRY: dict[str, TunableSpec] | None = None


def _registry() -> dict[str, TunableSpec]:
    global _REGISTRY
    if _REGISTRY is None:
        _REGISTRY = load_registry()
    return _REGISTRY


def get_spec(name: str, config_dir: Path | None = None) -> TunableSpec:
    reg = load_registry(config_dir) if config_dir is not None else _registry()
    # normalize: allow kyth- prefix or hyphen/underscore variants
    key = name.removeprefix("kyth-")
    if key in reg:
        return reg[key]
    # try underscore variant
    alt = key.replace("_", "-")
    if alt in reg:
        return reg[alt]
    alt2 = key.replace("-", "_")
    for k, v in reg.items():
        if k.replace("-", "_") == alt2:
            return v
    raise KeyError(f"unknown tunable {name!r}")


def list_tunables(config_dir: Path | None = None) -> list[TunableSpec]:
    reg = load_registry(config_dir) if config_dir is not None else _registry()
    return sorted(reg.values(), key=lambda s: s.name)


def _import_module(spec: TunableSpec):
    return importlib.import_module(f"kyth_shared.{spec.module}")


def _find_callable(mod: Any, prefix: str = "", suffix: str = "") -> Any | None:
    for attr in dir(mod):
        if prefix and not attr.startswith(prefix):
            continue
        if suffix and not attr.endswith(suffix):
            continue
        fn = getattr(mod, attr)
        if callable(fn):
            return fn
    return None


def load_tunable(name: str, path: Path | None = None, config_dir: Path | None = None) -> dict[str, Any]:
    spec = get_spec(name, config_dir)
    mod = _import_module(spec)
    fn = _find_callable(mod, prefix="load_")
    if fn is None:
        raise AttributeError(f"{spec.module} has no load_* function")
    # most load_* accept optional path arg
    try:
        return fn(path) if path is not None else fn()
    except TypeError:
        return fn()


def save_tunable(name: str, cfg: dict[str, Any], path: Path | None = None, config_dir: Path | None = None) -> Path:
    spec = get_spec(name, config_dir)
    mod = _import_module(spec)
    fn = _find_callable(mod, prefix="save_")
    if fn is None:
        raise AttributeError(f"{spec.module} has no save_* function")
    try:
        return fn(cfg, path) if path is not None else fn(cfg)
    except TypeError:
        return fn(cfg)


def generate_tunable(name: str, cfg: dict[str, Any] | None = None, dest: Path | None = None, config_dir: Path | None = None) -> Path | None:
    spec = get_spec(name, config_dir)
    mod = _import_module(spec)
    fn = _find_callable(mod, prefix="generate_")
    if fn is None:
        # no generate for this tunable (e.g. kargs_preset has desired_kargs)
        return None
    # try (cfg, dest) then (cfg) then ()
    try:
        if cfg is not None and dest is not None:
            return fn(cfg, dest)
        if cfg is not None:
            return fn(cfg)
        if dest is not None:
            # some modules: generate_foo(cfg, dest) where cfg optional
            try:
                return fn(None, dest)
            except TypeError:
                return fn(dest)
        return fn()
    except TypeError:
        # fallback: try single arg
        try:
            return fn(cfg) if cfg is not None else fn()
        except TypeError:
            return fn()


def tunable_status(name: str, conf: Path | None = None, config_dir: Path | None = None) -> str:
    spec = get_spec(name, config_dir)
    mod = _import_module(spec)
    fn = _find_callable(mod, suffix="_status")
    if fn is None:
        raise AttributeError(f"{spec.module} has no *_status function")
    try:
        return fn(conf) if conf is not None else fn()
    except TypeError:
        return fn()


def tunable_module(name: str, config_dir: Path | None = None) -> str:
    return get_spec(name, config_dir).module


def tunable_kind(name: str, config_dir: Path | None = None) -> str:
    return get_spec(name, config_dir).kind
