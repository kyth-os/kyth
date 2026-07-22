# shellcheck shell=bash
# Plasma starts a separate KSplash process after Plymouth and the display
# manager. Own that late boot stage instead of inheriting an upstream look-and-
# feel splash from Fedora/KDE packages.
splash_root=/usr/share/plasma/look-and-feel/org.kythos.desktop
install -d -m 0755 \
	"${splash_root}/contents/splash/images" \
	/etc/xdg \
	/etc/skel/.config
install -m 0644 /ctx/branding/plasma-splash/metadata.json \
	"${splash_root}/metadata.json"
install -m 0644 /ctx/branding/plasma-splash/contents/splash/Splash.qml \
	"${splash_root}/contents/splash/Splash.qml"
install -m 0644 /ctx/branding/kyth-logo-transparent.svg \
	"${splash_root}/contents/splash/images/kyth-logo.svg"

cat >/etc/xdg/ksplashrc <<'KSPLASHEOF'
[KSplash]
Engine=KSplashQML
Theme=org.kythos.desktop
KSPLASHEOF
install -m 0644 /etc/xdg/ksplashrc /etc/skel/.config/ksplashrc
