# Run a game or app with the temporary performance profile wrapper.
[group('KythOS')]
game-performance +args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/game-performance {{ args }}

# Set desktop/system performance mode.

# Modes: max, gaming, performance, balanced, powersave, status
# Fix 10: direct exec avoids extra bash fork (was 3 forks per toggle)
[group('KythOS')]
performance-mode mode="status":
    exec /usr/bin/kyth-performance-mode "{{ mode }}"

# Quick shortcut: switch to gaming mode (EPP=performance, half-speed animations, no blur).
[group('KythOS')]
gaming-mode:
    exec /usr/bin/kyth-performance-mode gaming

# Quick shortcut: restore balanced mode (EPP=balance_performance, full animations).
[group('KythOS')]
balanced-mode:
    exec /usr/bin/kyth-performance-mode balanced

# Run a command with a named temporary profile.
[group('KythOS')]
game-performance-profile profile +args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/game-performance --profile "{{ profile }}" {{ args }}

# Run a game or app inside gamescope (adaptive sync + frame pacing, no HDR).
# Useful even without HDR: better VRR, FSR upscaling, frame limiter.
# Usage: ujust gamescope -- %command%
#        ujust gamescope -W 2560 -H 1440 -r 165 -- %command%

# Extra gamescope flags can be passed before the -- separator.
[group('KythOS')]
gamescope +args:
    #!/usr/bin/env bash
    set -euo pipefail
    exec /usr/bin/kyth-gamescope quality {{ args }}

# Run a game or app inside gamescope with HDR enabled.
# Requires an HDR-capable display and a Wayland session.
# Note: --hdr-itm-enable (SDR→HDR tone mapping) is intentionally omitted —
#       it makes SDR content look over-saturated. Add it manually if you want it:
#       ujust game-hdr --hdr-itm-enable -- %command%
# Usage: ujust game-hdr -- %command%

# ujust game-hdr -W 2560 -H 1440 -- %command%
[group('KythOS')]
game-hdr +args:
    #!/usr/bin/env bash
    set -euo pipefail
    exec /usr/bin/kyth-gamescope hdr {{ args }}

# Run a game or app with KythOS Gamescope presets.
# Usage:
#   ujust game-scope quality -- %command%
#   ujust game-scope hdr --fps 120 -- %command%
# ujust game-scope sharp --fsr --nested 1920x1080 --output 2560x1440 -- %command%
[group('KythOS')]
game-scope preset="quality" *args:
    #!/usr/bin/env bash
    set -euo pipefail
    exec /usr/bin/kyth-gamescope "{{ preset }}" {{ args }}

# Show or change the active sched-ext scheduler.
# Usage: ujust scx status | ujust scx list | ujust scx set rusty
[group('KythOS')]
scx action="status" scheduler="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [[ -n "{{ scheduler }}" ]]; then
        /usr/bin/kyth-scx "{{ action }}" "{{ scheduler }}"
    else
        /usr/bin/kyth-scx "{{ action }}"
    fi

# Show or change the experimental NVMe queue tuning profile.
# Usage: ujust nvme-tuning status | ujust nvme-tuning kyth | ujust nvme-tuning default
[group('KythOS')]
nvme-tuning profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-nvme-tuning "{{ profile }}"

# I/O tune (io.toml) — declarative udev for NVMe+SATA, offline
[group('KythOS')]
io-tune profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-io-tune "{{ profile }}"

# Kargs perf profile (kargs.toml) — rpm-ostree kargs, revertible
[group('KythOS')]
kargs-apply profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-kargs-apply "{{ profile }}"

# Net latency (net-latency.toml) — BBR+FQ+tcp_fastopen, gaming opt-in
[group('KythOS')]
net-tune mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-net-tune "{{ mode }}"

# UKSMD dedup (uksmd.toml) — 15-30% RAM save on >16GB, idle zero when off
[group('KythOS')]
uksmd mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-uksmd "{{ mode }}"

# Journal slim (journal.toml) — 200M/64M perf vs 500M base, offline
[group('KythOS')]
journal-tune mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-journal-tune "{{ mode }}"

# THP khugepaged (thp.toml) — madvise + scan 10s, cuts UE stutter
[group('KythOS')]
thp-tune profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-thp-tune "{{ profile }}"

# Mimalloc per-game (mimalloc.toml) — 10-20% p95, no global cost
[group('KythOS')]
mimalloc mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-mimalloc "{{ mode }}"

# Mimalloc wrapper — run game with mimalloc
[group('KythOS')]
mimalloc-run +args:
    #!/usr/bin/env bash
    set -euo pipefail
    exec /usr/bin/kyth-mimalloc-run {{ args }}

