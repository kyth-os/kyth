# shellcheck shell=bash
# ── User comfort polish ───────────────────────────────────────────────────────
install -m 0755 /ctx/kyth-user-polish /usr/bin/kyth-user-polish

cat >/usr/bin/kyth-windows-friendly-defaults <<'WINDEFAULTEOF'
#!/usr/bin/env bash
exec /usr/bin/kyth-user-polish "$@"
WINDEFAULTEOF
chmod +x /usr/bin/kyth-windows-friendly-defaults

install -m 0644 /ctx/kyth-scripts/kyth-user-polish.desktop \
	/etc/skel/.config/autostart/kyth-user-polish.desktop

install -m 0644 /etc/skel/.config/autostart/kyth-user-polish.desktop \
	/etc/xdg/autostart/kyth-user-polish.desktop
