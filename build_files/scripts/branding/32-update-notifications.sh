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

python3 -c '
import importlib.machinery, importlib.util, pathlib
path = pathlib.Path("/usr/bin/kyth-welcome")
loader = importlib.machinery.SourceFileLoader("kyth_welcome_smoke", str(path))
spec = importlib.util.spec_from_loader(loader.name, loader)
module = importlib.util.module_from_spec(spec)
loader.exec_module(module)
'
