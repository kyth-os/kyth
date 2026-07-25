#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── OpenRGB — i2c bus access ──────────────────────────────────────────────────
# i2c-dev: exposes /dev/i2c-* devices to userspace so OpenRGB can talk to
# DRAM, motherboard, and GPU RGB controllers directly.
# i2c-piix4: provides the SMBus (i2c) controller driver that covers the AMD
# FCH/SB southbridge found on virtually all Ryzen gaming motherboards and many
# Intel boards. Without it OpenRGB cannot enumerate most onboard RGB zones.
printf 'i2c-dev\ni2c-piix4\n' >/etc/modules-load.d/openrgb.conf
