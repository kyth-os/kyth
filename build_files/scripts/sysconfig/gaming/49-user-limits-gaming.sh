#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── User Limits for Gaming (Fsync/ESync) ──────────────────────────────────────
# Raises NOFILE (open files) for Wine/Proton fast synchronization, and MEMLOCK
# (locked, non-swappable memory) for GPU driver features that pin buffers.
#
# MEMLOCK is only raised for the user manager (interactive login sessions,
# where games actually run), not the system manager. Unbounded MEMLOCK is
# non-swappable and non-reclaimable by the kernel, which works directly
# against the sysconfig/systemd/03-systemd-oomd-hardening.sh rationale of avoiding
# sudden low-memory OOM kills — raising it for every root-level system
# service too (which never needs it) would widen that risk for no gaming
# benefit, so system.conf.d only gets the NOFILE bump.
write_config /etc/systemd/system.conf.d/99-game-limits.conf <<'EOF'
[Manager]
DefaultLimitNOFILE=1048576
EOF

write_config /etc/systemd/user.conf.d/99-game-limits.conf <<'EOF'
[Manager]
DefaultLimitNOFILE=1048576
DefaultLimitMEMLOCK=infinity
EOF
