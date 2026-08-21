#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# shellcheck source=../lib/check-multilib.sh disable=SC1091
source "../lib/check-multilib.sh"
# shellcheck source=../lib/gaming-coprs.sh disable=SC1091
source "../lib/gaming-coprs.sh"
# shellcheck source=../lib/packages-helpers.sh disable=SC1091
source "../lib/packages-helpers.sh"
# shellcheck source=../lib/dnf-retry.sh disable=SC1091
source "../lib/dnf-retry.sh"

# Enable COPRs for gaming packages (retry loop survives Copr/Fedora mirror blips)
for copr in "${KYTH_GAMING_COPRS[@]}"; do
	copr_enable_retry "${copr}"
done

# Gaming packages
# libde265.i686 is excluded: it's an HEVC decoder pulled in transitively by
# some gaming libs, but it's frequently unavailable on Fedora mirrors and is not needed.
# steam and lutris are intentionally absent as RPMs — both are installed as
# Flatpaks by kyth-default-flatpaks.service so the immutable base stays lean
# while the first-boot gaming experience is ready out of the box.
# umu-launcher is intentionally absent here — not in bazzite COPR for Fedora 44;
# installed from GitHub releases in thirdparty.sh instead.
#
# Keep native x86_64 packages aligned before adding their i686 multilib builds.
# Fedora mirror/COPR timing can expose a newer i686 build while the base image
# still carries the previous x86_64 build; mismatched versions conflict on
# shared doc/man files.
dnf_retry upgrade -y libatomic.x86_64 nss.x86_64 || true

# Multilib 32-bit packages are required for 32-bit Windows games running via Steam/Wine.
# If gaming core features are disabled in custom profile builds, skip 32-bit multilib.
multilib_pkgs=()
if is_enabled "${ENABLE_GAMING_CORE:-1}"; then
	multilib_pkgs=(
		mangohud.i686
		vkBasalt.i686
		libFAudio.i686
		libobs_vkcapture.i686
		libobs_glcapture.i686
		gamemode.i686
		libXScrnSaver.i686
		libxcb.i686
		libatomic.i686
		mesa-libGL.i686
		mesa-dri-drivers.i686
		nss.i686
	)
fi

dnf_retry install -y --skip-unavailable --exclude=libde265.i686 \
	gamescope \
	gamescope-shaders \
	mangohud.x86_64 \
	vkBasalt.x86_64 \
	libFAudio.x86_64 \
	libobs_vkcapture.x86_64 \
	libobs_glcapture.x86_64 \
	xrandr \
	xdg-user-dirs \
	xdg-terminal-exec \
	gamemode \
	libXScrnSaver \
	libatomic \
	nss \
	steam-devices \
	game-devices-udev \
	xpadneo \
	xone \
	dualsensectl \
	joycond \
	kdeplasma-addons \
	input-remapper \
	libxcrypt-compat \
	"${multilib_pkgs[@]}"

# --skip-unavailable must not silently drop the x86_64 gaming stack.
required_gaming_rpms=(
	gamescope
	gamescope-shaders
	mangohud
	gamemode
	steam-devices
)
missing_gaming_rpms=()
for pkg in "${required_gaming_rpms[@]}"; do
	if ! rpm -q "${pkg}" >/dev/null 2>&1; then
		missing_gaming_rpms+=("${pkg}")
	fi
done
if ((${#missing_gaming_rpms[@]})); then
	echo "ERROR: required gaming packages missing after install: ${missing_gaming_rpms[*]}" >&2
	exit 1
fi

# Guards against a package landing in only one of x86_64/i686 (see
# lib/check-multilib.sh for why). The install above uses --skip-unavailable,
# so a mirror/COPR desync on any of these can silently drop just one arch.
if is_enabled "${ENABLE_GAMING_CORE:-1}"; then
	check_multilib_pairs "${KYTH_MULTILIB_PAIRS[@]}"
fi

# Upstream SCX GitHub releases do not publish Linux binaries. Fedora's signed
# RPM remains available for explicit compatibility testing, but is disabled by
# default because its 0.5.4 BPF ABI is incompatible with kernel 7.1.
if is_enabled "${ENABLE_SCX:-0}"; then
	dnf_retry install -y scx_rusty
	command -v scx_rusty >/dev/null
fi
