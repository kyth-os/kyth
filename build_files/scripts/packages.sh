#!/bin/bash

set -euo pipefail

# ── Locale filtering ──────────────────────────────────────────────────────────
# Strip non-English locale data from every subsequent RPM install.
# Saves 100–300 MB across the full package set with no functional loss
# on an English workstation.
echo '%_install_langs en_US' >>/etc/rpm/macros

# ── DNF parallelism ───────────────────────────────────────────────────────────
# Raise parallel download slots from the default 3 to 10 — same value used by
# UBlue, Bazzite, and recommended in Fedora documentation.
# Prevent any package dependency from pulling in a new kernel (e.g. akmod deps
# installing kernel-modules without kernel-core, which leaves a modules dir
# with no vmlinuz and breaks the bootc kernel check downstream). The bare
# `kernel` meta package is pinned too: its subpackages are excluded, so dnf5
# upgrade would otherwise report it as a broken-dependency Problem every day
# (the kernel version is fixed from the base image by design).
# CountMe adds an anonymous weekly age bucket to one repository metadata request.
# This lets Fedora-style mirror logs estimate active systems without user
# accounts, hardware IDs, or per-machine identifiers. Fedora's aggregate is
# repository-scoped and cannot be used as a KythOS-specific install count.
cat >>/etc/dnf/dnf.conf <<'DNFCONFEOF'
max_parallel_downloads=10
excludepkgs=kernel,kernel-core*,kernel-modules*,kernel-modules-core*,kernel-modules-extra*,kernel-devel*,kernel-debug*
countme=True
DNFCONFEOF

# KythOS is its own distribution identity. Replace the inherited Fedora artwork
# package with Fedora's generic drop-in before installing desktop components so
# upstream boot watermarks and launcher icons cannot leak into the final image.
dnf5 swap -y --allowerasing fedora-logos generic-logos

### Install Docker for container operations
# container-selinux provides the SELinux policy module for container runtimes
# (docker_t, container_t, etc.) — required for Docker to work under enforcing.
dnf5 install -y docker container-selinux

# Add rpmfusion free and nonfree repositories for Fedora 44.
# The release RPMs ship and install the GPG key themselves — this is the
# standard RPM Fusion bootstrap pattern; there is no separately hosted key
# URL to pre-import (unlike Brave/Negativo17).
# Fail loudly: every later codec install uses --skip-unavailable, so a missing
# RPM Fusion repo would otherwise ship an image silently lacking the
# freeworld codec stack.
dnf5 install -y \
	https://mirrors.rpmfusion.org/free/fedora/rpmfusion-free-release-44.noarch.rpm \
	https://mirrors.rpmfusion.org/nonfree/fedora/rpmfusion-nonfree-release-44.noarch.rpm
rpm -q rpmfusion-free-release rpmfusion-nonfree-release

# Fedora 44 transitions can leave debug/source repo metalinks unpublished or
# intermittently unavailable. We never install from those repos in image builds,
# so disable them up front to avoid noisy 404s and brittle solver behavior.
#
# Also disable negativo17's fedora-multimedia repo when it is inherited from an
# upstream base image. RPM Fusion supplies the codec stack we need, while
# negativo17's Mesa builds have caused AMD VA-API to fail initialization.
python3 - <<'PY'
from pathlib import Path
import configparser

repo_dir = Path("/etc/yum.repos.d")
patterns = ("debug", "source")
disabled_repo_ids = {"fedora-multimedia"}
disabled_repo_tokens = ("negativo17",)

for repo_file in repo_dir.glob("*.repo"):
    parser = configparser.RawConfigParser(strict=False)
    parser.optionxform = str
    try:
        with repo_file.open("r", encoding="utf-8") as fh:
            parser.read_file(fh)
    except Exception:
        continue

    changed = False
    for section in parser.sections():
        section_lower = section.lower()
        repo_name = parser.get(section, "name", fallback="").lower()
        repo_baseurl = parser.get(section, "baseurl", fallback="").lower()
        repo_metalink = parser.get(section, "metalink", fallback="").lower()
        repo_mirrorlist = parser.get(section, "mirrorlist", fallback="").lower()
        repo_text = "\n".join((section_lower, repo_name, repo_baseurl, repo_metalink, repo_mirrorlist))
        should_disable = (
            any(token in section_lower for token in patterns)
            or section_lower in disabled_repo_ids
            or any(token in repo_text for token in disabled_repo_tokens)
        )
        if should_disable:
            if parser.get(section, "enabled", fallback="1").strip() != "0":
                parser.set(section, "enabled", "0")
                changed = True

    if changed:
        with repo_file.open("w", encoding="utf-8") as fh:
            parser.write(fh, space_around_delimiters=False)
