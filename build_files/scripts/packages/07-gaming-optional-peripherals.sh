#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# shellcheck source=../lib/packages-helpers.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/../lib/packages-helpers.sh"

# ── Optional PC gaming peripheral stack ──────────────────────────────────────
# Keep these out of the core gaming transaction. They come from a mix of Fedora,
# RPM Fusion, COPRs, and fast-moving driver packages; if one has a temporary
# dependency conflict or mirror outage, the image should still ship the core
# Steam/Gamescope/MangoHud/GameMode stack. Install these together normally, then
# retry individually if one flaky package prevents the batch from landing.
optional_gaming_packages=(
	rom-properties-kf6
	game-devices-udev
	xpadneo
	xone
	dualsensectl
	jstest-gtk
	libcec
	cec-utils
	openrazer-daemon
	openrazer-meta
	opentabletdriver
	corectrl
	akmod-v4l2loopback
	v4l2loopback
	v4l-utils
	joycond
	gamescope-session-plus
	openrgb
	libwacom
	libwacom-data
	hplip
	ryzenadj
	i2c-tools
	lm_sensors
	sunshine
	extest
	extest.i686
	# Vulkan / GL debugging: vulkaninfo, glxinfo, glxgears
	vulkan-tools
	mesa-demos
	# Logitech Unifying/Bolt receiver and device manager
	solaar
)

install_available_optional_packages gaming "${optional_gaming_packages[@]}"
