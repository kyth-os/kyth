#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── User Limits for Gaming (Fsync/ESync) ──────────────────────────────────────
# Raises NOFILE (open files) and MEMLOCK (locked memory) limits system-wide
# to ensure Wine/Proton can utilize fast synchronization.
mkdir -p /etc/systemd/system.conf.d /etc/systemd/user.conf.d

cat >/etc/systemd/system.conf.d/99-game-limits.conf <<'EOF'
[Manager]
DefaultLimitNOFILE=1048576
DefaultLimitMEMLOCK=infinity
EOF

cat >/etc/systemd/user.conf.d/99-game-limits.conf <<'EOF'
[Manager]
DefaultLimitNOFILE=1048576
DefaultLimitMEMLOCK=infinity
EOF