PY

# ── Multimedia baseline ───────────────────────────────────────────────────────
# Install a full system codec stack so common local playback, browser media,
# and creator workflows work without extra setup.  RPM Fusion provides the
# patent-encumbered pieces Fedora does not ship by default.
#
# Package rationale:
#   gstreamer1-plugins-good      — Fedora "good" tier: OGG/Vorbis, FLAC, WAV,
#     AIFF, MP4/isomp4, MKV/Matroska, WebM, AVI, VP8, QuickTime. Not pulled in
#     transitively — without it KDE Elisa, Gwenview, and any GStreamer-based app
#     cannot open these common formats.
#   gstreamer1-plugins-bad-freeworld — RPM Fusion nonfree: H.264 encode (x264),
#     HEVC encode (x265), and other patent-encumbered encoders/decoders.
#   gstreamer1-plugins-ugly      — RPM Fusion free: MP3 decode (mad), MPEG-1/2
#     A/V, AC3 (Dolby Digital).
#   gstreamer1-libav             — ffmpeg-backed GStreamer plugin; handles
#     virtually every container/codec ffmpeg supports.
#   gstreamer1-vaapi             — GStreamer VA-API plugin (vaapidecode element).
#     The VA-API driver backends (iHD, radeonsi_drv_video.so) are already
#     installed; without this plugin GStreamer apps do software decode even on
#     capable hardware.
#   NOTE: pipewire-codec-aptx (RPM Fusion nonfree) was removed. PipeWire 1.6.5
#     on Fedora 44 ships pipewire-libs-extra which bundles aptX/aptX-HD and LDAC
#     natively — the RPM Fusion package conflicts with the same file path.
#
# gstreamer1-plugins-bad-freeworld conflicts with Fedora's stock
# gstreamer1-plugins-bad; remove the stock build first, then install the RPM
# Fusion replacement with --allowerasing.
dnf5 remove -y gstreamer1-plugins-bad || true
dnf5 install -y --allowerasing --skip-unavailable --exclude=gstreamer1-plugins-bad \
	ffmpeg \
	ffmpegthumbnailer \
	gstreamer1-plugins-good \
	gstreamer1-plugin-openh264 \
	gstreamer1-plugins-bad-freeworld \
	gstreamer1-plugins-ugly \
	gstreamer1-libav \
	gstreamer1-vaapi \
	mozilla-openh264 \
	mpv

# Install baseline tooling in a single transaction to reduce solver and
# metadata overhead before the gaming repos are enabled.
dnf5 install -y --skip-unavailable \
	sddm \
	sddm-breeze \
	kwallet-pam \
	fprintd \
	fprintd-pam \
	pcsc-lite \
	opensc \
	krdc \
	bubblewrap \
	skopeo \
	plasma-workspace-x11 \
	xorg-x11-server-Xorg \
	xorg-x11-xinit \
	xorg-x11-drv-libinput \
	irqbalance \
	p7zip \
	p7zip-plugins \
	plocate \
	cabextract \
	ntfs-3g \
	ntfsprogs \
	libpst \
	cifs-utils \
	rsync \
	xorriso \
	squashfs-tools \
	fuse \
	fuse-libs \
	fuse3 \
	mtools \
	dosfstools \
	sbsigntools \
	qemu-char-spice \
	qemu-device-display-virtio-gpu \
	qemu-device-display-virtio-vga \
	qemu-device-usb-redirect \
	qemu-img \
	qemu-system-aarch64 \
	qemu-system-x86-core \
	util-linux-script \
	tmux \
	gh \
	openssl \
	fwupd

