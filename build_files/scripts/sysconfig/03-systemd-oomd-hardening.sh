#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── systemd-oomd hardening ────────────────────────────────────────────────────
# By default systemd-oomd runs but monitors nothing — cgroups must explicitly
# opt in with ManagedOOMSwap/ManagedOOMMemoryPressure. Without these, oomd sits
# idle while the kernel OOM killer fires, which kills whatever happened to
# trigger the allocation (often dbus-broker, Xwayland, or plasmashell) rather
# than the actual memory hog — causing instant black screens.
#
# Thresholds are tuned for a gaming workload on a low-RAM system (≤16 GB):
# - 50% pressure / 15 s (old defaults) fires during every game loading screen
#   because shader compilation and asset streaming routinely sustain high
#   pressure for 20–40 s. That caused premature browser tab and app kills that
#   look like "memory crashes" but aren't OOM — just oomd misfiring.
# - 65% pressure / 40 s gives games room to burst through loading spikes while
#   still catching genuine runaway processes well before the kernel OOM killer.
# - SwapUsedLimit raised to 85%: zram compresses at ~3:1, so 85% of 14 GB of
#   zram logical capacity still leaves physical RAM available for decompression.
mkdir -p /etc/systemd/oomd.conf.d
cat >/etc/systemd/oomd.conf.d/99-kyth.conf <<'OOMDEOF'
[OOM]
SwapUsedLimit=85%
DefaultMemoryPressureLimit=65%
DefaultMemoryPressureDurationSec=40s
OOMDEOF

# Opt the user session slice into oomd monitoring. oomd will select and kill
# the highest-OOM-score process inside user.slice when thresholds are breached,
# sparing session-critical processes like dbus-broker and plasmashell.
mkdir -p /etc/systemd/system/user.slice.d
cat >/etc/systemd/system/user.slice.d/10-oomd-user.conf <<'OOMDSLICEEOF'
[Slice]
ManagedOOMSwap=kill
ManagedOOMMemoryPressure=kill
ManagedOOMMemoryPressureLimit=65%
OOMDSLICEEOF

