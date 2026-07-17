#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── DualSense controller — hidraw userspace access ───────────────────────────
# The hid-playstation kernel module exposes PS5 DualSense haptics and adaptive
# triggers through the hidraw interface.  Without these rules the device node
# is root-only, so Proton/Steam cannot send haptic or trigger commands.
# TAG+="uaccess" grants access to the logged-in seat user automatically via
# systemd-logind — no manual chmod or group membership required.
#
# 054c = Sony Corp vendor ID
# 0ce6 = DualSense (USB and BT)
# 0df2 = DualSense Edge (USB and BT)
cat >/usr/lib/udev/rules.d/99-kyth-dualsense.rules <<'DSEOF'
# DualSense (USB)
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0ce6", SUBSYSTEM=="hidraw", TAG+="uaccess"
# DualSense Edge (USB)
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0df2", SUBSYSTEM=="hidraw", TAG+="uaccess"
# DualSense (Bluetooth — matched via device path rather than idVendor)
KERNEL=="hidraw*", KERNELS=="*054C:0CE6*", TAG+="uaccess"
KERNEL=="hidraw*", KERNELS=="*054C:0DF2*", TAG+="uaccess"
DSEOF