# IRQ affinity (irq.toml) — GPU/NVMe off X3D CCD0
[group('KythOS')]
irq-tune profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-irq-tune "{{ profile }}"

# Btrfs mount perf (btrfs-perf.toml) — zstd:1 + noatime
[group('KythOS')]
btrfs-tune profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-btrfs-tune "{{ profile }}"

# Trim nodiscard + fstrim weekly (trim.toml)
[group('KythOS')]
trim-tune profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-trim-tune "{{ profile }}"

# Ananicy gaming nice (ananicy.toml) — cgroup realtime
[group('KythOS')]
ananicy profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-ananicy "{{ profile }}"

# Zswap tier (zswap.toml) — complements zram on <16GB
[group('KythOS')]
zswap profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-zswap "{{ profile }}"

# GPU DPM perf (gpu-power.toml) — high vs auto
[group('KythOS')]
gpu-power profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-gpu-power "{{ profile }}"

# Sched latency (sched-latency.toml) — 6ms gaming jitter cut
[group('KythOS')]
sched-latency profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-sched-latency "{{ profile }}"

# Readahead ephemeral (readahead.toml)
[group('KythOS')]
readahead path="":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-readahead "{{ path }}"

[group('KythOS')]
readahead-run +args:
    #!/usr/bin/env bash
    set -euo pipefail
    exec /usr/bin/kyth-readahead-run {{ args }}

# Master gaming (gaming-performance.toml) — one toggle for 46-60
[group('KythOS')]
gaming-master profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-gaming-master "{{ profile }}"

# Wine sync (wine-sync.toml) — NTSync/futex2 auto
[group('KythOS')]
wine-sync mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-wine-sync "{{ mode }}"

# KWin latency (kwin-latency.toml) — tearing/MaxFPS for VRR
[group('KythOS')]
kwin-latency profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-kwin-latency "{{ profile }}"

# PipeWire gaming quantum (pipewire-gaming.toml)
[group('KythOS')]
pipewire-gaming profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-pipewire-gaming "{{ profile }}"

# Btrfs autotune weekly (btrfs-autotune.toml)
[group('KythOS')]
btrfs-autotune mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-btrfs-autotune "{{ mode }}"

# Boot fast-path (loader.toml) — 0s vs 2s greenboot
[group('KythOS')]
boot-timeout mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-boot-timeout "{{ mode }}"

# OOM gaming guard (oom-gaming.toml) — 75% vs 50%
[group('KythOS')]
oom-gaming profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-oom-gaming "{{ profile }}"

# Shader cache tmpfs (shader-tmpfs.toml) — 2G tmpfs
[group('KythOS')]
shader-tmpfs mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-shader-tmpfs "{{ mode }}"

# Gaming CFS burst (gaming-cfs.toml) — 400% CPUQuota
[group('KythOS')]
gaming-cfs profile="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-gaming-cfs "{{ profile }}"

# Perf audit — 46-70 + systemd-analyze + budget
[group('KythOS')]
gaming-audit mode="":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-gaming-audit {{ mode }}

# Steam deadzone 5% gaming (steam-deadzone.toml)
[group('KythOS')]
steam-deadzone mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-steam-deadzone "{{ mode }}"

# SELinux gaming allow_execheap (selinux-gaming.toml)
[group('KythOS')]
selinux-gaming mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-selinux-gaming "{{ mode }}"

# Fcitx5 latency 10ms gaming (fcitx-latency.toml)
[group('KythOS')]
fcitx-latency mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-fcitx-latency "{{ mode }}"

# HDR store preserve (hdr-store.toml)
[group('KythOS')]
hdr-store mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-hdr-store "{{ mode }}"

# System audit — ledger + snapshot + trim
[group('KythOS')]
system-audit:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-system-audit

# PSI gaming 90% avoid (psi.toml)
[group('KythOS')]
psi-gaming mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-psi-gaming "{{ mode }}"

# NUMA X3D CCD0 (numa.toml)
[group('KythOS')]
numa mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-numa "{{ mode }}"

# PCIe ASPM L1 off gaming (pcie.toml)
[group('KythOS')]
pcie mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-pcie "{{ mode }}"

# THP collapse defrag 0 gaming (thp-collapse.toml)
[group('KythOS')]
thp-collapse mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-thp-collapse "{{ mode }}"

# PSI poll 500ms gaming (psi-poll.toml)
[group('KythOS')]
psi-poll mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-psi-poll "{{ mode }}"

# Compaction 0 gaming (compaction.toml)
[group('KythOS')]
compaction mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-compaction "{{ mode }}"

# FSCache 10G (fscache.toml)
[group('KythOS')]
fscache mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-fscache "{{ mode }}"

# HDR per-game peak (hdr-per-game.toml)
[group('KythOS')]
hdr-per-game:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-hdr-per-game

