# shellcheck shell=bash
# ── KythOS icons ───────────────────────────────────────────────────────────────
# KDE Plasma 6 Kickoff looks up icons in this order:
#   start-here-kde-plasma → start-here-kde → start-here
# Boot and display-manager components resolve /etc/os-release LOGO=kyth through
# the same icon stack, while GRUB themes key off BLS grub_class names. Install
# both KythOS-native names and Fedora-compatible overrides so stale boot entries
# cannot render the inherited Fedora badge.
# Two failure modes to defeat:
#   1. fedora-logos ships PNGs at exact pixel sizes; Qt/Plasma prefers an
#      exact-size PNG over a scalable SVG, so the Fedora icon won at lookup.
#   2. The Kickoff plasmoid's default icon is "", which falls back to the theme
#      lookup — so a cached/stale Fedora logo survived into the applet.
# Fix: install PNGs at every standard size AND patch Kickoff's main.xml so the
# compiled-in default is kyth-kickoff, requiring no per-user config at all.

# Scalable SVGs (also used by the kyth-set-kickoff-icon first-login script)
for theme_dir in \
	/usr/share/icons/hicolor/scalable/apps \
	/usr/share/icons/breeze/apps/scalable \
	/usr/share/icons/breeze-dark/apps/scalable; do
	mkdir -p "${theme_dir}"
	cp /ctx/branding/kyth-logo-transparent.svg "${theme_dir}/kyth.svg"
	cp /ctx/branding/kyth-logo-transparent.svg "${theme_dir}/kyth-symbol.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/kythos.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/kyth-kickoff.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/distributor-logo.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/fedora-logo-icon.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/start-here.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/start-here-kde.svg"
	cp /ctx/branding/kyth-kickoff.svg "${theme_dir}/start-here-kde-plasma.svg"
done

# PNGs at every standard size — beats inherited exact-size Fedora PNGs at lookup
for sz in 16 22 24 32 48 64 128 256; do
	for base in /usr/share/icons/hicolor /usr/share/icons/breeze /usr/share/icons/breeze-dark; do
		dir="${base}/${sz}x${sz}/apps"
		mkdir -p "${dir}"
		rsvg-convert -w "${sz}" -h "${sz}" /ctx/branding/kyth-kickoff.svg \
			-o "${dir}/kyth-kickoff.png"
		rsvg-convert -w "${sz}" -h "${sz}" /ctx/branding/kyth-logo-transparent.svg \
			-o "${dir}/kyth.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/kythos.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/distributor-logo.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/fedora-logo-icon.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/start-here.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/start-here-kde.png"
		cp "${dir}/kyth-kickoff.png" "${dir}/start-here-kde-plasma.png"
	done
done

# Extra legacy lookup locations used by boot menus, display managers, and older
# GTK/KDE code paths. The Fedora-named files intentionally contain KythOS art:
# some existing BLS snippets still say grub_class=fedora until the migration
# below has run.
mkdir -p /usr/share/pixmaps
cp /ctx/branding/kyth-logo-transparent.svg /usr/share/pixmaps/kyth.svg
cp /ctx/branding/kyth-kickoff.svg /usr/share/pixmaps/kythos.svg
cp /ctx/branding/kyth-kickoff.svg /usr/share/pixmaps/distributor-logo.svg
cp /ctx/branding/kyth-kickoff.svg /usr/share/pixmaps/fedora-logo-icon.svg
rsvg-convert -w 64 -h 64 /ctx/branding/kyth-logo-transparent.svg -o /usr/share/pixmaps/kyth.png
rsvg-convert -w 64 -h 64 /ctx/branding/kyth-kickoff.svg -o /usr/share/pixmaps/kythos.png
cp /usr/share/pixmaps/kythos.png /usr/share/pixmaps/distributor-logo.png
cp /usr/share/pixmaps/kythos.png /usr/share/pixmaps/fedora-logo-icon.png

for grub_icon_dir in \
	/boot/grub2/themes/system/icons \
	/boot/grub2/themes/starfield/icons \
	/usr/share/grub/themes/system/icons \
	/usr/share/grub/themes/starfield/icons; do
	mkdir -p "${grub_icon_dir}"
	for icon in kyth kythos fedora gnu-linux linux; do
		rsvg-convert -w 32 -h 32 /ctx/branding/kyth-kickoff.svg \
			-o "${grub_icon_dir}/${icon}.png"
	done
done

mkdir -p /etc/default
if [[ -f /etc/default/grub ]]; then
	if grep -q '^GRUB_DISTRIBUTOR=' /etc/default/grub; then
		sed -i 's/^GRUB_DISTRIBUTOR=.*/GRUB_DISTRIBUTOR="KythOS"/' /etc/default/grub
	else
		printf '\nGRUB_DISTRIBUTOR="KythOS"\n' >>/etc/default/grub
	fi
else
	printf 'GRUB_DISTRIBUTOR="KythOS"\n' >/etc/default/grub
fi

# Microsoft 365 web-app shortcut icons (referenced by the .desktop entries the
# kyth-welcome Work Setup page writes; without them Kickoff shows a generic globe).
for app in outlook word excel powerpoint onenote teams; do
	cp "/ctx/branding/m365/kyth-m365-${app}.svg" \
		/usr/share/icons/hicolor/scalable/apps/
	for sz in 16 22 24 32 48 64 128 256; do
		dir="/usr/share/icons/hicolor/${sz}x${sz}/apps"
		mkdir -p "${dir}"
		rsvg-convert -w "${sz}" -h "${sz}" "/ctx/branding/m365/kyth-m365-${app}.svg" \
			-o "${dir}/kyth-m365-${app}.png"
	done
done

# Clear any stale caches so the new icons take effect immediately on first boot.
rm -f /usr/share/icons/hicolor/icon-theme.cache
rm -f /usr/share/icons/breeze/icon-theme.cache
rm -f /usr/share/icons/breeze-dark/icon-theme.cache
gtk-update-icon-cache -f /usr/share/icons/hicolor/ 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/breeze/ 2>/dev/null || true
gtk-update-icon-cache -f /usr/share/icons/breeze-dark/ 2>/dev/null || true