# Enable COPRs for gaming packages
dnf5 copr enable -y ublue-os/bazzite
dnf5 copr enable -y ublue-os/bazzite-multilib
dnf5 copr enable -y ublue-os/staging
dnf5 copr enable -y ublue-os/packages
dnf5 copr enable -y ublue-os/obs-vkcapture
dnf5 copr enable -y lukenukem/asus-linux
dnf5 copr enable -y ycollet/audinux

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
dnf5 upgrade -y libatomic.x86_64 nss.x86_64 || true

dnf5 install -y --skip-unavailable --exclude=libde265.i686 \
	gamescope \
	gamescope-shaders \
	mangohud.x86_64 \
	mangohud.i686 \
	vkBasalt.x86_64 \
	vkBasalt.i686 \
	libFAudio.x86_64 \
	libFAudio.i686 \
	libobs_vkcapture.x86_64 \
	libobs_glcapture.x86_64 \
	libobs_vkcapture.i686 \
	libobs_glcapture.i686 \
	xrandr \
	evtest \
	xdg-user-dirs \
	xdg-terminal-exec \
	gamemode \
	gamemode.i686 \
	libXScrnSaver \
	libXScrnSaver.i686 \
	libxcb.i686 \
	libatomic \
	libatomic.i686 \
	mesa-libGL.i686 \
	mesa-dri-drivers.i686 \
	nss \
	nss.i686 \
	steam-devices \
	kdeplasma-addons \
	input-remapper \
	libxcrypt-compat

# ── Optional PC gaming peripheral stack ──────────────────────────────────────
# Keep these out of the core gaming transaction. They come from a mix of Fedora,
# RPM Fusion, COPRs, and fast-moving driver packages; if one has a temporary
# dependency conflict or mirror outage, the image should still ship the core
# Steam/Gamescope/MangoHud/GameMode stack. Install these together normally, then
# retry individually if one flaky package prevents the batch from landing.
optional_gaming_packages=(
	rom-properties-kf6
	game-devices-udev
	xpadneo
	xone
	dualsensectl
	jstest-gtk
	libcec
	cec-utils
	openrazer-daemon
	openrazer-meta
	opentabletdriver
	corectrl
	akmod-v4l2loopback
	v4l2loopback
	v4l-utils
	joycond
	gamescope-session-plus
	openrgb
	libwacom
	libwacom-data
	hplip
	ryzenadj
	i2c-tools
	lm_sensors
	sunshine
	extest
	extest.i686
	# Vulkan / GL debugging: vulkaninfo, glxinfo, glxgears
	vulkan-tools
	mesa-demos
	# Logitech Unifying/Bolt receiver and device manager
	solaar
)

