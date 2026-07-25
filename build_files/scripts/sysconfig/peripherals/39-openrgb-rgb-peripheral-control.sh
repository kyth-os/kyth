#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── OpenRGB — RGB peripheral control ─────────────────────────────────────────
# OpenRGB ships its own udev rules file that grants access to LED controllers
# via i2c, hidraw, and USB. The package installs them to /usr/lib/udev/rules.d/
# automatically. Do not start the GUI unconditionally at login: OpenRGB probes
# hardware aggressively and has crashed on systems with no configured profile.
# Users who want profile restoration can enable OpenRGB's own autostart setting.
rm -f /etc/skel/.config/autostart/openrgb.desktop
