# shellcheck shell=bash
# ── KythOS default Plasma layout preset ───────────────────────────────────────
# kyth-apply-desktop-layout is the native Rust binary copied from the
# hub-web-builder stage; no Python launcher remains in the source tree.
# kyth-refresh-taskbar-pins is likewise native; no Python launcher remains.
install -m 0644 /ctx/kyth-scripts/kyth-refresh-taskbar-pins.service \
	/usr/lib/systemd/user/kyth-refresh-taskbar-pins.service
install -m 0644 /ctx/kyth-scripts/kyth-refresh-taskbar-pins.path \
	/usr/lib/systemd/user/kyth-refresh-taskbar-pins.path
mkdir -p /etc/systemd/user/default.target.wants
# The .path unit carries no [Install] section, so enable-by-name is
# impossible; wire the wants symlink directly.
ln -sf /usr/lib/systemd/user/kyth-refresh-taskbar-pins.path \
	/etc/systemd/user/default.target.wants/kyth-refresh-taskbar-pins.path
