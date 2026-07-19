#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── rtkit Audio Priority ─────────────────────────────────────────────────────
# Configures rtkit daemon limits so PipeWire and WirePlumber can reliably claim
# real-time scheduling priority (SCHED_RR) under heavy system load.
mkdir -p /etc/rtkit.conf.d
cat >/etc/rtkit.conf.d/99-kyth.conf <<'EOF'
[Configuration]
MaxRealtimePriority=20
RTTimeMaxUSec=200000
EOF
