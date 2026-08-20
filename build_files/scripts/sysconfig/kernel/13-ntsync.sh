#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── NTSYNC ───────────────────────────────────────────────────────────
# Custom kernels may ship ntsync. The udev rule gives the 'users' group access
# to /dev/ntsync so Wine/Proton can use NT synchronization primitives when the
# module is available.
write_line 'ntsync' /usr/lib/modules-load.d/kyth-ntsync.conf
write_line 'KERNEL=="ntsync", GROUP="users", MODE="0660"' /usr/lib/udev/rules.d/99-ntsync.rules

# zram-size capped at 8 GiB: matches Fedora zram-generator-defaults (min(ram, 8192))
# and memory_tune.py tiers. Uncapped `ram` on 64 GiB hosts creates a 62 GiB
# zram device whose dev-zram0.device job times out for 45s at boot
# (6.5s -> 51.5s: "Timed out waiting for device dev-zram0.device"), then
# retries instantly. Fedora default avoids the stall; high-RAM hosts can
# still get uncapped ram via memory_tune.py at runtime.
# swap-priority=100 ensures zram is always chosen over any disk swap.
write_config /etc/systemd/zram-generator.conf <<'ZRAMEOF'
[zram0]
zram-size = min(ram, 8192)
compression-algorithm = zstd
swap-priority = 100
ZRAMEOF

# systemd waits for dev-zram0.device via udev; extend its job timeout so
# the initial cold-boot race does not log as a failure before the module
# creates the device (observed: timeout at 90s then success 1s later).
mkdir -p /etc/systemd/system/dev-zram0.device.d
cat > /etc/systemd/system/dev-zram0.device.d/10-timeout.conf <<'DEVTIMEOUT'
[Unit]
JobTimeoutSec=180
DEVTIMEOUT
