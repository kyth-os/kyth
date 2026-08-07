# Run a game or app with the temporary performance profile wrapper.
[group('KythOS')]
game-performance +args:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/game-performance {{ args }}

# Set desktop/system performance mode.

# Modes: max, gaming, performance, balanced, powersave, status
[group('KythOS')]
performance-mode mode="status":
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-performance-mode "{{ mode }}"

# Quick shortcut: switch to gaming mode (EPP=performance, half-speed animations, no blur).
[group('KythOS')]
gaming-mode:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-performance-mode gaming

# Quick shortcut: restore balanced mode (EPP=balance_performance, full animations).
[group('KythOS')]
balanced-mode:
    #!/usr/bin/env bash
    set -euo pipefail
    /usr/bin/kyth-performance-mode balanced

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
