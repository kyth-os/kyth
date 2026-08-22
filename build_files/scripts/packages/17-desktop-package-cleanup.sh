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

# Plasma X11 session + classic Xorg greeter stack. KythOS greets and logs in
# on Wayland only. Keep NVIDIA proprietary GL/EGL userspace and XWayland
# (Steam/Proton/Electron). --no-autoremove so a leftover Requires: cannot pull
# sddm or plasma-workspace out with Xorg.
dnf5 remove -y --no-autoremove \
	plasma-workspace-x11 \
	kwin-x11 \
	xorg-x11-server-Xorg \
	xorg-x11-xinit \
	xorg-x11-drv-libinput \
	xorg-x11-drv-amdgpu \
	xorg-x11-drv-ati \
	2>/dev/null || true

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


