#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# shellcheck source=../lib/packages-helpers.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/../lib/packages-helpers.sh"

if ! is_enabled "${ENABLE_GAMING_PERIPHERALS:-0}"; then
	echo "Specialized gaming peripheral profile is disabled; keeping the lean base stack."
	exit 0
fi

# ── Optional PC gaming peripheral stack ──────────────────────────────────────
# Keep these out of the core gaming transaction. They come from a mix of Fedora,
# RPM Fusion, COPRs, and fast-moving driver packages; if one has a temporary
# dependency conflict or mirror outage, the image should still ship the core
# Steam/Gamescope/MangoHud/GameMode stack. Install these together normally, then
# retry individually if one flaky package prevents the batch from landing.
optional_gaming_packages=(
	rom-properties-kf6
	jstest-gtk
	libcec
	cec-utils
	opentabletdriver
	corectrl
	akmod-v4l2loopback
	v4l2loopback
	v4l-utils
	gamescope-session-plus
	libwacom
	libwacom-data
	hplip
	ryzenadj
	i2c-tools
	lm_sensors
	extest
	extest.i686
	# Vulkan / GL debugging: vulkaninfo, glxinfo, glxgears
	vulkan-tools
	mesa-demos
)

install_available_optional_packages gaming "${optional_gaming_packages[@]}"
