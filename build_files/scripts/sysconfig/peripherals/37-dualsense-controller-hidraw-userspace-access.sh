#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Game controllers — hidraw userspace access ────────────────────────────────
# Kernel gamepad drivers expose haptics, adaptive triggers, gyro and LED
# control through the hidraw interface. Without these rules the device nodes
# are root-only, so Proton/Steam cannot send haptic or trigger commands.
# TAG+="uaccess" grants access to the logged-in seat user automatically via
# systemd-logind — no manual chmod or group membership required.
#
# Covers the major vendors, not just Sony: Steam/Proton users plug in Xbox,
# Nintendo, 8BitDo, Logitech and Stadia pads just as often as DualSense.
write_config /usr/lib/udev/rules.d/99-kyth-controllers.rules <<'CTLEOF'
# Sony DualSense (USB) — 054c:0ce6, DualSense Edge (USB) — 054c:0df2
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0ce6", SUBSYSTEM=="hidraw", TAG+="uaccess"
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="0df2", SUBSYSTEM=="hidraw", TAG+="uaccess"
# Sony DualSense (Bluetooth — matched via device path rather than idVendor)
KERNEL=="hidraw*", KERNELS=="*054C:0CE6*", TAG+="uaccess"
KERNEL=="hidraw*", KERNELS=="*054C:0DF2*", TAG+="uaccess"
# Sony DualShock 4 (USB/BT)
KERNEL=="hidraw*", ATTRS{idVendor}=="054c", ATTRS{idProduct}=="09cc", SUBSYSTEM=="hidraw", TAG+="uaccess"
KERNEL=="hidraw*", KERNELS=="*054C:09CC*", TAG+="uaccess"
# Microsoft Xbox controllers (USB) — 045e; wireless adapter — 045e:02e6
KERNEL=="hidraw*", ATTRS{idVendor}=="045e", SUBSYSTEM=="hidraw", TAG+="uaccess"
# Nintendo Switch Pro Controller — 057e:2009; Joy-Con L/R — 057e:2006/2007
KERNEL=="hidraw*", ATTRS{idVendor}=="057e", SUBSYSTEM=="hidraw", TAG+="uaccess"
# Logitech gamepads (F310/F710/rumble) — 046d
KERNEL=="hidraw*", ATTRS{idVendor}=="046d", SUBSYSTEM=="hidraw", TAG+="uaccess"
# Valve Steam Controller / Steam Deck — 28de
KERNEL=="hidraw*", ATTRS{idVendor}=="28de", SUBSYSTEM=="hidraw", TAG+="uaccess"
# 8BitDo — 2dc8
KERNEL=="hidraw*", ATTRS{idVendor}=="2dc8", SUBSYSTEM=="hidraw", TAG+="uaccess"
# Google Stadia controller — 18d1:9400
KERNEL=="hidraw*", ATTRS{idVendor}=="18d1", ATTRS{idProduct}=="9400", SUBSYSTEM=="hidraw", TAG+="uaccess"
CTLEOF
# Superseded Sony-only filename from earlier images.
rm -f /usr/lib/udev/rules.d/99-kyth-dualsense.rules
