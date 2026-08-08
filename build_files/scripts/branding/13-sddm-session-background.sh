# shellcheck shell=bash
# ── SDDM session type + login screen background ───────────────────────────────
# Force X11 display server. Kinoite 44 / KDE 6.6 defaults to a Wayland session;
# KWin Wayland requires a working DRM/GBM backend and can crash on VM GPUs
# without 3D acceleration, which drops the SPICE
# connection and makes the VM appear to close. X11 is stable on all hardware
# and VM GPU drivers; users can switch to Wayland from the session picker.
write_config /etc/sddm.conf.d/10-kyth.conf <<'SDDMCONFEOF'
[General]
DisplayServer=x11
DefaultSession=plasmax11.desktop

[Theme]
Current=breeze

[X11]
SessionDir=/usr/share/xsessions
SDDMCONFEOF

# Software-rendering fallback for virtual machines: makes Plasma's X11 session
# usable when the VM display has no virgl/3D acceleration. Skipped on bare metal
# (systemd-detect-virt returns non-zero when not in a VM/container) and when
# kyth.hwgl=1 is in the cmdline to force hardware GL inside a VM.
write_config /etc/skel/.config/plasma-workspace/env/10-kyth-qemu-safe.sh 0755 <<'QEMUSAFEEOF'
#!/bin/sh
if systemd-detect-virt -q 2>/dev/null && ! grep -qw 'kyth.hwgl=1' /proc/cmdline 2>/dev/null; then
    export LIBGL_ALWAYS_SOFTWARE=1
    export GALLIUM_DRIVER=llvmpipe
    export MESA_LOADER_DRIVER_OVERRIDE=llvmpipe
    export QT_QUICK_BACKEND=software
fi
QEMUSAFEEOF

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
