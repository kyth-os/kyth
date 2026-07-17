#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── CAKE Network Queueing Discipline ──────────────────────────────────────────
# Switches default network queueing discipline to CAKE to prioritize low-latency
# traffic (gaming/VOIP) over high-bandwidth background transfers.
mkdir -p /etc/sysctl.d
cat >/etc/sysctl.d/99-kyth-network-qdisc.conf <<'EOF'
net.core.default_qdisc = cake
EOF
