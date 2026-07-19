# shellcheck shell=bash
# ── KythOS default Plasma layout preset ───────────────────────────────────────
install -m 0755 /ctx/kyth-apply-desktop-layout /usr/bin/kyth-apply-desktop-layout
install -m 0755 /ctx/kyth-refresh-taskbar-pins /usr/bin/kyth-refresh-taskbar-pins
install -m 0644 /ctx/kyth-scripts/kyth-refresh-taskbar-pins.service \
	/usr/lib/systemd/user/kyth-refresh-taskbar-pins.service
install -m 0644 /ctx/kyth-scripts/kyth-refresh-taskbar-pins.path \
	/usr/lib/systemd/user/kyth-refresh-taskbar-pins.path
mkdir -p /etc/systemd/user/default.target.wants
