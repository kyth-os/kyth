#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# shellcheck source=../lib/gaming-coprs.sh disable=SC1091
source "../lib/gaming-coprs.sh"

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
# All three ship in the Terra repo — the same packages Bazzite uses. The repo
# file is rendered directly by kyth-build-support repo-render (no release RPM
# is installed), and the repo is disabled afterwards so it does not persist
# as an active package source in the final image.
mkdir -p /etc/yum.repos.d
/usr/bin/kyth-build-support repo-render \
	--config /ctx/config/repos.json \
	--name terra \
	--output /etc/yum.repos.d/terra.repo

if dnf5 install -y --skip-unavailable \
	dmemcg-booster \
	plasma-foreground-booster-dmemcg \
	vulkan-low-latency-layer \
	opentabletdriver \
	extest \
	extest.i686; then
	systemctl enable dmemcg-booster-system.service 2>/dev/null || true
	systemctl --global enable dmemcg-booster-user.service 2>/dev/null || true
else
	echo "WARNING: dmemcg-booster/vulkan-low-latency-layer install failed; skipping." >&2
fi
# plasma-foreground-booster-dmemcg has no Terra build for this Fedora release;
# --skip-unavailable drops it silently, so call it out explicitly.
if ! rpm -q plasma-foreground-booster-dmemcg >/dev/null 2>&1; then
	echo "WARNING: plasma-foreground-booster-dmemcg unavailable for this Fedora release; Plasma foreground VRAM boost not installed." >&2
fi
# Same explicit guards for the other Terra-only packages: a partial skip
# inside the --skip-unavailable batch would otherwise be silent.
for terra_pkg in dmemcg-booster vulkan-low-latency-layer opentabletdriver extest; do
	if ! rpm -q "${terra_pkg}" >/dev/null 2>&1; then
		echo "WARNING: ${terra_pkg} unavailable for this Fedora release; skipped." >&2
	fi
done
dnf5 config-manager setopt terra.enabled=0

# Disable COPRs so they don't persist in the final image
/usr/bin/kyth-build-support disable-gaming-coprs
