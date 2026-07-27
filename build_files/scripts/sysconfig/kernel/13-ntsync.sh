#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── NTSYNC ───────────────────────────────────────────────────────────
# Custom kernels may ship ntsync. The udev rule gives the 'users' group access
# to /dev/ntsync so Wine/Proton can use NT synchronization primitives when the
# module is available.
write_line 'ntsync' /usr/lib/modules-load.d/kyth-ntsync.conf
write_line 'KERNEL=="ntsync", GROUP="users", MODE="0660"' /usr/lib/udev/rules.d/99-ntsync.rules

# zram-size = ram: logical size equals physical RAM.
# With zram present, the logical size is not static physical overhead; it grows
# lazily. Compressed pages at ~3:1 zstd ratio mean a full zram swap uses only
# ~1/3 of its capacity in physical RAM, offering a massive buffer that prevents
# lockups/OOM-kills during heavy compilation or AAA gaming.
# swap-priority=100 ensures zram is always chosen over any disk swap.
write_config /etc/systemd/zram-generator.conf <<'ZRAMEOF'
[zram0]
zram-size = ram
compression-algorithm = zstd
swap-priority = 100
ZRAMEOF
