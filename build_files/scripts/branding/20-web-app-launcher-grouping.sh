# shellcheck shell=bash
# ── Web app launcher grouping ─────────────────────────────────────────────────
# Chromium-family browsers create PWA launchers without Categories=. KDE cannot
# classify those launchers and drops them into Lost and Found. Add a custom
# category only when the browser did not provide one, preserving any category a
# user assigns later with the menu editor.
cat >/usr/bin/kyth-web-app-categorize <<'WEBAPPCATEGORIZEEOF'
#!/usr/bin/env bash
set -euo pipefail

app_dir="${HOME}/.local/share/applications"
[[ -d "${app_dir}" ]] || exit 0

changed=0
shopt -s nullglob
for launcher in \
    "${app_dir}"/chrome-*.desktop \
    "${app_dir}"/chromium-*.desktop \
    "${app_dir}"/brave-*.desktop \
    "${app_dir}"/msedge-*.desktop \
    "${app_dir}"/com.google.Chrome.flextop.*.desktop \
    "${app_dir}"/org.chromium.Chromium.flextop.*.desktop \
    "${app_dir}"/com.brave.Browser.flextop.*.desktop \
    "${app_dir}"/com.microsoft.Edge.flextop.*.desktop; do
    grep -Eq -- '--app(-id)?=' "${launcher}" || continue
    grep -q '^Categories=' "${launcher}" && continue
    sed -i '/^\[Desktop Entry\]$/a Categories=X-KythWebApp;' "${launcher}"
    changed=1
done

if (( changed )) && command -v kbuildsycoca6 >/dev/null 2>&1; then
    kbuildsycoca6 --noincremental >/dev/null 2>&1 || true
fi
WEBAPPCATEGORIZEEOF
chmod +x /usr/bin/kyth-web-app-categorize

mkdir -p /etc/systemd/user/default.target.wants
cat >/etc/systemd/user/kyth-web-app-categorize.service <<'WEBAPPSERVICEEOF'
[Unit]
Description=Place browser-installed web apps in the Web Apps launcher folder

[Service]
Type=oneshot
ExecStart=/usr/bin/kyth-web-app-categorize
WEBAPPSERVICEEOF

cat >/etc/systemd/user/kyth-web-app-categorize.path <<'WEBAPPPATHEOF'
[Unit]
Description=Watch for browser-installed web app launchers

[Path]
PathChanged=%h/.local/share/applications
Unit=kyth-web-app-categorize.service

[Install]
WantedBy=default.target
WEBAPPPATHEOF
ln -sf /etc/systemd/user/kyth-web-app-categorize.path \
	/etc/systemd/user/default.target.wants/kyth-web-app-categorize.path

# Seed the same familiar folder layout into fresh homes. The autostart helper
# repairs these for existing users and for accounts created by unusual tools.
mkdir -p \
	/etc/skel/Desktop \
	/etc/skel/Documents \
	/etc/skel/Downloads \
	/etc/skel/Games \
	/etc/skel/Music \
	/etc/skel/Pictures \
	/etc/skel/Public \
	/etc/skel/Templates \
	/etc/skel/Videos

cat >/etc/skel/Games/.directory <<'GAMESDIREEOF'
[Desktop Entry]
Icon=applications-games
Name=Games
GAMESDIREEOF

cat >/etc/skel/.config/user-dirs.dirs <<'USERDIRSEOF'
XDG_DESKTOP_DIR="$HOME/Desktop"
XDG_DOWNLOAD_DIR="$HOME/Downloads"
XDG_TEMPLATES_DIR="$HOME/Templates"
XDG_PUBLICSHARE_DIR="$HOME/Public"
XDG_DOCUMENTS_DIR="$HOME/Documents"
XDG_MUSIC_DIR="$HOME/Music"
XDG_PICTURES_DIR="$HOME/Pictures"
XDG_VIDEOS_DIR="$HOME/Videos"
USERDIRSEOF

cat >/etc/skel/.config/plasma-org.kde.plasma.desktop-appletsrc <<'PLASMADESKTOPEOF'
[Containments][1]
wallpaperplugin=org.kde.image

[Containments][1][Wallpaper][org.kde.image][General]
Image=/usr/share/wallpapers/kyth/contents/images/1920x1080.svg
PLASMADESKTOPEOF