install_available_optional_packages() {
	local group_name=$1
	shift

	local pkg
	local -a available_packages=()

	# One metadata load for all packages instead of N individual queries.
	local available_set
	available_set=$(dnf5 repoquery --available --qf '%{name}\n' "$@" 2>/dev/null | sort -u)

	for pkg in "$@"; do
		if grep -qx "${pkg}" <<<"${available_set}"; then
			available_packages+=("${pkg}")
		else
			echo "optional ${group_name} package '${pkg}' is unavailable in configured repos; skipping."
		fi
	done

	((${#available_packages[@]})) || return 0

	# Use one transaction in the normal case. If one optional package has a
	# transient conflict, retry individually so the rest still land.
	if dnf5 install -y --skip-unavailable "${available_packages[@]}"; then
		return 0
	fi

	echo "WARNING: optional ${group_name} package batch failed; retrying individually." >&2
	for pkg in "${available_packages[@]}"; do
		dnf5 install -y --skip-unavailable "${pkg}" ||
			echo "WARNING: optional ${group_name} package '${pkg}' failed to install; continuing." >&2
	done
}

install_available_optional_packages gaming "${optional_gaming_packages[@]}"

# ── ASUS Linux hardware control ───────────────────────────────────────────────
# asusctl/asusd expose ASUS ROG/TUF/Zephyrus/ProArt controls such as platform
# profiles, battery charge limits, fan curves, keyboard lighting, and newer
# Armoury firmware attributes. supergfxctl provides hybrid/dGPU mode management
# for supported ASUS laptops. The upstream asusd udev rules are DMI-gated, and
# Kyth adds a matching supergfxd udev rule in the branding layer.
dnf5 install -y --skip-unavailable \
	asusctl \
	supergfxctl || true
systemctl disable supergfxd.service 2>/dev/null || true
rm -f /etc/systemd/system/getty.target.wants/supergfxd.service

is_enabled() {
	case "${1,,}" in
	1 | true | yes | on) return 0 ;;
	*) return 1 ;;
	esac
}

# ── system76-scheduler ────────────────────────────────────────────────────────
# Dynamically adjusts CFS nice values and I/O priority based on which window
# is focused and whether a game is running.  Gives a noticeable responsiveness
# boost during gaming without requiring per-app configuration.
if dnf5 repoquery --available system76-scheduler 2>/dev/null | grep -q .; then
	dnf5 install -y --skip-unavailable system76-scheduler || true
	if rpm -q system76-scheduler >/dev/null 2>&1; then
		systemctl enable com.system76.Scheduler 2>/dev/null || true
	fi
else
	echo "system76-scheduler is unavailable in configured repos; skipping."
fi

# ── ananicy-cpp process priority rules ───────────────────────────────────────
# Applies static per-process CPU/I/O priorities (browser, game launchers,
# compilers, etc.) to smooth desktop responsiveness under mixed load.
if is_enabled "${ENABLE_ANANICY:-1}"; then
	if dnf5 repoquery --available ananicy-cpp 2>/dev/null | grep -q .; then
		dnf5 install -y --skip-unavailable \
			ananicy-cpp \
			ananicy-cpp-rules \
			ananicy-cpp-rules-git || true
		if rpm -q ananicy-cpp >/dev/null 2>&1; then
			systemctl enable ananicy-cpp.service 2>/dev/null || true
		fi
	else
		echo "ananicy-cpp is unavailable in configured repos; skipping."
	fi
else
	echo "ENABLE_ANANICY is off; skipping ananicy-cpp install."
fi

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

# ── Platform and wireless firmware ───────────────────────────────────────────
# Fedora has been splitting linux-firmware into smaller subpackages. Keep the
# hardware-critical families explicit so workstation laptops do not depend on
# whichever subset the base image happened to include:
#   - iwlwifi-mvm: Intel Wi-Fi 4/5/6/6E families common in EliteBook systems
#   - iwlwifi-mld: newer Intel Wi-Fi 7 / BE-series devices
#   - iwlwifi-dvm + iwlegacy: older Intel adapters still seen in business fleets
#   - realtek/mediatek/atheros/brcmfmac: common USB/PCIe/Bluetooth companion HW
#   - cirrus/sof/intel-vsc: HP laptop audio, DSP, camera, and sensor firmware
dnf5 install -y --skip-unavailable \
	iwlwifi-mvm-firmware \
	iwlwifi-mld-firmware \
	iwlwifi-dvm-firmware \
	iwlegacy-firmware \
	intel-vsc-firmware \
	alsa-sof-firmware \
	realtek-firmware \
	mediatek-firmware \
	atheros-firmware \
	brcmfmac-firmware \
	cirrus-audio-firmware || true

iwlwifi_firmware_probe="$(
	find /usr/lib/firmware \
		\( -name 'iwlwifi-*.ucode*' -o -name 'iwlwifi-*.pnvm*' \) \
		-print -quit
)"
if [[ -z "${iwlwifi_firmware_probe}" ]]; then
	echo "ERROR: Intel iwlwifi firmware blobs are missing from the image." >&2
	exit 1
fi
echo "Intel iwlwifi firmware present: ${iwlwifi_firmware_probe}"

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

