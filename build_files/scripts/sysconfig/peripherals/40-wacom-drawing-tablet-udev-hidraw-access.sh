#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Wacom / drawing tablet — udev hidraw access ───────────────────────────────
# libwacom (installed in packages.sh) provides the tablet database that KWin and
# libinput use on Wayland to map pressure curves correctly. The udev rules below
# grant the logged-in user direct hidraw access so tools like Krita and Blender
# can read raw pressure data without requiring root.
write_config /usr/lib/udev/rules.d/99-kyth-tablets.rules <<'TABLETEOF'
# Wacom tablets — hidraw access for the logged-in user
KERNEL=="hidraw*", ATTRS{idVendor}=="056a", TAG+="uaccess"
# HUION tablets
KERNEL=="hidraw*", ATTRS{idVendor}=="256c", TAG+="uaccess"
# XP-Pen tablets
KERNEL=="hidraw*", ATTRS{idVendor}=="28bd", TAG+="uaccess"
# Gaomon tablets
KERNEL=="hidraw*", ATTRS{idVendor}=="201a", TAG+="uaccess"
TABLETEOF
