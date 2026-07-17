#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Systemd Slice Priorities ──────────────────────────────────────────────────
# Prioritizes user session graphical processes and games over background
# system services by adjusting CPU and IO scheduler weights.
mkdir -p /etc/systemd/system/user.slice.d /etc/systemd/system/system.slice.d

cat >/etc/systemd/system/user.slice.d/10-weights.conf <<'EOF'
[Slice]
CPUWeight=1000
IOWeight=1000
EOF

cat >/etc/systemd/system/system.slice.d/10-weights.conf <<'EOF'
[Slice]
CPUWeight=100
IOWeight=100
EOF