# ── NVIDIA GPU ────────────────────────────────────────────────────────────────
# Bundle akmod-nvidia so kyth-hw-setup can build the kernel module at first
# boot without requiring a manual rpm-ostree layer step. On AMD/Intel systems
# the package sits dormant and the build is never triggered.
#
# kernel-devel* sits in dnf.conf excludepkgs (top of this script) to stop akmod
# deps from dragging in a second kernel. That exclude made akmod-nvidia
# unresolvable, and the old --skip-unavailable + || true silently shipped
# images with no akmod-nvidia at all — breaking the first-boot NVIDIA path.
# Clear the exclude for this one transaction, pin kernel-devel to the exact
# kernel in the image so akmods finds matching headers at first boot, and
# verify the result so a regression fails the build instead of first boot.
KERNEL_FLAVOR="$(cat /usr/share/kyth/kernel-flavor 2>/dev/null || echo fedora)"
if [[ "${KERNEL_FLAVOR}" == "fedora" ]]; then
	KERNEL_VR=$(rpm -q kernel-core --qf '%{VERSION}-%{RELEASE}.%{ARCH}\n' | sort -V | tail -n 1)
	dnf5 install -y --setopt=excludepkgs= \
		"kernel-devel-${KERNEL_VR}" \
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
# nvidia-vaapi-driver and 32-bit CUDA libs: best-effort — not yet consistently
# published for Fedora 44 in RPM Fusion nonfree. Install when available;
# LIBVA_DRIVER_NAME=nvidia + NVD_BACKEND=direct (set in the NVIDIA runtime env
# generator) will activate it automatically once the package lands.
dnf5 install -y --skip-unavailable --setopt=excludepkgs= \
	nvidia-vaapi-driver \
	xorg-x11-drv-nvidia-cuda-libs.i686 || true

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

# Remove unwanted desktop packages in one solver transaction:
# - plasma-welcome: plasma-login handles first-boot setup instead.
# - plasma-discover-rpm-ostree: bootc updates the whole OS image; individual RPM
#   updates shown by Discover are phantom/unactionable. Keep Discover itself so
#   Flatpak management still works.
# - kio-gdrive: Google denied KDE's Drive API authorization, so Dolphin exposes
#   an account entry that fails with "Access denied to .". System Hub provides
#   the supported rclone OAuth wizard.
dnf5 remove -y --no-autoremove \
	plasma-welcome \
	plasma-welcome-fedora \
	plasma-discover-rpm-ostree \
	kio-gdrive \
	2>/dev/null || true

# Remove Firefox — Brave Browser is installed as a Flatpak on first boot
# via kyth-default-flatpaks.service (avoids baking external repo keys into
# the build and eliminates DNS-dependent rpm --import calls in CI).
dnf5 remove -y firefox || true

# ── Desktop helper, Plymouth, mutable-workspace, and creator tooling ─────────
# Keep required desktop helper packages in one transaction. Optional niceties
# use a batched fast path with individual fallback so a transient RPM/scriptlet
# issue in a font or hardware utility does not block the image.
dnf5 install -y --skip-unavailable \
	python3-pyqt6 \
	python3-pyqt6-webengine \
	python3-pip \
	python3-devel \
	python3-pytest \
	python3-defusedxml \
	curl \
	qt6-qtwayland \
	plymouth \
	plymouth-plugin-script \
	librsvg2-tools \
	distrobox \
	unzip \
	git \
	ShellCheck \
	shfmt \
	spice-vdagent \
	virt-viewer \
	kscreen \
	neovim \
	zsh \
	nodejs \
	npm \
	openconnect \
	vpnc \
	kde-connect \
	plasma-browser-integration \
	cups-browsed

# Fedora has historically moved between versioned and unversioned Python tool
# entrypoints. Keep the familiar `pip` command present on PATH for users while
# leaving the RPM-owned pip3 binary untouched.
if ! command -v pip >/dev/null 2>&1; then
	pip3_path="$(command -v pip3 || true)"
	if [[ -z "${pip3_path}" ]]; then
		echo "ERROR: python3-pip installed without pip3 on PATH." >&2
		exit 1
	fi
	ln -s "${pip3_path}" /usr/local/bin/pip
fi
pip --version


