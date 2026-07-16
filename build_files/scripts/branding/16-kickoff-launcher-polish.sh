# shellcheck shell=bash
# ── First-login script: polish Kickoff launcher defaults ──────────────────────
# Belt-and-suspenders: the icon theme install above should be enough, but this
# also writes the icon key directly into each user's Kickoff applet config in
# case the theme lookup is overridden by a previously cached value. It also
# disables Plasma's newly-installed app badges so KythOS launchers land in
# their categories without green dots or "New!" labels.
cat >/usr/bin/kyth-set-kickoff-icon <<'KICKOFEOF'
#!/usr/bin/env python3
import os, re, shutil, subprocess

aprc = os.path.expanduser("~/.config/plasma-org.kde.plasma.desktop-appletsrc")
autostart = os.path.expanduser("~/.config/autostart/kyth-set-kickoff-icon.desktop")
kwriteconfig = shutil.which('kwriteconfig6')

if kwriteconfig:
    subprocess.run([
        kwriteconfig, '--file', 'kickoffrc',
        '--group', 'General',
        '--key', 'highlightNewlyInstalledApps',
        '--type', 'bool', 'false',
    ], check=False)

if kwriteconfig and os.path.exists(aprc):
    content = open(aprc).read()
    for m in re.finditer(
        r'^\[Containments\]\[(\d+)\]\[Applets\]\[(\d+)\]',
        content, re.MULTILINE
    ):
        cont, applet = m.group(1), m.group(2)
        body_start = m.end()
        nxt = re.search(r'^\[', content[body_start:], re.MULTILINE)
        body = content[body_start: body_start + nxt.start()] if nxt else content[body_start:]
        if 'plugin=org.kde.plasma.kickoff' in body:
            subprocess.run([
                kwriteconfig, '--file', aprc,
                '--group', 'Containments', '--group', cont,
                '--group', 'Applets', '--group', applet,
                '--group', 'Configuration', '--group', 'General',
                '--key', 'icon', 'kyth-kickoff',
            ], check=False)
            subprocess.run([
                kwriteconfig, '--file', aprc,
                '--group', 'Containments', '--group', cont,
                '--group', 'Applets', '--group', applet,
                '--group', 'Configuration', '--group', 'General',
                '--key', 'highlightNewlyInstalledApps',
                '--type', 'bool', 'false',
            ], check=False)

try:
    os.unlink(autostart)
except OSError:
    pass
KICKOFEOF
chmod +x /usr/bin/kyth-set-kickoff-icon

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

