# shellcheck shell=bash
# ── Plasma Login Manager session type + login wallpaper ───────────────────────
# /etc/plasmalogin.conf owns the greeter wallpaper. 10-kyth.conf owns the
# Wayland session default used when 11-kyth-session.conf is missing
# (kyth-configure-session failed to write).
# Session type is owned by 11-kyth-session.conf (written every boot as
# plasmalogin ExecStartPre): always Plasma Wayland. Lexical order means 11
# overrides Session here. VMs, nomodeset, and first-boot NVIDIA without a
# render node use kyth-greeter-compositor's software-compose rescue.
# [X11] SessionDir is an empty directory so leftover Plasma X11 session
# files cannot appear in the greeter even if a base RPM still ships them.
#
# Wallpaper must live in /etc/plasmalogin.conf, not only conf.d: current
# plasma-login-manager reads Greeter/Wallpaper from the main file and
# ignores those keys in drop-ins (KDE #515211 / discuss 46226). The KCM
# also expects a copy under the plasmalogin home.
install -d -m 0755 /usr/share/kyth/no-xsessions
install -d -m 0755 /var/lib/plasmalogin/wallpapers
install -m 0644 /usr/share/wallpapers/kyth/contents/images/1920x1080.svg \
	/var/lib/plasmalogin/wallpapers/kyth.svg
if getent passwd plasmalogin >/dev/null 2>&1; then
	chown -R plasmalogin:plasmalogin /var/lib/plasmalogin/wallpapers
fi
write_config /usr/lib/tmpfiles.d/kyth-plasmalogin-wallpaper.conf <<'PLMTMPFILESEOF'
d /var/lib/plasmalogin/wallpapers 0755 plasmalogin plasmalogin -
C /var/lib/plasmalogin/wallpapers/kyth.svg 0644 plasmalogin plasmalogin - /usr/share/wallpapers/kyth/contents/images/1920x1080.svg
PLMTMPFILESEOF

write_config /etc/plasmalogin.conf <<'PLMMAINCONFEOF'
[Greeter]
WallpaperPluginId=org.kde.image
WallpaperPlugin=org.kde.image

[Greeter][Wallpaper][org.kde.image][General]
Image=file:///var/lib/plasmalogin/wallpapers/kyth.svg
PreviewImage=file:///var/lib/plasmalogin/wallpapers/kyth.svg
PLMMAINCONFEOF

write_config /etc/plasmalogin.conf.d/10-kyth.conf <<'PLMCONFEOF'
[General]
DefaultSession=plasma.desktop

[Autologin]
Session=plasma.desktop

[Greeter]
WallpaperPluginId=org.kde.image
WallpaperPlugin=org.kde.image

[Greeter][Wallpaper][org.kde.image][General]
Image=file:///var/lib/plasmalogin/wallpapers/kyth.svg
PreviewImage=file:///var/lib/plasmalogin/wallpapers/kyth.svg

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
