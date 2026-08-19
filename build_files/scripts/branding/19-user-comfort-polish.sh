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

# The systemd user unit above is the single launcher for kyth-user-polish. The
# old XDG autostart entries (both the /etc/skel copy and the system-wide
# /etc/xdg/autostart copy) are intentionally NOT installed: shipping them
# alongside the unit made the polish run twice, concurrently, at every login —
# two processes writing the same KDE config (kwriteconfig, kyth-apply-desktop-
# layout --force, sycoca rebuild) and racing each other. kyth-user-polish's own
# cleanup_autostart() still prunes any leftover ~/.config/autostart copy from
# systems that were installed before this change.