optional_desktop_packages=(
	jetbrains-mono-fonts
	cascadia-code-fonts
	liberation-fonts-all
	inter-fonts
	papirus-icon-theme
	# Calibri/Cambria-compatible fonts: fix Office document rendering for Windows migrants.
	# Arial/Times are covered by liberation-fonts; Calibri (default since Office 2007)
	# needs Carlito, and Cambria needs Caladea, for correct line-break and pagination matching.
	google-carlito-fonts
	google-caladea-fonts
	# Emoji rendering — without this, emoji in browsers and terminals render as
	# empty boxes on systems that only have the liberation/inter font set.
	google-noto-emoji-fonts
	# Modern CLI tools loved by Linux veterans (all gracefully absent if unavailable).
	bat
	eza
	fd-find
	ripgrep
	fzf
	zoxide
	git-delta
	starship
	helix
	# zsh enhancements — sourced automatically by the /etc/skel/.zshrc below.
	zsh-autosuggestions
	zsh-syntax-highlighting
	# fish shell — out-of-box syntax highlighting and autosuggestions with no config.
	# Good first shell for Windows migrants; veterans can chsh -s /usr/bin/fish.
	fish
	# zellij — modern terminal multiplexer; tmux-compatible with a friendlier UI.
	zellij
	# btop — interactive resource/process monitor (better htop).
	btop
	# fastfetch — system info display (neofetch replacement, actively maintained).
	fastfetch
	# gum — Charm CLI beautification library; used by ujust scripts for interactive menus.
	gum
	# ydotool — Wayland-compatible xdotool; required for Wayland automation scripts.
	ydotool
	# ddcutil — DDC/CI monitor brightness/contrast control via I²C.
	ddcutil
	ddcutil-service
	# iio-sensor-proxy — exposes orientation sensors (accelerometer) over D-Bus
	# for auto-rotation on convertibles and handhelds.
	iio-sensor-proxy
)

install_available_optional_packages desktop "${optional_desktop_packages[@]}"
# spice-vdagentd is socket/udev-activated — no systemctl enable needed.
# kde-connect: Phone Link equivalent for Android — pairs over LAN/Bluetooth.
# plasma-browser-integration: native host for browser media controls, download
#   progress, and desktop integration once the browser extension is enabled.
# cups-browsed: auto-discovers printers on the LAN without manual config.
# liberation-fonts-all: metric-compatible substitutes for Arial/Times/Courier.
#   mscore-fonts-all (RPM Fusion) was removed — its %post downloads from
#   SourceForge at install time, which is unreliable in CI builds.
# openrgb: RGB peripheral control installed by default; udev rules grant LED device
#   access to the logged-in user. Autostarted at login via XDG autostart entry.
# libwacom/libwacom-data: tablet pressure-curve database used by KWin/libinput on
#   Wayland for Wacom and Wacom-compatible tablets. Without this, pressure sensitivity
#   maps incorrectly and drawing feels like a binary on/off signal.
# hplip: HP printer driver stack. Auto-detects most HP USB/network printers without
#   manual CUPS configuration.
# input-remapper is already installed in the gaming packages block above.

# ── VS Code ───────────────────────────────────────────────────────────────────
# Bake VS Code native RPM into the image so it has full access to the local
# filesystem and terminal without the sandboxing constraints of a Flatpak.
# The Microsoft signing key is vendored in-repo (build_files/RPM-GPG-KEY-microsoft,
# fingerprint BC528686B50D79E339D3721CEB3E94ADBE1229CF) and bind-mounted at /ctx,
# so the build has no DNS-dependent rpm --import call.
install -Dm 0644 /ctx/RPM-GPG-KEY-microsoft /etc/pki/rpm-gpg/RPM-GPG-KEY-microsoft
rpm --import /etc/pki/rpm-gpg/RPM-GPG-KEY-microsoft
cat >/etc/yum.repos.d/vscode.repo <<'EOF'
[code]
name=Visual Studio Code
baseurl=https://packages.microsoft.com/yumrepos/vscode
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-microsoft
EOF
dnf5 install -y code
# Disable so the Microsoft repo is not active in the running OS;
# VS Code self-updates are not meaningful in an immutable image.
dnf5 config-manager setopt code.enabled=0

