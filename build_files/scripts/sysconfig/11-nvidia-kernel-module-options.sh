#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── NVIDIA kernel module options ─────────────────────────────────────────────
# nvidia-drm.modeset=1  — required for Wayland/SDDM to use the NVIDIA KMS driver
#   instead of falling back to fbdev; without it KDE Plasma on Wayland will not
#   start on NVIDIA hardware.
# NVreg_PreserveVideoMemoryAllocations=1 — keeps VRAM contents across suspend/
#   resume cycles, preventing a black screen after wake on NVIDIA systems.
# nouveau is NOT blacklisted: the proprietary NVIDIA driver is not installed in
#   this image, so nouveau must remain loadable to provide KMS/display output on
#   NVIDIA hardware. If a user layers the proprietary driver via rpm-ostree they
#   should add their own blacklist via /etc/modprobe.d/blacklist-nouveau.conf.
cat >/etc/modprobe.d/nvidia-kyth.conf <<'NVEOF'
options nvidia-drm modeset=1
options nvidia NVreg_PreserveVideoMemoryAllocations=1
options nvidia NVreg_TemporaryFilePath=/var/tmp
NVEOF

