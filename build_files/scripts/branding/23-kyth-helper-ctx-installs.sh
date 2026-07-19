# shellcheck shell=bash
# ── KythOS Helper app — /ctx file installs ──────────────────────────────────────
install -m 0755 /ctx/kyth-welcome/kyth-welcome /usr/bin/kyth-welcome
# /usr/bin/kyth-welcome is a thin shim; the application package lives here.
mkdir -p /usr/lib/kyth-welcome
cp -a /ctx/kyth-welcome/kyth_welcome /usr/lib/kyth-welcome/
rm -rf /usr/lib/kyth-welcome/kyth_welcome/__pycache__
# kyth_welcome.__init__ resolves kyth_shared via sys.path at
# (file parent).parent.parent / "kyth_shared" → /usr/kyth_shared.
mkdir -p /usr/kyth_shared
cp -a /ctx/kyth_shared/kyth_shared /usr/kyth_shared/
rm -rf /usr/kyth_shared/kyth_shared/__pycache__
find /usr/lib/kyth-welcome -type d -exec chmod 0755 {} +
find /usr/lib/kyth-welcome -type f -exec chmod 0644 {} +
install -m 0755 /ctx/kyth-welcome/kyth-welcome-launch /usr/bin/kyth-welcome-launch
install -m 0644 /ctx/kyth-welcome/kyth-welcome.desktop \
	/usr/share/applications/kyth-welcome.desktop
cat >/usr/share/applications/kyth-app-store.desktop <<'APPSTOREEOF'
[Desktop Entry]
Type=Application
Name=KythOS App Store
GenericName=App Store
Comment=Find and install trusted apps on KythOS
Exec=/usr/bin/kyth-welcome-launch --page "App Store"
Icon=plasmadiscover
Terminal=false
Categories=Settings;PackageManager;
Keywords=apps;store;software;flatpak;install;remove;
StartupNotify=true
StartupWMClass=kyth-welcome
APPSTOREEOF
install -m 0755 /ctx/kyth-partition-install.sh /usr/bin/kyth-partition-install

# Place System Hub on the desktop for all new users. The executable bit is
# required so KDE Plasma 6 treats it as trusted without prompting the user.
mkdir -p /etc/skel/Desktop
install -m 0755 /ctx/kyth-welcome/kyth-welcome.desktop \
	/etc/skel/Desktop/kyth-welcome.desktop

# Recycle Bin on the desktop keeps deletion recovery visible. Type=Link entries
# open in Dolphin and need no executable/trust bit. Kept in /usr/share/kyth so
# the user-polish pass can seed existing accounts too.
mkdir -p /usr/share/kyth
cat >/usr/share/kyth/kyth-recycle-bin.desktop <<'TRASHEOF'
[Desktop Entry]
Type=Link
URL=trash:/
Name=Recycle Bin
GenericName=Trash
Icon=user-trash
TRASHEOF
install -m 0644 /usr/share/kyth/kyth-recycle-bin.desktop \
	/etc/skel/Desktop/kyth-recycle-bin.desktop