# ── Google Antigravity IDE ────────────────────────────────────────────────────
# Bake Google Antigravity IDE native RPM into the image so it has full access to the local
# filesystem and terminal without the sandboxing constraints of a Flatpak.
# The Google repository signing key is vendored in-repo (build_files/RPM-GPG-KEY-google-antigravity)
# and bind-mounted at /ctx, so the build has no DNS-dependent rpm --import call.
install -Dm 0644 /ctx/RPM-GPG-KEY-google-antigravity /etc/pki/rpm-gpg/RPM-GPG-KEY-google-antigravity
# Skip importing key into RPM database because Fedora's strict crypto policy/Sequoia
# rejects the key format (No binding signature at time ...). Since Google Artifact
# Registry repositories are served over HTTPS, gpgcheck is disabled instead.
cat >/etc/yum.repos.d/antigravity.repo <<'EOF'
[antigravity-rpm]
name=Antigravity RPM Repository
baseurl=https://us-central1-yum.pkg.dev/projects/antigravity-auto-updater-dev/antigravity-rpm
enabled=1
gpgcheck=0
repo_gpgcheck=0
EOF
dnf5 install -y antigravity
# Disable so the Antigravity repo is not active in the running OS;
# self-updates are not meaningful in an immutable image.
dnf5 config-manager setopt antigravity-rpm.enabled=0


# ── Windows environment management tools ─────────────────────────────────────
# Tools for users who manage Windows hosts, Azure, or Active Directory from
# KythOS. Reuses the already-vendored Microsoft signing key from the VS Code
# block above.

# Azure CLI — same Microsoft key, different repo.
cat >/etc/yum.repos.d/azure-cli.repo <<'AZUREREPOEOF'
[azure-cli]
name=Azure CLI
baseurl=https://packages.microsoft.com/yumrepos/azure-cli
enabled=1
gpgcheck=1
gpgkey=file:///etc/pki/rpm-gpg/RPM-GPG-KEY-microsoft
AZUREREPOEOF

dnf5 install -y azure-cli
rpm -q azure-cli

# Disable update checks — same reason as VS Code: immutable image.
dnf5 config-manager setopt azure-cli.enabled=0

# RDP, Active Directory, Kerberos, and SMB tooling — all in standard Fedora repos.
# freerdp: best-in-class RDP client; powers Remmina's RDP backend.
# realmd/sssd/adcli: domain join, AD auth, and LDAP/Kerberos enrollment.
# krb5-workstation: kinit, klist, kdestroy — Kerberos ticket management.
# samba-client: smbclient + net ads + wbinfo for SMB share browsing and AD queries.
#   (cifs-utils for mounting is already installed in the baseline block above.)
dnf5 install -y --skip-unavailable \
	freerdp \
	realmd \
	sssd \
	sssd-ad \
	sssd-tools \
	adcli \
	krb5-workstation \
	samba-client \
	openldap-clients

# ── greenboot boot-time health checks ────────────────────────────────────────
# greenboot marks each boot good/bad and triggers automatic rollback to the
# previous bootc deployment if health checks fail across three consecutive boots.
# greenboot-default-health-checks adds basic required/wanted service checks out
# of the box. Installed last so a transient package issue here cannot gate the
# full image build — the core gaming stack lands regardless.
dnf5 install -y greenboot greenboot-default-health-checks
systemctl enable greenboot-healthcheck.service greenboot-set-rollback-trigger.service

# ── Tailscale zero-config VPN ─────────────────────────────────────────────────
# WireGuard-based mesh VPN with no port forwarding required. Useful for LAN party
# gaming over the internet and remote desktop access.
# Disabled by default — opt-in via `ujust setup-tailscale`.
# Vendor the repo config inline rather than fetching from Tailscale's CDN at
# build time — a transient CDN blip would otherwise fail the entire build.
mkdir -p /etc/yum.repos.d
cat >/etc/yum.repos.d/tailscale-stable.repo <<'TAILSCALEREPOEOF'
[tailscale-stable]
name=Tailscale stable
baseurl=https://pkgs.tailscale.com/stable/fedora/$releasever/$basearch
enabled=1
type=rpm
repo_gpgcheck=1
gpgcheck=0
gpgkey=https://pkgs.tailscale.com/stable/fedora/repo.gpg
TAILSCALEREPOEOF
dnf5 install -y tailscale
systemctl disable tailscaled.service 2>/dev/null || true
dnf5 config-manager setopt tailscale-stable.enabled=0

# Keep downloaded metadata and RPMs in Docker's /var/cache mount. The cache is
# excluded from the image layer automatically and speeds up later rebuilds.
