#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── OpenRGB — RGB peripheral control ─────────────────────────────────────────
# OpenRGB ships its own udev rules file that grants access to LED controllers
# via i2c, hidraw, and USB. The package installs them to /usr/lib/udev/rules.d/
# automatically; this block adds an XDG autostart entry so RGB profiles are
# applied at login without the user having to launch OpenRGB manually.
# The --noGui --startminimized flags load the saved profile and stay in the tray.
mkdir -p /etc/skel/.config/autostart
cat >/etc/skel/.config/autostart/openrgb.desktop <<'ORGBEOF'
[Desktop Entry]
Type=Application
Name=OpenRGB
Comment=Apply saved RGB profile at login
Exec=openrgb --noGui --startminimized
Icon=openrgb
Terminal=false
X-KDE-autostart-condition=false
ORGBEOF
