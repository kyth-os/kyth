# shellcheck shell=bash
# ── User comfort polish ───────────────────────────────────────────────────────
install -m 0755 /ctx/kyth-user-polish /usr/bin/kyth-user-polish

write_config /usr/bin/kyth-windows-friendly-defaults 0755 <<'WINDEFAULTEOF'
#!/usr/bin/env bash
exec /usr/bin/kyth-user-polish "$@"
WINDEFAULTEOF

install -m 0644 /ctx/config/kyth-user-polish.service \
	/usr/lib/systemd/user/kyth-user-polish.service

mkdir -p /usr/lib/systemd/user/graphical-session.target.wants
ln -sfn /usr/lib/systemd/user/kyth-user-polish.service \
	/usr/lib/systemd/user/graphical-session.target.wants/kyth-user-polish.service

install -m 0644 /ctx/kyth-scripts/kyth-user-polish.desktop \
	/etc/skel/.config/autostart/kyth-user-polish.desktop

install -m 0644 /etc/skel/.config/autostart/kyth-user-polish.desktop \
	/etc/xdg/autostart/kyth-user-polish.desktop

