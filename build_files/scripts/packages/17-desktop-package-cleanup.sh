#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

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
	cups-browsed \
	2>/dev/null || true

# Plasma X11 session + classic Xorg server/drivers. KythOS greets and logs in
# on Wayland only via Plasma Login Manager. Keep NVIDIA proprietary GL/EGL
# userspace and XWayland (Steam/Proton/Electron). Do not remove
# xorg-x11-xinit: plasma-login-manager Requires it, so a purge yanks PLM
# and the reinstall pulls xinit back. Reinstall PLM after the session
# purge, then drop leftover SDDM packages.
dnf5 remove -y --no-autoremove \
	plasma-workspace-x11 \
	kwin-x11 \
	xorg-x11-server-Xorg \
	xorg-x11-drv-libinput \
	xorg-x11-drv-amdgpu \
	xorg-x11-drv-ati
dnf5 install -y plasma-login-manager
dnf5 install -y --skip-unavailable kcm-plasmalogin
dnf5 remove -y --no-autoremove \
	sddm \
	sddm-breeze \
	sddm-wayland-plasma \
	sddm-x11 \
	sddm-kcm \
	2>/dev/null || true

# --no-autoremove can leave a package when something still Requires it. That
# must fail the image: hiding xsessions is not the same as removing Plasma X11.
# xorg-x11-xinit is not an X11 session; it is a PLM dependency and must stay.
forbidden_x11_session_rpms=(
	plasma-workspace-x11
	kwin-x11
	xorg-x11-server-Xorg
	xorg-x11-drv-libinput
	xorg-x11-drv-amdgpu
	xorg-x11-drv-ati
)
leftover_x11_session_rpms=()
for pkg in "${forbidden_x11_session_rpms[@]}"; do
	if rpm -q "${pkg}" >/dev/null 2>&1; then
		leftover_x11_session_rpms+=("${pkg}")
	fi
done
if ((${#leftover_x11_session_rpms[@]})); then
	echo "ERROR: Plasma X11 / Xorg session RPMs still installed: ${leftover_x11_session_rpms[*]}" >&2
	exit 1
fi
if ! rpm -q xorg-x11-server-Xwayland >/dev/null 2>&1; then
	echo "ERROR: xorg-x11-server-Xwayland must remain installed for games and Electron" >&2
	exit 1
fi
if ! rpm -q xorg-x11-xinit >/dev/null 2>&1; then
	echo "ERROR: xorg-x11-xinit must remain installed (plasma-login-manager Requires it)" >&2
	exit 1
fi
if ! rpm -q plasma-login-manager >/dev/null 2>&1 \
	|| [[ ! -x /usr/bin/plasmalogin ]] \
	|| [[ ! -f /usr/lib/systemd/system/plasmalogin.service ]]; then
	echo "ERROR: Plasma Login Manager must remain installed as the display manager" >&2
	exit 1
fi
if rpm -q sddm >/dev/null 2>&1 || [[ -x /usr/bin/sddm ]]; then
	echo "ERROR: SDDM is still installed; KythOS greets with plasmalogin" >&2
	exit 1
fi

# Remove Firefox — Brave Browser is installed as a Flatpak on first boot
# via kyth-default-flatpaks.service (avoids baking external repo keys into
# the build and eliminates DNS-dependent rpm --import calls in CI).
dnf5 remove -y firefox || true

# Purge non-English locale data, documentation, and manpages to enforce minimal image size
rm -rf \
	/usr/share/doc/* \
	/usr/share/man/* \
	/usr/share/info/* \
	/usr/share/gnome/help/* \
	2>/dev/null || true
find /usr/share/locale -mindepth 1 -maxdepth 1 ! -name 'en*' ! -name 'locale.alias' -exec rm -rf {} + 2>/dev/null || true

# Purge DNF solver metadata, package caches, and transient logs to keep image layer lean
dnf5 clean all 2>/dev/null || true
rm -rf /var/cache/dnf /var/cache/libdnf5 /tmp/* /var/tmp/* 2>/dev/null || true


