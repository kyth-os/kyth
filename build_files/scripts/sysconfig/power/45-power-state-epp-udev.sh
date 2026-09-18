#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Power State EPP Scaling ──────────────────────────────────────────────────
# Single power owner: power-profiles-daemon (PPD). The profile (performance /
# balanced / power-saver, via powerprofilesctl) is the one knob everything
# else follows:
#   - kyth-power-arbiter translates AC/battery/game events into PPD profiles.
#   - EPP is a follower: kyth_shared.epp_ac generates PPD-setting udev rules
#     (never raw sysfs writes), and kyth-performance-mode / kyth_shared
#     performance.apply_power_owner set EPP from the active PPD profile.
# Nothing else writes energy_performance_preference directly.
write_config /etc/udev/rules.d/99-kyth-power-epp.rules <<'EOF'
# Debounced via kyth-power-arbiter.service to coalesce per-second power_supply events
SUBSYSTEM=="power_supply", ATTR{online}=="1", TAG+="systemd", ENV{SYSTEMD_WANTS}="kyth-power-arbiter.service"
SUBSYSTEM=="power_supply", ATTR{online}=="0", TAG+="systemd", ENV{SYSTEMD_WANTS}="kyth-power-arbiter.service"
EOF
# Install arbiter (single writer)
install -m 0755 /ctx/kyth-power-arbiter /usr/bin/kyth-power-arbiter
install -m 0644 /ctx/kyth-power-arbiter.service /usr/lib/systemd/system/kyth-power-arbiter.service
