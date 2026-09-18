#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── User Limits for Gaming (Fsync/ESync) ──────────────────────────────────────
# Raises NOFILE (open files) for Wine/Proton fast synchronization globally —
# esync needs it in every session where Wine can run.
#
# MEMLOCK (locked, non-swappable memory) is scoped to the game slice instead:
# unbounded MEMLOCK is non-swappable and non-reclaimable by the kernel, which
# works directly against the sysconfig/systemd/03-systemd-oomd-hardening.sh
# rationale of avoiding sudden low-memory OOM kills. Games run inside
# gaming.slice via kyth-game-launch, so the slice carries the relaxation and
# ordinary login sessions keep the safe default.
write_config /etc/systemd/system.conf.d/99-game-limits.conf <<'EOF'
[Manager]
DefaultLimitNOFILE=1048576
EOF

write_config /etc/systemd/user.conf.d/99-game-limits.conf <<'EOF'
[Manager]
DefaultLimitNOFILE=1048576
EOF

write_config /etc/systemd/system/gaming.slice.d/10-game-limits.conf <<'EOF'
[Slice]
# Game slice only: pinned GPU buffers need locked memory; nowhere else does.
LimitNOFILE=1048576
LimitMEMLOCK=infinity
EOF