# Bore sched_bore=1 gaming (bore.toml)
[group('KythOS')]
bore mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-bore "{{ mode }}"

# Shader cache auto 2G/4G (shader-cache-size.toml)
[group('KythOS')]
shader-cache-size mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-shader-cache-size "{{ mode }}"

# Overlay metacopy=on btrfs (podman-overlay.toml)
[group('KythOS')]
podman-overlay mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-podman-overlay "{{ mode }}"

# Net backlog 5000 gaming (net-backlog.toml)
[group('KythOS')]
net-backlog mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-net-backlog "{{ mode }}"

# VM watermark 500 gaming (vm-watermark.toml)
[group('KythOS')]
vm-watermark mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-vm-watermark "{{ mode }}"

# TCP notsent 16384 gaming (tcp-notsent.toml)
[group('KythOS')]
tcp-notsent mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-notsent "{{ mode }}"

# max_map_count 2G gaming (max-map-count.toml)
[group('KythOS')]
max-map-count mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-max-map-count "{{ mode }}"

# Dirty ratio 5/5 gaming (dirty-ratio.toml)
[group('KythOS')]
dirty-ratio mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-dirty-ratio "{{ mode }}"

# VFS cache 50 gaming (vfs-cache.toml)
[group('KythOS')]
vfs-cache mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-vfs-cache "{{ mode }}"

# TCP ECN 1 gaming (tcp-ecn.toml)
[group('KythOS')]
tcp-ecn mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-ecn "{{ mode }}"

# TCP slow start 0 gaming (tcp-slow-start.toml)
[group('KythOS')]
tcp-slow-start mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-slow-start "{{ mode }}"

# Sched autogroup 0 gaming (sched-autogroup.toml)
[group('KythOS')]
sched-autogroup mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-sched-autogroup "{{ mode }}"

# Sched nr_migrate 64 gaming (sched-nr-migrate.toml)
[group('KythOS')]
sched-nr-migrate mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-sched-nr-migrate "{{ mode }}"

# Page cluster 0 gaming (page-cluster.toml)
[group('KythOS')]
page-cluster mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-page-cluster "{{ mode }}"

# TCP retries2 8 gaming (tcp-retries2.toml)
[group('KythOS')]
tcp-retries2 mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-retries2 "{{ mode }}"

# TCP keepalive 120 gaming (tcp-keepalive.toml)
[group('KythOS')]
tcp-keepalive mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-keepalive "{{ mode }}"

# Sched child runs first 0 gaming (sched-child.toml)
[group('KythOS')]
sched-child mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-sched-child "{{ mode }}"

# VM stat 10 gaming (vm-stat.toml)
[group('KythOS')]
vm-stat mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-vm-stat "{{ mode }}"

# Numa balancing 0 gaming (numa-balancing.toml)
[group('KythOS')]
numa-balancing mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-numa-balancing "{{ mode }}"

# TCP fastopen 3 gaming (tcp-fastopen.toml)
[group('KythOS')]
tcp-fastopen mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-fastopen "{{ mode }}"

# TCP mtu probing 1 gaming (tcp-mtu-probing.toml)
[group('KythOS')]
tcp-mtu-probing mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-mtu-probing "{{ mode }}"

# Dirty expire 100 gaming (dirty-expire.toml)
[group('KythOS')]
dirty-expire mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-dirty-expire "{{ mode }}"

# File max 2097152 gaming (file-max.toml)
[group('KythOS')]
file-max mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-file-max "{{ mode }}"

# Perf cpu 5 gaming (perf-cpu.toml)
[group('KythOS')]
perf-cpu mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-perf-cpu "{{ mode }}"

# Swappiness 10 gaming (swappiness.toml)
[group('KythOS')]
swappiness mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-swappiness "{{ mode }}"

# TCP fin timeout 30 gaming (tcp-fin-timeout.toml)
[group('KythOS')]
tcp-fin-timeout mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-fin-timeout "{{ mode }}"

# Somaxconn 8192 gaming (somaxconn.toml)
[group('KythOS')]
somaxconn mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-somaxconn "{{ mode }}"

# Inotify watches 1048576 gaming (inotify-watches.toml)
[group('KythOS')]
inotify-watches mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-inotify-watches "{{ mode }}"

# Min free kbytes 131072 gaming (min-free-kbytes.toml)
[group('KythOS')]
min-free-kbytes mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-min-free-kbytes "{{ mode }}"

# Rmem max 16777216 gaming (rmem-max.toml)
[group('KythOS')]
rmem-max mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-rmem-max "{{ mode }}"

# Wmem max 16777216 gaming (wmem-max.toml)
[group('KythOS')]
wmem-max mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-wmem-max "{{ mode }}"

