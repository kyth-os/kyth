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
# Classic Xorg DDX drivers are not installed: the greeter and Plasma session
# are Wayland. XWayland talks GBM/EGL, not those DDX drivers.
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

# qemu-ga's Fedora unit is not conditioned on virtualization. Enabling
# it unconditionally makes qemu-ga fail on bare metal (no virtio-serial).
# Restrict the unit to VMs; keep it enabled so guests still get it.
install -d /usr/lib/systemd/system/qemu-guest-agent.service.d
cat > /usr/lib/systemd/system/qemu-guest-agent.service.d/10-kyth-vm-only.conf <<'QEMUGA'
[Unit]
ConditionVirtualization=vm
QEMUGA
systemctl enable qemu-guest-agent.service 2>/dev/null || true
