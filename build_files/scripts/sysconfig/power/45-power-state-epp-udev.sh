#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Power State EPP Scaling ──────────────────────────────────────────────────
# Automates CPU Energy Performance Preference transitions:
# - Performance on AC power for maximum snappiness.
# - Balanced Power on battery to preserve battery life.
write_config /etc/udev/rules.d/99-kyth-power-epp.rules <<'EOF'
# Debounced via kyth-power-arbiter.service to coalesce per-second power_supply events
SUBSYSTEM=="power_supply", ATTR{online}=="1", TAG+="systemd", ENV{SYSTEMD_WANTS}="kyth-power-arbiter.service"
SUBSYSTEM=="power_supply", ATTR{online}=="0", TAG+="systemd", ENV{SYSTEMD_WANTS}="kyth-power-arbiter.service"
EOF
# Install arbiter (single writer)
install -m 0755 /ctx/kyth-power-arbiter /usr/bin/kyth-power-arbiter
install -m 0644 /ctx/kyth-power-arbiter.service /usr/lib/systemd/system/kyth-power-arbiter.service