# Aio max 1048576 gaming (aio-max.toml)
[group('KythOS')]
aio-max mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-aio-max "{{ mode }}"

# Overcommit memory 1 gaming (overcommit-memory.toml)
[group('KythOS')]
overcommit-memory mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-overcommit-memory "{{ mode }}"

# Netdev budget 600 gaming (netdev-budget.toml)
[group('KythOS')]
netdev-budget mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-netdev-budget "{{ mode }}"

# Rmem default 262144 gaming (rmem-default.toml)
[group('KythOS')]
rmem-default mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-rmem-default "{{ mode }}"

# Wmem default 262144 gaming (wmem-default.toml)
[group('KythOS')]
wmem-default mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-wmem-default "{{ mode }}"

# Tcp window scaling 1 gaming (tcp-window-scaling.toml)
[group('KythOS')]
tcp-window-scaling mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-window-scaling "{{ mode }}"

# Tcp sack 1 gaming (tcp-sack.toml)
[group('KythOS')]
tcp-sack mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-sack "{{ mode }}"

# Tcp timestamps 1 gaming (tcp-timestamps.toml)
[group('KythOS')]
tcp-timestamps mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-timestamps "{{ mode }}"

# Busy read 50 gaming (busy-read.toml)
[group('KythOS')]
busy-read mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-busy-read "{{ mode }}"

# Busy poll 50 gaming (busy-poll.toml)
[group('KythOS')]
busy-poll mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-busy-poll "{{ mode }}"

# Tcp no metrics save 1 gaming (tcp-no-metrics-save.toml)
[group('KythOS')]
tcp-no-metrics-save mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-no-metrics-save "{{ mode }}"

# Tcp retries1 3 gaming (tcp-retries1.toml)
[group('KythOS')]
tcp-retries1 mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-retries1 "{{ mode }}"

# Tcp orphan retries 0 gaming (tcp-orphan-retries.toml)
[group('KythOS')]
tcp-orphan-retries mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-tcp-orphan-retries "{{ mode }}"

# EPP AC performance vs balanced (epp-ac.toml)
[group('KythOS')]
epp-ac mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-epp-ac "{{ mode }}"

# Run an OpenGL app through Zink.
[group('KythOS')]
zink-run +args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/zink-run {{ args }}

# Run a game with the Vulkan low-latency layer (Anti-Lag 2 / Reflex on any GPU).
# Exposes VK_AMD_anti_lag by default; pass --reflex for VK_NV_low_latency2.
# Also works as a Steam launch option: LOW_LATENCY_LAYER=1 %command%
# Usage: ujust low-latency -- %command%

# ujust low-latency --reflex -- %command%
[group('KythOS')]
low-latency +args:
    #!/usr/bin/env bash
    set -euo pipefail
    exec /usr/bin/low-latency-run {{ args }}

# EXPERIMENTAL: install bpftune, an eBPF daemon that continuously retunes
# live kernel parameters (TCP buffers, neighbor tables, sysctls…) based on
# observed load. Unlike every kyth-tunable, it is not declarative or
# offline — it keeps adjusting things while running, which can fight
# whatever the tunables above already set (Clean Perf / Master Gaming /
# Net latency in particular). No official Fedora/EPEL package exists;
# this layers it from a third-party COPR (crono/bpftune-gaming) on
# request only — never automatically, and never enabled by default.
[group('KythOS')]
enable-bpftune:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "━━━ bpftune — EXPERIMENTAL ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "  bpftune continuously auto-tunes kernel parameters via eBPF."
    echo "  It is NOT one of KythOS's own declarative tunables and can fight"
    echo "  with them (Clean Perf, Master Gaming, Net latency especially)."
    echo "  Source: a third-party COPR (crono/bpftune-gaming), not an"
    echo "  official Fedora/EPEL package."
    echo
    read -r -p "  Continue? [y/N] " reply
    if [[ ! "${reply}" =~ ^[Yy]$ ]]; then
        echo "  Cancelled — nothing changed."
        exit 0
    fi
    sudo dnf5 copr enable -y crono/bpftune-gaming
    sudo rpm-ostree install --idempotent bpftune
    sudo dnf5 copr disable -y crono/bpftune-gaming
    echo
    echo "  Staged. Reboot, then: sudo systemctl enable --now bpftune.service"
    echo "  To remove it later: ujust disable-bpftune"

# Stop and remove bpftune (see enable-bpftune above).
[group('KythOS')]
disable-bpftune:
    #!/usr/bin/env bash
    set -euo pipefail
    sudo systemctl disable --now bpftune.service 2>/dev/null || true
    sudo rpm-ostree uninstall --idempotent bpftune
    echo "Removed. Reboot to finish rolling it back."
