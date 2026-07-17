#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── KWin Realtime Priority ───────────────────────────────────────────────────
# Elevates the Plasma compositor (kwin_wayland) to use real-time scheduling (SCHED_RR).
# This prevents input and window rendering lag under heavy load.
mkdir -p /etc/systemd/user/plasma-kwin_wayland.service.d
cat >/etc/systemd/user/plasma-kwin_wayland.service.d/10-realtime.conf <<'EOF'
[Service]
CPUSchedulingPolicy=rr
CPUSchedulingPriority=50
EOF
