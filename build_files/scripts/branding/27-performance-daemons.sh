# shellcheck shell=bash
# ── KythOS performance daemons ────────────────────────────────────────────────
install -m 0755 /ctx/kyth-sched /usr/bin/kyth-sched
install -m 0644 /ctx/kyth-sched.service /usr/lib/systemd/user/kyth-sched.service

install -m 0755 /ctx/kyth-telem /usr/bin/kyth-telem
install -m 0644 /ctx/kyth-telem.service /usr/lib/systemd/user/kyth-telem.service

install -m 0755 /ctx/kyth-update-watcher /usr/bin/kyth-update-watcher
install -m 0644 /ctx/kyth-update-watcher.service /usr/lib/systemd/system/kyth-update-watcher.service
install -m 0644 /ctx/kyth-update-watcher.timer /usr/lib/systemd/system/kyth-update-watcher.timer

# Zero-Python update escape hatch — works even when KythOS Hub is broken.
install -m 0755 /ctx/kyth-apply-update /usr/bin/kyth-apply-update
install -m 0644 /ctx/kyth-apply-update.desktop /usr/share/applications/kyth-apply-update.desktop

mkdir -p /etc/kyth
install -m 0644 /ctx/kyth-sched-profiles.toml /etc/kyth/sched-profiles.toml
install -m 0644 /ctx/auto-update.toml /etc/kyth/auto-update.toml
install -m 0644 /ctx/kyth-asus-supergfxd.rules /usr/lib/udev/rules.d/98-kyth-asus-supergfxd.rules

# Autostart on first login — removes itself after running once (like kyth-set-resolution).
mkdir -p /etc/skel/.config/autostart
cat >/etc/skel/.config/autostart/kyth-welcome.desktop <<'WELCOMEEOF'
[Desktop Entry]
Type=Application
Name=KythOS Helper
Exec=/usr/bin/kyth-welcome-launch
X-KDE-autostart-after=panel
Hidden=false
NoDisplay=true
WELCOMEEOF

