# shellcheck shell=bash
# ── Update / first-login notification UX ──────────────────────────────────────
# The native kyth-update-watcher owns update checks and notifications. Do not
# install the retired PySide/Qt tray notifier or create a second update path.

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
