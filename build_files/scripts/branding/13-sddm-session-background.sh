# shellcheck shell=bash
# ── SDDM session type + login screen background ───────────────────────────────
# 10-kyth.conf owns the theme and the Wayland greeter/session default used when
# 11-kyth-session.conf is missing (kyth-configure-session failed to write).
# Session type is owned by 11-kyth-session.conf (written every boot as SDDM
# ExecStartPre): Wayland unless nomodeset. Lexical order means 11 overrides
# DisplayServer/DefaultSession here. VMs and first-boot NVIDIA without a render
# node use kyth-sddm-compositor's software-compose rescue instead of an X11
# session. X11 remains installed for the session picker.
write_config /etc/sddm.conf.d/10-kyth.conf <<'SDDMCONFEOF'
[General]
DisplayServer=wayland
DefaultSession=plasma.desktop

[Theme]
Current=breeze

[Wayland]
SessionDir=/usr/share/wayland-sessions
CompositorCommand=/usr/bin/kyth-sddm-compositor
SDDMCONFEOF

# System-wide session env: software compose only when there is no GPU render
# node. kyth.hwgl=1 forces hardware GL (GPU passthrough / virgl). Live media
# adds its own unconditional live.sh on top of this.
write_config /etc/xdg/plasma-workspace/env/10-kyth-software-compose.sh 0755 <<'COMPOSEEOF'
#!/bin/sh
if grep -qw 'kyth.hwgl=1' /proc/cmdline 2>/dev/null; then
	return 0 2>/dev/null || exit 0
fi
if ls /dev/dri/renderD* >/dev/null 2>&1; then
	return 0 2>/dev/null || exit 0
fi
export LIBGL_ALWAYS_SOFTWARE=1
export GALLIUM_DRIVER=llvmpipe
export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
export QT_QUICK_BACKEND=software
export KWIN_COMPOSE=Q
COMPOSEEOF

# theme.conf.user overrides the breeze SDDM theme defaults without modifying
# the upstream theme files. The wallpaper is already installed above.
write_config /usr/share/sddm/themes/breeze/theme.conf.user <<'SDDMEOF'
[General]
type=image
background=/usr/share/wallpapers/kyth/contents/images/1920x1080.svg
logo=/usr/share/pixmaps/kyth.svg
showlogo=shown
SDDMEOF

# Make enrolled fingerprints available to the login and screen-lock PAM stack.
# fprintd-pam provides the module; authselect activates it in Fedora's profile.
if command -v authselect >/dev/null 2>&1 && authselect current >/dev/null 2>&1; then
	authselect enable-feature with-fingerprint
fi
