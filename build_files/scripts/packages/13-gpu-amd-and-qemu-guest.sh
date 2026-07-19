#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

### GPU drivers

# ── AMD GPU ───────────────────────────────────────────────────────────────────
# amdgpu is in the kernel; RADV (Vulkan) comes from mesa (Fedora repos).
# linux-firmware provides the baseline firmware set.  The AMD subpackages are
# listed explicitly so future Fedora packaging splits cannot accidentally drop
# GPU firmware or CPU microcode from AMD bare-metal installs.
#
# mesa-vulkan-drivers: RADV — the Mesa AMD Vulkan driver. Required for Vulkan
#   on AMD hardware (RDNA/GCN).
# vulkan-loader: the Vulkan ICD loader that dispatches calls to RADV/others.
# mesa-libgbm: Generic Buffer Management — used by DRM/KMS, Wayland, EGL.
# libdrm: Direct Rendering Manager userspace library.
# mesa-dri-drivers: OpenGL/DRI Gallium drivers, also provides radeonsi_drv_video.so
#   (AMD VA-API decode backend used by libva).
# xorg-x11-drv-amdgpu: X11 DDX driver for AMD. Required for SDDM X11 greeter
#   and Xwayland; relies on the in-kernel amdgpu KMS driver.
# xorg-x11-drv-ati: fallback DDX for older Radeon GPUs.
#
# ── QEMU/KVM guest ────────────────────────────────────────────────────────────
# qemu-guest-agent: graceful shutdown, snapshot freeze, guest state queries.
#   spice-vdagent handles clipboard and display resize in SPICE sessions.
dnf5 install -y --skip-unavailable \
	linux-firmware \
	amd-gpu-firmware \
	amd-ucode-firmware \
	libva-utils \
	mesa-vulkan-drivers \
	vulkan-loader \
	mesa-dri-drivers \
	mesa-libgbm \
	libdrm \
	xorg-x11-drv-amdgpu \
	xorg-x11-drv-ati \
	radeontop \
	nvtop \
	libclc \
	qemu-guest-agent

# Fedora 44's Mesa split makes `rpm -q mesa-va-drivers` look absent even when
# the VA-API driver is installed. Verify the capability and file ownership
# directly so build logs catch a genuinely broken AMD video decode stack.
rpm -q --whatprovides mesa-va-drivers
rpm -q --whatprovides /usr/lib64/dri/radeonsi_drv_video.so
test -e /usr/lib64/dri/radeonsi_drv_video.so

# qemu-guest-agent is socket-activated on Fedora but the socket is only
# created when running inside a VM. Enable it unconditionally — systemd
# no-ops it on bare metal when the virtio-serial device is absent.
systemctl enable qemu-guest-agent.service 2>/dev/null || true
