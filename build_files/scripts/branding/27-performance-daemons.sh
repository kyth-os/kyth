# shellcheck shell=bash
# ── KythOS performance daemons ────────────────────────────────────────────────
install -m 0755 /ctx/kyth-sched /usr/bin/kyth-sched
install -m 0644 /ctx/kyth-sched.service /usr/lib/systemd/user/kyth-sched.service

install -m 0755 /ctx/kyth-telem /usr/bin/kyth-telem
install -m 0644 /ctx/kyth-telem.service /usr/lib/systemd/user/kyth-telem.service

install -m 0755 /ctx/kyth-ai-perfd /usr/bin/kyth-ai-perfd
install -m 0644 /ctx/kyth-ai-perfd.service /usr/lib/systemd/user/kyth-ai-perfd.service

install -m 0755 /ctx/kyth-update-watcher /usr/bin/kyth-update-watcher
install -m 0644 /ctx/kyth-update-watcher.service /usr/lib/systemd/system/kyth-update-watcher.service
install -m 0644 /ctx/kyth-update-watcher.timer /usr/lib/systemd/system/kyth-update-watcher.timer

# Pre-create the fwupd cross-process lock (kyth_shared/system/firmware.py:
# stage_firmware_batch, kyth-full-update, Hub's page_update_firmware flock
# around it) so an unprivileged caller can flock(2) it too: flock only needs
# an open fd, not write access, but /run itself is not world-writable for
# *creating* new files, so the path must already exist before a non-root
# process can open it. Recreated every boot since /run is tmpfs.
install -m 0644 /dev/stdin /usr/lib/tmpfiles.d/kyth-fwupd-lock.conf <<'FWUPDLOCKEOF'
f /run/kyth-fwupd.lock 0644 root root -
FWUPDLOCKEOF

# Declarative cgroup gaming slice — hash-gated, offline
install -m 0644 /ctx/gaming.slice /usr/lib/systemd/system/gaming.slice

# Shared probe cache — warms bootc/flatpak/nvidia for System Hub cold starts.
install -m 0755 /ctx/kyth-probe /usr/bin/kyth-probe
install -m 0644 /ctx/kyth-probe.service /usr/lib/systemd/system/kyth-probe.service
install -m 0644 /ctx/kyth-probe.timer /usr/lib/systemd/system/kyth-probe.timer

install -m 0644 /ctx/kyth-guardian.service /usr/lib/systemd/user/kyth-guardian.service
install -m 0644 /ctx/kyth-guardian.timer /usr/lib/systemd/user/kyth-guardian.timer
install -m 0644 /ctx/kyth-guardian.path /usr/lib/systemd/user/kyth-guardian.path
install -m 0755 /ctx/kyth-guardian /usr/bin/kyth-guardian
install -Dm0644 /ctx/config/guardian-model.json /usr/share/kyth/guardian-model.json

# tmpfs + persistent system cache dir
mkdir -p /var/cache/kyth
# Ensure unit names match WantedBy installs (user units ship as kyth-probe.*)
# (files above already use kyth-probe.service / .timer under user/)

# Graphical-Hub-independent update escape hatch.
install -m 0755 /ctx/kyth-apply-update /usr/bin/kyth-apply-update
install -m 0644 /ctx/kyth-apply-update.desktop /usr/share/applications/kyth-apply-update.desktop

mkdir -p /etc/kyth
install -m 0644 /ctx/kyth-sched-profiles.toml /etc/kyth/sched-profiles.toml
install -m 0644 /ctx/auto-update.toml /etc/kyth/auto-update.toml
install -m 0644 /ctx/kyth-asus-supergfxd.rules /usr/lib/udev/rules.d/98-kyth-asus-supergfxd.rules

# Autostart on first login — removes itself after running once (like kyth-set-resolution).
write_config /etc/skel/.config/autostart/kyth-welcome.desktop <<'WELCOMEEOF'
[Desktop Entry]
Type=Application
Name=KythOS Helper
Exec=/usr/bin/kyth-welcome-launch
X-KDE-autostart-after=panel
Hidden=false
NoDisplay=true
WELCOMEEOF
