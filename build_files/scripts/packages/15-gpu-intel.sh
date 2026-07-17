#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Intel GPU ─────────────────────────────────────────────────────────────────
# mesa-dri-drivers already ships iris (Gen 9+) and crocus (Gen 4–8) Gallium
# drivers, and mesa-vulkan-drivers includes ANV (Intel Vulkan). The gap is
# hardware video decode (VA-API): iHD is the modern backend (Broadwell/Gen 8+),
# i965 covers older Gen 4–7 parts.
dnf5 install -y --skip-unavailable \
	intel-media-driver \
	libva-intel-driver \
	intel-gpu-tools \
	intel-compute-runtime || true
