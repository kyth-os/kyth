# shellcheck shell=bash
# ── Update / first-login notification UX ──────────────────────────────────────
install -m 0755 /ctx/kyth-welcome/kyth-update-notifier /usr/bin/kyth-update-notifier
install -m 0644 /ctx/kyth-welcome/kyth-update-notifier.desktop \
	/usr/share/applications/kyth-update-notifier.desktop
mkdir -p /etc/skel/.config/autostart
install -m 0644 /ctx/kyth-welcome/kyth-update-notifier.desktop \
	/etc/skel/.config/autostart/kyth-update-notifier.desktop

write_config /etc/xdg/autostart/kyth-post-update-check.desktop <<'POSTUPDATEAUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS Post-Update Check
Exec=/usr/bin/kyth-post-update-check --no-notify
NoDisplay=true
X-KDE-autostart-after=panel
POSTUPDATEAUTOSTARTEOF

write_config /etc/xdg/autostart/kyth-firstboot-app-status.desktop <<'APPSTATUSAUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS App Setup Status
Exec=/usr/bin/kyth-firstboot-app-status
NoDisplay=true
X-KDE-autostart-after=panel
APPSTATUSAUTOSTARTEOF

write_config /etc/xdg/autostart/kyth-steam-game-export.desktop <<'STEAMEXPORTAUTOSTARTEOF'
[Desktop Entry]
Type=Application
Name=KythOS Steam Game Menu Export
Exec=/usr/bin/kyth-steam-game-export
NoDisplay=true
X-KDE-autostart-after=panel
STEAMEXPORTAUTOSTARTEOF

# Build-time syntax check only; the notifier imports shared services and does
# not depend on the retired Python/Qt Hub package being installed.
python3 -c 'import ast, pathlib; ast.parse(pathlib.Path("/usr/bin/kyth-update-notifier").read_text())'
