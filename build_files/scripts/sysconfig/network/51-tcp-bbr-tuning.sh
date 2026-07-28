#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── TCP BBRv3 Congestion Tuning ──────────────────────────────────────────────
# Enables Explicit Congestion Notification (ECN) and disables slow start after idle
# to minimize bufferbloat and network latency spikes.
write_config /etc/sysctl.d/99-kyth-network.conf <<'EOF'
net.ipv4.tcp_ecn = 1
net.ipv4.tcp_slow_start_after_idle = 0
EOF
