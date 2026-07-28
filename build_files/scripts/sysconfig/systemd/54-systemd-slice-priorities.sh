#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── Systemd Slice Priorities ──────────────────────────────────────────────────
# Prioritizes user session graphical processes and games over background
# system services by adjusting CPU and IO scheduler weights.
write_config /etc/systemd/system/user.slice.d/10-weights.conf <<'EOF'
[Slice]
CPUWeight=1000
IOWeight=1000
EOF

write_config /etc/systemd/system/system.slice.d/10-weights.conf <<'EOF'
[Slice]
CPUWeight=100
IOWeight=100
EOF
