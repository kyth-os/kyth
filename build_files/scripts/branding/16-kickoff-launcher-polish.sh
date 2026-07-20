# shellcheck shell=bash
# ── First-login script: polish Kickoff launcher defaults ──────────────────────
# Belt-and-suspenders: the icon theme install above should be enough, but this
# also writes the icon key directly into each user's Kickoff applet config in
# case the theme lookup is overridden by a previously cached value. It also
# disables Plasma's newly-installed app badges so KythOS launchers land in
# their categories without green dots or "New!" labels.
install -m 0755 /ctx/kyth-set-kickoff-icon /usr/bin/kyth-set-kickoff-icon

mkdir -p /etc/skel/.config/autostart
cat >/etc/skel/.config/autostart/kyth-set-kickoff-icon.desktop <<'AUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS: Set Kickoff Icon
Exec=/usr/bin/kyth-set-kickoff-icon
X-KDE-autostart-after=panel
Hidden=false
NoDisplay=true
AUTOSTARTEOF

mkdir -p /etc/xdg/autostart
install -m 0644 /etc/skel/.config/autostart/kyth-set-kickoff-icon.desktop \
	/etc/xdg/autostart/kyth-set-kickoff-icon.desktop
