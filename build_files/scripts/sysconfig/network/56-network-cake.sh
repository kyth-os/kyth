#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── CAKE Network Queueing Discipline ──────────────────────────────────────────
# Switches default network queueing discipline to CAKE to prioritize low-latency
# traffic (gaming/VOIP) over high-bandwidth background transfers. CAKE does its
# own internal pacing, so it's compatible with the net.ipv4.tcp_congestion_control
# = bbr set in build_files/data/sysctl.d/99-kyth.conf — that file intentionally
# does NOT also set default_qdisc; this is the only file that owns that key.
mkdir -p /etc/sysctl.d
cat >/etc/sysctl.d/99-kyth-network-qdisc.conf <<'EOF'
net.core.default_qdisc = cake
EOF
