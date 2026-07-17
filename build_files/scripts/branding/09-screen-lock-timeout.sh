# shellcheck shell=bash
# ── Screen lock timeout ───────────────────────────────────────────────────────
# Default auto-lock after 15 minutes of inactivity. KDE's stock default is 5
# minutes which is too aggressive for a desktop/gaming workstation.
cat >/etc/skel/.config/kscreenlockerrc <<'SCREENLOCKEOF'
[Daemon]
Autolock=true
LockGracePeriod=5
LockOnResume=true
Timeout=15

[Greeter][Wallpaper][org.kde.image][General]
Image=/usr/share/wallpapers/kyth/contents/images/1920x1080.svg
SCREENLOCKEOF
