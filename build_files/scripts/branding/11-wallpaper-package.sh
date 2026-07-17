# shellcheck shell=bash
# ── KythOS wallpaper package ────────────────────────────────────────────────────
# Install as a proper KDE wallpaper package so the L&F lookup 'Image=kyth' works.
mkdir -p /usr/share/wallpapers/kyth/contents/images
cp /ctx/wallpaper/kyth-wallpaper.svg \
	/usr/share/wallpapers/kyth/contents/images/1920x1080.svg
printf '{"KPlugin":{"Authors":[{"Name":"KythOS"}],"Id":"kyth","Name":"KythOS","License":"CC-BY-SA-4.0"},"KPackageStructure":"Wallpaper/Images"}\n' \
	>/usr/share/wallpapers/kyth/metadata.json

# Patch all L&F defaults (Fedora variants + Breeze) to use KythOS wallpaper.
# Fedora Kinoite ships org.fedoraproject.fedora*.desktop themes that set
# Image=Fedora; we replace that in every theme so no L&F can restore the
# stock Fedora rocket wallpaper.
find /usr/share/plasma/look-and-feel -name defaults | while read -r f; do
	sed -i 's/^Image=.*/Image=kyth/' "$f"
	grep -q '^Image=' "$f" || printf '\n[Wallpaper]\nImage=kyth\n' >>"$f"
done

# System-wide XDG fallback — applied to every user before their personal
# config exists, so first-boot always shows the KythOS wallpaper.
mkdir -p /etc/xdg
cat >/etc/xdg/plasma-org.kde.plasma.desktop-appletsrc <<'XDGPLASMAEOF'
[Containments][1][Wallpaper][org.kde.image][General]
Image=/usr/share/wallpapers/kyth/contents/images/1920x1080.svg
XDGPLASMAEOF
