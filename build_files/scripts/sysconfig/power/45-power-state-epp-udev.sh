#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── Power State EPP Scaling ──────────────────────────────────────────────────
# Automates CPU Energy Performance Preference transitions:
# - Performance on AC power for maximum snappiness.
# - Balanced Power on battery to preserve battery life.
write_config /etc/udev/rules.d/99-kyth-power-epp.rules <<'EOF'
SUBSYSTEM=="power_supply", ATTR{online}=="1", RUN+="/usr/bin/kyth-set-epp performance"
SUBSYSTEM=="power_supply", ATTR{online}=="0", RUN+="/usr/bin/kyth-set-epp balance_power"
EOF
