# shellcheck shell=bash
# ── KythOS Helper app — packaged Python install ───────────────────────────────
# /ctx is a read-only BuildKit bind mount. Setuptools creates build metadata
# beside a local project, so stage the package in the writable build tmpfs.
welcome_package_dir="$(mktemp -d /tmp/kyth-welcome-package.XXXXXX)"
cp -a /ctx/kyth-welcome/. "${welcome_package_dir}/"
cp -a /ctx/kyth-installer "${welcome_package_dir}/kyth-installer"
python3 -m pip install \
	--no-cache-dir \
	--no-deps \
	--no-build-isolation \
	--prefix=/usr \
	"${welcome_package_dir}" \
	"${welcome_package_dir}/kyth-installer"
rm -rf "${welcome_package_dir}"
unset welcome_package_dir
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
install -m 0755 /ctx/kyth-network-share /usr/libexec/kyth-network-share
install -m 0755 /ctx/kyth-set-sleep-mode /usr/libexec/kyth-set-sleep-mode
install -m 0755 /ctx/kyth-retry-hardware-setup /usr/libexec/kyth-retry-hardware-setup

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
