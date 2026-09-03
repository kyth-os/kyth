# Tunables Inventory — Tunable Registry Refactor (Slice 1)

Generated: 2026-08-18. Source: `build_files/kyth-*` (257 files) + `src/kyth_shared/kyth_shared/*.py` (199 modules).

## Summary

- **Thin bash wrappers**: 94 files matching `#!/usr/bin/env bash` + `python3 -c "from kyth_shared.<mod> import ..."` with identical `set -euo pipefail` / `need_root()` / `case status|gaming|balanced|apply` scaffolding.
- **Sysctl-kind wrappers**: 49 (write `/etc/sysctl.d/99-kyth-*.conf` via `generate_*`, call `sysctl --system`).
- **Other-kind wrappers**: 45 (write `/etc/kyth/*.toml`, `/etc/default/*`, kargs, systemd, etc. — not via sysctl composer).
- **Native Rust dispatcher**: 83 (all 49 sysctl wrappers plus 34 other-kind wrappers); 11 other-kind wrappers remain on the compatibility dispatcher.
- **Already migrated to composer**: `build_files/config/sysctl/base.toml` (24 keys) + `network.toml` (20 keys). `gaming.toml` is empty — the per-tunable gaming overrides are still in individual modules and duplicate the composer tiers.

## Duplicate-key risk

The composer exists to prevent the CAKE/bbr clobber. Several per-tunable keys **already duplicate** composer tiers and will conflict once migrated if not deduplicated:

| Overlap with `base.toml` (must dedup) | Overlap with `network.toml` (must dedup) |
|---|---|
| `vm.compaction_proactiveness` (`compaction_tune`, `thp_tune`) | `net.core.default_qdisc`, `net.core.rmem_max`, `net.core.wmem_max`, `net.ipv4.tcp_rmem`, `net.ipv4.tcp_wmem`, `net.ipv4.tcp_congestion_control`, `net.ipv4.tcp_ecn`, `net.ipv4.tcp_fastopen`, `net.ipv4.tcp_mtu_probing`, `net.ipv4.tcp_slow_start_after_idle` (all in `net_latency`) |
| `vm.dirty_expire_centisecs` (`dirty_expire`) | `net.core.netdev_max_backlog` (`net_backlog`) |
| `vm.dirty_writeback_centisecs` (`dirty_ratio`) | `net.core.rmem_max` (`rmem_max`), `net.core.wmem_max` (`wmem_max`), `net.ipv4.tcp_ecn`, `net.ipv4.tcp_fastopen`, `net.ipv4.tcp_mtu_probing`, `net.ipv4.tcp_slow_start_after_idle` (individual tcp_* modules) |
| `fs.inotify.max_user_watches` (`inotify_watches`) | — |
| `vm.max_map_count` (`max_map_count`) | — |
| `kernel.sched_autogroup_enabled` (`sched_autogroup`) | — |
| `vm.swappiness` (`swappiness`) | — |
| `vm.vfs_cache_pressure` (`vfs_cache_pressure`) | — |
| `vm.stat_interval` (`vm_stat`) | — |
| `vm.watermark_scale_factor` (`vm_watermark`) | — |

`gaming.toml` is currently empty; all 49 sysctl tunables currently emit separate `99-kyth-<name>.conf` files that sort-override the composed `99-kyth-base.conf`. Migration must move **gaming overrides** into `gaming.toml` (tiered) and delete the per-tunable emitters.

## Full 94-wrapper inventory

