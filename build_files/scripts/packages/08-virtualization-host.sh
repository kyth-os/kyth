#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# shellcheck source=../lib/packages-helpers.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/../lib/packages-helpers.sh"

if ! is_enabled "${ENABLE_VIRTUALIZATION_HOST:-0}"; then
	echo "Virtualization host profile is disabled; retaining guest integration only."
	exit 0
fi

dnf5 install -y --skip-unavailable \
	qemu-char-spice \
	qemu-device-display-virtio-gpu \
	qemu-device-display-virtio-vga \
	qemu-device-usb-redirect \
	qemu-img \
	qemu-system-x86-core
