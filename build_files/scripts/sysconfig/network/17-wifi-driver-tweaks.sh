#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── WiFi driver tweaks ───────────────────────────────────────────────────────
write_config /etc/modprobe.d/cfg80211-kyth.conf <<'CFG80211EOF'
options cfg80211 ieee80211_regdom=US
CFG80211EOF

# Adapter workarounds are device/driver matched at boot by the hardware policy.
# Keep only the universal regulatory default in the immutable image and remove
# legacy broad overrides during image upgrades.
rm -f \
	/etc/modprobe.d/mt7921-kyth.conf \
	/etc/modprobe.d/iwlwifi-kyth.conf \
	/etc/modprobe.d/iwlmvm-kyth.conf \
	/etc/modprobe.d/btusb-kyth.conf
