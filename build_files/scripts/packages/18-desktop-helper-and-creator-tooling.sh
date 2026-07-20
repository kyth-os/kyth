#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# shellcheck source=../lib/packages-helpers.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/../lib/packages-helpers.sh"

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
	openconnect \
	vpnc \
	kde-connect \
	plasma-browser-integration \
	cups-browsed

# Headroom host wrapper — delegates to kyth-ai-dev container
install -Dm 0755 /dev/stdin /usr/bin/headroom <<'WRAPPEREOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ -x "${HOME}/.local/bin/headroom" ]]; then
	exec "${HOME}/.local/bin/headroom" "$@"
fi

box="${KYTH_AI_DEV_BOX:-kyth-ai-dev}"
if command -v distrobox >/dev/null 2>&1 && distrobox list --no-color 2>/dev/null | awk '{print $3}' | grep -qx "${box}"; then
	exec distrobox enter "${box}" -- headroom "$@"
else
	echo "Headroom is managed in the KythOS AI Developer container (${box})."
	echo "Initializing ${box} environment..."
	kyth-ai-dev setup
	exec distrobox enter "${box}" -- headroom "$@"
fi
WRAPPEREOF

# Atomic systems map /usr/local to the root-owned /var/usrlocal. npm's
# system default therefore makes `npm install -g` fail for desktop users.
# npmrc supports environment expansion, and ~/.local/bin is already on the
# Fedora user PATH, so global CLI tools belong in the user's home directory.
cat >/etc/npmrc <<'EOF'
prefix=${HOME}/.local
EOF

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
	cascadia-code-nf-fonts
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
	gh
	docker-compose
	direnv
	jq
	yq
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
# input-remapper is already installed in the gaming packages block
# (packages/06-gaming-core.sh).
