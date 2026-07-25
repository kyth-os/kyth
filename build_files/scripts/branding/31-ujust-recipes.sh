# shellcheck shell=bash
# ── ujust recipes ─────────────────────────────────────────────────────────────
# Install KythOS-specific ujust recipes so users can run e.g. "ujust rebase kyth:stable".
mkdir -p /usr/share/ublue-os/just
cp /ctx/just/kyth.just /usr/share/ublue-os/just/75-kyth.just
# kyth.just imports its per-domain recipe files from kyth/ next to itself
# (just resolves imports relative to the importing file), so that directory
# ships alongside it here.
cp -r /ctx/just/kyth /usr/share/ublue-os/just/kyth
# The upstream justfile only imports up to 60-custom.just; wire in our file.
printf '\nimport? "/usr/share/ublue-os/just/75-kyth.just"\n' >>/usr/share/ublue-os/justfile
# Unit files installed here (not just before, elsewhere) since `systemctl
# enable` below needs each one to already exist — see
# branding/36-misc-utility-installs.sh for the matching binaries.
install -m 0644 /ctx/kyth-local-bin-migrate.service /usr/lib/systemd/system/kyth-local-bin-migrate.service
install -m 0644 /ctx/kyth-duperemove.service /usr/lib/systemd/system/kyth-duperemove.service
install -m 0644 /ctx/kyth-duperemove.timer /usr/lib/systemd/system/kyth-duperemove.timer
install -m 0644 /ctx/kyth-scx-loader.service /usr/lib/systemd/system/scx_loader.service
systemctl enable kyth-local-bin-migrate.service 2>/dev/null || true
systemctl enable kyth-duperemove.timer 2>/dev/null || true
systemctl --global enable kyth-proton-cachyos-update.timer 2>/dev/null || true
# Without wait-online, network-online.target is reached instantly and the
# flatpak units below race DNS at boot and fail. Enabling it only delays
# units ordered After=network-online.target, not the rest of boot.
systemctl enable NetworkManager-wait-online.service 2>/dev/null || true
systemctl enable kyth-flathub-setup.service 2>/dev/null || true
systemctl enable kyth-default-flatpaks.service 2>/dev/null || true
systemctl enable kyth-hw-setup.service 2>/dev/null || true
systemctl enable kyth-update-watcher.timer 2>/dev/null || true
systemctl enable kyth-probe.timer 2>/dev/null || true
if command -v scx_rusty >/dev/null 2>&1; then
	systemctl --global enable kyth-sched.service 2>/dev/null || true
fi
systemctl --global enable kyth-telem.service 2>/dev/null || true
systemctl --global enable kyth-probe.timer 2>/dev/null || true
