#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── VRAM foreground prioritization + Vulkan low-latency layer ────────────────
# dmemcg-booster (Valve, gitlab.steamos.cloud/holo/dmemcg-booster) enables the
# kernel dmem cgroup controller across the systemd hierarchy and sets dmem.low
# protection so the foreground app's VRAM is the last thing evicted under
# memory pressure. plasma-foreground-booster-dmemcg tracks the focused Plasma
# window and boosts its cgroup; it activates via its own /etc/xdg/autostart
# entry, no enablement needed. Requires CONFIG_CGROUP_DMEM plus amdgpu dmem
# region support — present in the CachyOS kernel; on the stock Fedora kernel
# flavor the daemons degrade to a harmless no-op if dmem is missing.
#
# vulkan-low-latency-layer is an implicit Vulkan layer providing hardware-
# agnostic VK_NV_low_latency2 (Reflex) and VK_AMD_anti_lag implementations.
# It is opt-in: inert until a game is launched with LOW_LATENCY_LAYER=1
# (see the low-latency-run wrapper / ujust low-latency).
#
# All three ship in the Terra repo — the same packages Bazzite uses. The
# terra-release RPM installs the repo file and signing key itself, so the
# bootstrap needs --nogpgcheck (same pattern as Bazzite and the RPM Fusion
# bootstrap above). The repo is disabled afterwards so it does not persist
# as an active package source in the final image.
# shellcheck disable=SC2016 # $releasever is a dnf repo variable, not a shell expansion
if dnf5 install -y --nogpgcheck --repofrompath 'terra,https://repos.fyralabs.com/terra$releasever' terra-release; then
	dnf5 install -y \
		dmemcg-booster \
		plasma-foreground-booster-dmemcg \
		vulkan-low-latency-layer
	systemctl enable dmemcg-booster-system.service
	systemctl --global enable dmemcg-booster-user.service
	dnf5 config-manager setopt terra.enabled=0
else
	echo "WARNING: Terra repo bootstrap failed; skipping VRAM booster + low-latency layer." >&2
fi

# Disable COPRs so they don't persist in the final image
dnf5 copr disable -y ublue-os/bazzite
dnf5 copr disable -y ublue-os/bazzite-multilib
dnf5 copr disable -y ublue-os/staging
dnf5 copr disable -y ublue-os/packages
dnf5 copr disable -y ublue-os/obs-vkcapture
dnf5 copr disable -y lukenukem/asus-linux
dnf5 copr disable -y ycollet/audinux
