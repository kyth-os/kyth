#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── rtkit Audio Priority ─────────────────────────────────────────────────────
# Configures rtkit daemon limits so PipeWire and WirePlumber can reliably claim
# real-time scheduling priority (SCHED_RR) under heavy system load.
write_config /etc/rtkit.conf.d/99-kyth.conf <<'EOF'
[Configuration]
MaxRealtimePriority=20
RTTimeMaxUSec=200000
EOF
