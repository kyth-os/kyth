#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Intel GPU ─────────────────────────────────────────────────────────────────
# mesa-dri-drivers already ships iris (Gen 9+) and crocus (Gen 4–8) Gallium
# drivers, and mesa-vulkan-drivers includes ANV (Intel Vulkan). The gap is
# hardware video decode (VA-API): libva-intel-media-driver is the iHD backend
# (Broadwell/Gen 8+; Fedora renamed it from intel-media-driver). It is
# required, not --skip-unavailable: without it every Intel iGPU silently loses
# hardware decode. The legacy i965 backend (libva-intel-driver, Gen 4–7) was
# dropped by Fedora entirely — those parts have no VA-API now.
dnf5 install -y \
	libva-intel-media-driver
dnf5 install -y --skip-unavailable \
	intel-gpu-tools \
	intel-compute-runtime || true