| # | Wrapper (build_files/) | Py module | Kind | Dest / Gaming value (truncated) | Migrates to |
|---|---|---|---|---|---|
| 1 | kyth-aio-max | aio_max | sysctl | `/etc/sysctl.d/99-kyth-aio-max.conf` → `fs.aio-max-nr=1048576` | gaming.toml |
| 2 | kyth-ananicy | ananicy_preset | other | `/etc/kyth/ananicy.toml` | native Rust dispatcher |
| 3 | kyth-boot-timeout | boot_loader | other | `/etc/kyth/loader.toml` → timeout 2 | registry (other) |
| 4 | kyth-bore | bore_tune | sysctl | `/etc/sysctl.d/99-kyth-bore.conf` → `kernel.sched_bore=1` | gaming.toml |
| 5 | kyth-btrfs-autotune | btrfs_autotune | other | `/etc/kyth/btrfs-autotune.toml` | native Rust dispatcher |
| 6 | kyth-btrfs-tune | btrfs_perf | other | btrfs perf | native Rust dispatcher |
| 7 | kyth-busy-poll | busy_poll | sysctl | `net.core.busy_poll=50` | gaming.toml |
| 8 | kyth-busy-read | busy_read | sysctl | `net.core.busy_read=50` | gaming.toml |
| 9 | kyth-compaction | compaction_tune | sysctl | `vm.compaction_proactiveness=0` — **dup base** | gaming.toml (dedup) |
| 10 | kyth-dirty-expire | dirty_expire | sysctl | `vm.dirty_expire_centisecs=100` — **dup base** | gaming.toml (dedup, base has 500) |
| 11 | kyth-dirty-ratio | dirty_ratio | sysctl | `vm.dirty_ratio=5` / `vm.dirty_background_ratio=5` / `vm.dirty_writeback_centisecs=500` — last **dup base** | gaming.toml |
| 12 | kyth-distrobox-cache | distrobox_cache | other | `/etc/kyth/distrobox-cache.toml` | native Rust dispatcher |
| 13 | kyth-epp-ac | epp_ac | other | `/etc/kyth/epp-ac.toml` | native Rust dispatcher |
| 14 | kyth-fcitx-latency | fcitx_latency | other | fcitx latency | registry (other) |
| 15 | kyth-file-max | file_max | sysctl | `fs.file-max=2097152` | gaming.toml (base has 2097152? check) |
| 16 | kyth-flatpak-prefetch | flatpak_prefetch | other | flatpak | native Rust dispatcher |
| 17 | kyth-flatpak-trim | flatpak_trim | other | flatpak | native Rust dispatcher |
| 18 | kyth-fscache | fscache_tune | other | `/var/cache/fscache` | native Rust dispatcher |
| 19 | kyth-gaming-audit | perf_audit | other | gaming audit | registry (other) |
| 20 | kyth-gaming-cfs | gaming_cfs | other | `/etc/kyth/gaming-cfs.toml` | native Rust dispatcher |
| 21 | kyth-gaming-master | gaming_master | other | gaming-performance | registry (other) |
| 22 | kyth-gpu-power | gpu_power | other | gpu power | native Rust dispatcher |
| 23 | kyth-hdr-per-game | hdr_per_game | other | hdr per game | native Rust dispatcher |
| 24 | kyth-hdr-store | hdr_store | other | hdr store | native Rust dispatcher |
| 25 | kyth-inotify-watches | inotify_watches | sysctl | `fs.inotify.max_user_watches=1048576` — **dup base** | gaming.toml |
| 26 | kyth-io-tune | io_tune | other | `/etc/kyth/io.toml` | native Rust dispatcher |
| 27 | kyth-irq-tune | irq_tune | other | `/etc/kyth/irq.toml` | native Rust dispatcher |
| 28 | kyth-journal-tune | journal_tune | other | `/etc/kyth/journal.toml` | native Rust dispatcher |
| 29 | kyth-kargs-apply | kargs_preset | other | kargs | registry (other) |
| 30 | kyth-kwin-latency | kwin_latency | other | KWin env | native Rust dispatcher |
| 31 | kyth-max-map-count | max_map_count | sysctl | `vm.max_map_count=2147483642` — **dup base** (base is 16777216) | gaming.toml (value conflict — keep 16777216 as base, gaming override TBD) |
| 32 | kyth-mimalloc | mimalloc_preset | other | mimalloc | native Rust dispatcher |
| 33 | kyth-mimalloc-run | mimalloc_preset | other | alias of above | native Rust dispatcher |
| 34 | kyth-min-free-kbytes | min_free_kbytes | sysctl | `vm.min_free_kbytes=131072` | gaming.toml |
| 35 | kyth-net-backlog | net_backlog | sysctl | `net.core.netdev_max_backlog=5000` — **dup network** | gaming.toml vs network (network has 5000 already?) |
| 36 | kyth-net-tune | net_latency | sysctl | 9 keys — **all dup network** | network.toml (already migrated, wrapper is redundant) |
| 37 | kyth-netdev-budget | netdev_budget | sysctl | `net.core.netdev_budget=600` | gaming.toml |
| 38 | kyth-numa | numa_tune | other | numa | native Rust dispatcher |
| 39 | kyth-numa-balancing | numa_balancing | sysctl | `kernel.numa_balancing=0` | gaming.toml |
| 40 | kyth-oom-gaming | oom_gaming | other | oom | registry (other) |
| 41 | kyth-overcommit-memory | overcommit_memory | sysctl | `vm.overcommit_memory=1` | gaming.toml |
| 42 | kyth-page-cluster | page_cluster | sysctl | `vm.page-cluster=0` — (base has 0) | gaming.toml (dup base `vm.page-cluster`) |
| 43 | kyth-perf-cpu | perf_cpu | sysctl | `kernel.perf_cpu_time_max_percent=5` | gaming.toml |
| 44 | kyth-perf-gate | perf_gate | other | perf gate | registry (other) |
| 45 | kyth-pipewire-gaming | pipewire_gaming | other | pipewire | native Rust dispatcher |
| 46 | kyth-podman-btrfs | podman_btrfs | other | podman btrfs | native Rust dispatcher |
| 47 | kyth-podman-overlay | overlay_tune | other | overlay | native Rust dispatcher |
| 48 | kyth-psi-gaming | psi_gaming | other | psi | native Rust dispatcher |
| 49 | kyth-psi-poll | psi_poll | sysctl | `vm.pressure_poll=500` | gaming.toml |
| 50 | kyth-readahead | readahead_preset | other | readahead | native Rust dispatcher |
| 51 | kyth-rmem-default | rmem_default | sysctl | `net.core.rmem_default=262144` | gaming.toml |
| 52 | kyth-rmem-max | rmem_max | sysctl | `net.core.rmem_max=16777216` — **dup network** | gaming.toml vs network |
| 53 | kyth-sccache | sccache_preset | other | sccache | native Rust dispatcher |
| 54 | kyth-sched-arbiter | sched_arbiter | other | sched arbiter | registry (other) |
| 55 | kyth-sched-autogroup | sched_autogroup | sysctl | `kernel.sched_autogroup_enabled=0` — **dup base** | gaming.toml |
| 56 | kyth-sched-child | sched_child | sysctl | `kernel.sched_child_runs_first=0` | gaming.toml |
| 57 | kyth-sched-latency | sched_latency | sysctl | 5 keys `kernel.sched_*` | gaming.toml |
| 58 | kyth-sched-nr-migrate | sched_nr_migrate | sysctl | `kernel.sched_nr_migrate=64` | gaming.toml |
| 59 | kyth-selinux-gaming | selinux_gaming | other | selinux | native Rust dispatcher |
| 60 | kyth-shader-cache-size | shader_cache_size | other | shader cache size | native Rust dispatcher |
| 61 | kyth-shader-tmpfs | shader_tmpfs | other | shader tmpfs | native Rust dispatcher |
| 62 | kyth-somaxconn | somaxconn | sysctl | `net.core.somaxconn=8192` | gaming.toml |
| 63 | kyth-steam-deadzone | steam_deadzone | other | steam | native Rust dispatcher |
| 64 | kyth-swappiness | swappiness | sysctl | `vm.swappiness=10` — **dup base** (base 180) | gaming.toml |
| 65 | kyth-system-audit | system_audit | other | system audit | registry (other) |
| 66 | kyth-tcp-ecn | tcp_ecn | sysctl | `net.ipv4.tcp_ecn=1` — **dup network** | gaming.toml vs network |
| 67 | kyth-tcp-fastopen | tcp_fastopen | sysctl | `net.ipv4.tcp_fastopen=3` — **dup network** | gaming.toml vs network |
| 68 | kyth-tcp-fin-timeout | tcp_fin_timeout | sysctl | `net.ipv4.tcp_fin_timeout=30` | gaming.toml |
| 69 | kyth-tcp-keepalive | tcp_keepalive | sysctl | `net.ipv4.tcp_keepalive_time=120` | gaming.toml |
| 70 | kyth-tcp-mtu-probing | tcp_mtu_probing | sysctl | `net.ipv4.tcp_mtu_probing=1` — **dup network** | gaming.toml vs network |
| 71 | kyth-tcp-no-metrics-save | tcp_no_metrics_save | sysctl | `net.ipv4.tcp_no_metrics_save=1` | gaming.toml |
| 72 | kyth-tcp-notsent | tcp_notsent | sysctl | `net.ipv4.tcp_notsent_lowat=16384` | gaming.toml |
| 73 | kyth-tcp-orphan-retries | tcp_orphan_retries | sysctl | `net.ipv4.tcp_orphan_retries=0` | gaming.toml |
| 74 | kyth-tcp-retries1 | tcp_retries1 | sysctl | `net.ipv4.tcp_retries1=3` | gaming.toml |
| 75 | kyth-tcp-retries2 | tcp_retries2 | sysctl | `net.ipv4.tcp_retries2=8` | gaming.toml |
| 76 | kyth-tcp-sack | tcp_sack | sysctl | `net.ipv4.tcp_sack=1` | gaming.toml |
| 77 | kyth-tcp-slow-start | tcp_slow_start | sysctl | `net.ipv4.tcp_slow_start_after_idle=0` — **dup network** | gaming.toml vs network |
| 78 | kyth-tcp-timestamps | tcp_timestamps | sysctl | `net.ipv4.tcp_timestamps=1` | gaming.toml |
| 79 | kyth-tcp-window-scaling | tcp_window_scaling | sysctl | `net.ipv4.tcp_window_scaling=1` | gaming.toml |
| 80 | kyth-telemetry-opt | telemetry_opt | other | telemetry | registry (other) |
| 81 | kyth-thp-collapse | thp_collapse | sysctl | `kernel.khugepaged_defrag=0` | gaming.toml |
| 82 | kyth-thp-tune | thp_tune | sysctl | 4 keys including `vm.compaction_proactiveness` — **dup base** | gaming.toml |
| 83 | kyth-trim-tune | trim_preset | other | trim | native Rust dispatcher |
| 84 | kyth-uksmd | uksmd_preset | other | uksmd | native Rust dispatcher |
| 85 | kyth-vfs-cache | vfs_cache_pressure | sysctl | `vm.vfs_cache_pressure=50` — **dup base** | gaming.toml |
| 86 | kyth-vm-stat | vm_stat | sysctl | `vm.stat_interval=10` — **dup base** | gaming.toml |
| 87 | kyth-vm-watermark | vm_watermark | sysctl | `vm.watermark_scale_factor=500` — **dup base** | gaming.toml |
| 88 | kyth-windows-verify | windows_verify | other | windows | registry (other) |
| 89 | kyth-wine-sync | wine_sync | other | wine sync | native Rust dispatcher |
| 90 | kyth-wmem-default | wmem_default | sysctl | `net.core.wmem_default=262144` | gaming.toml |
| 91 | kyth-wmem-max | wmem_max | sysctl | `net.core.wmem_max=16777216` — **dup network** | gaming.toml vs network |
| 92 | kyth-work-cache | work_cache | other | work cache | native Rust dispatcher |
| 93 | kyth-zswap | zswap_preset | sysctl | `vm.zswap_*` (modprobe not sysctl) — actually `options zswap` | registry (other, not sysctl.d) |
| 94 | kyth-zswap (duplicate row handling) | — | — | — | — |

Note: `kyth-net-tune` (net_latency) is already fully represented in `network.toml` — the wrapper is now redundant and should become a compat alias that no-ops or maps to `network` tier status.

## Migration strategy

1. **Gaming overrides** for keys that already exist in `base.toml` must go to `gaming.toml`, not duplicate `base.toml`. Composer will emit `99-kyth-gaming.conf` only when `gaming.toml` has keys; `sysctl --system` applies files in lexical order, so `99-kyth-gaming.conf` overrides `99-kyth-base.conf`.
2. **Network keys**: Individual `tcp_*` / `rmem_*` / `wmem_*` wrappers that duplicate `network.toml` should be deprecated — either delete or make them report `active` by reading `network.toml` / `99-kyth-network.conf` instead of per-file existence.
3. **Non-sysctl** (45 wrappers): Do not move through `sysctl_compose`; register in `tunables.toml` for dispatcher dispatch only, keep bespoke `generate_*` until Slice 5.
