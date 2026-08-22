# shellcheck shell=bash
# ── Plasma Login Manager session type + login wallpaper ───────────────────────
# 10-kyth.conf owns the wallpaper and the Wayland session default used when
# 11-kyth-session.conf is missing (kyth-configure-session failed to write).
# Session type is owned by 11-kyth-session.conf (written every boot as
# plasmalogin ExecStartPre): always Plasma Wayland. Lexical order means 11
# overrides Session here. VMs, nomodeset, and first-boot NVIDIA without a
# render node use kyth-greeter-compositor's software-compose rescue.
# [X11] SessionDir is an empty directory so leftover Plasma X11 session
# files cannot appear in the greeter even if a base RPM still ships them.
install -d -m 0755 /usr/share/kyth/no-xsessions
write_config /etc/plasmalogin.conf.d/10-kyth.conf <<'PLMCONFEOF'
[General]
DefaultSession=plasma.desktop

[Autologin]
Session=plasma.desktop

[Greeter]
WallpaperPlugin=org.kde.image

[Greeter][Wallpaper][org.kde.image][General]
Image=file:///usr/share/wallpapers/kyth/contents/images/1920x1080.svg
PreviewImage=file:///usr/share/wallpapers/kyth/contents/images/1920x1080.svg

[Wayland]
SessionDir=/usr/share/wayland-sessions

[X11]
SessionDir=/usr/share/kyth/no-xsessions
PLMCONFEOF

# System-wide session env: software compose when there is no GPU render node,
# or when nomodeset disabled GPU KMS. kyth.hwgl=1 forces hardware GL (GPU
# passthrough / virgl). Live media adds its own unconditional live.sh on top.
write_config /etc/xdg/plasma-workspace/env/10-kyth-software-compose.sh 0755 <<'COMPOSEEOF'
#!/bin/sh
if grep -qw 'kyth.hwgl=1' /proc/cmdline 2>/dev/null; then
	return 0 2>/dev/null || exit 0
fi
if grep -qw nomodeset /proc/cmdline 2>/dev/null; then
	:
elif ls /dev/dri/renderD* >/dev/null 2>&1; then
	return 0 2>/dev/null || exit 0
fi
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export QT_QUICK_BACKEND=software
export KWIN_COMPOSE=Q
COMPOSEEOF

# Make enrolled fingerprints available to the login and screen-lock PAM stack.
# fprintd-pam provides the module; authselect activates it in Fedora's profile.
if command -v authselect >/dev/null 2>&1 && authselect current >/dev/null 2>&1; then
	authselect enable-feature with-fingerprint
fi
