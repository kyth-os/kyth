#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../lib/fedora-kernel.sh"

# ── NVIDIA GPU ────────────────────────────────────────────────────────────────
# Bundle akmod-nvidia so kyth-hw-setup can build the kernel module at first
# boot without requiring a manual rpm-ostree layer step. On AMD/Intel systems
# the package sits dormant and the build is never triggered.
#
# kernel-devel* sits in dnf.conf excludepkgs (packages/01-locale-and-dnf-tuning.sh)
# to stop akmod deps from dragging in a second kernel. That exclude made akmod-nvidia
# unresolvable, and the old --skip-unavailable + || true silently shipped
# images with no akmod-nvidia at all — breaking the first-boot NVIDIA path.
# Clear the exclude for this one transaction, pin kernel-devel to the exact
# kernel in the image so akmods finds matching headers at first boot, and
# verify the result so a regression fails the build instead of first boot.
#
# 03-rpmfusion deletes leftover negativo17 fedora-multimedia repo files.
# Do not pass --disablerepo=fedora-multimedia here: dnf5 exits 2 when that
# repo id is already gone. The NVIDIA origin check below still fails the
# build if packages somehow resolve from negativo17.
KERNEL_FLAVOR="$(cat /usr/share/kyth/kernel-flavor 2>/dev/null || echo fedora)"
if [[ "${KERNEL_FLAVOR}" == "fedora" ]]; then
	update_fedora_kernel
	KERNEL_VR="${FEDORA_KERNEL_VR}"
	dnf5 install -y --setopt=excludepkgs= \
		akmod-nvidia \
		xorg-x11-drv-nvidia \
		xorg-x11-drv-nvidia-libs \
		xorg-x11-drv-nvidia-libs.i686 \
		xorg-x11-drv-nvidia-cuda-libs \
		egl-wayland
	rpm -q akmod-nvidia akmods "kernel-devel-${KERNEL_VR}" \
		xorg-x11-drv-nvidia egl-wayland
else
	# CachyOS flavor: matching headers (kernel-cachyos-devel-matched) come from
	# the COPR in build_base; only the akmod machinery is needed here.
	dnf5 install -y --setopt=excludepkgs= \
		akmod-nvidia \
		xorg-x11-drv-nvidia \
		xorg-x11-drv-nvidia-libs \
		xorg-x11-drv-nvidia-libs.i686 \
		xorg-x11-drv-nvidia-cuda-libs \
		egl-wayland
	rpm -q akmod-nvidia akmods \
		xorg-x11-drv-nvidia egl-wayland
fi

nvidia_origin=$(rpm -q --queryformat '%{VENDOR} %{PACKAGER}\n' akmod-nvidia xorg-x11-drv-nvidia 2>/dev/null || true)
if grep -Eiq 'negativo17|fedora-multimedia' <<<"${nvidia_origin}"; then
	echo "ERROR: NVIDIA stack installed from negativo17: ${nvidia_origin:-unknown}"
	exit 1
fi
# nvidia-vaapi-driver and 32-bit CUDA libs: best-effort — not yet consistently
# published for Fedora 44 in RPM Fusion nonfree. Install when available;
# LIBVA_DRIVER_NAME=nvidia + NVD_BACKEND=direct (set in the NVIDIA runtime env
# generator) will activate it automatically once the package lands.
dnf5 install -y --skip-unavailable --setopt=excludepkgs= \
	nvidia-vaapi-driver \
	xorg-x11-drv-nvidia-cuda-libs.i686 || true
