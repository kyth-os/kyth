#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── ASUS Linux hardware control ───────────────────────────────────────────────
# asusctl/asusd expose ASUS ROG/TUF/Zephyrus/ProArt controls such as platform
# profiles, battery charge limits, fan curves, keyboard lighting, and newer
# Armoury firmware attributes. supergfxctl provides hybrid/dGPU mode management
# for supported ASUS laptops. The upstream asusd udev rules are DMI-gated, and
# Kyth adds a matching supergfxd udev rule in the branding layer.
dnf5 install -y --skip-unavailable \
	asusctl \
	supergfxctl || true
systemctl disable supergfxd.service 2>/dev/null || true
rm -f /etc/systemd/system/getty.target.wants/supergfxd.service

# asusd/supergfxd ship D-Bus policy files hardcoded to group="sudo" (an
# Ubuntu/Pop!_OS convention). Fedora's admin group is "wheel", not "sudo", so
# dbus-broker rejects that policy line outright on every boot:
#   Invalid group-name in .../asusd.conf +9: group="sudo"
# Rewrite to the group that actually exists here.
for dbus_policy in \
	/usr/share/dbus-1/system.d/asusd.conf \
	/etc/dbus-1/system.d/org.supergfxctl.Daemon.conf; do
	[[ -f "${dbus_policy}" ]] && sed -i 's/group="sudo"/group="wheel"/' "${dbus_policy}"
done
