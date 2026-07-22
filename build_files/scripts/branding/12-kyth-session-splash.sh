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
install -m 0755 /ctx/kyth-session-splash-guard \
	/usr/bin/kyth-session-splash-guard

cat >/etc/xdg/ksplashrc <<'KSPLASHEOF'
[KSplash]
Engine=KSplashQML
Theme=org.kythos.desktop
KSPLASHEOF
install -m 0644 /etc/xdg/ksplashrc /etc/skel/.config/ksplashrc

# Existing accounts can already have an explicit upstream theme in their own
# ksplashrc, which takes precedence over /etc/xdg. Repair it immediately before
# Plasma renders the splash so the first login after an update is branded too.
install -d -m 0755 /usr/lib/systemd/user/plasma-ksplash.service.d
cat >/usr/lib/systemd/user/plasma-ksplash.service.d/20-kyth-branding.conf <<'KSPLASHDROPEOF'
[Service]
ExecStartPre=/usr/bin/kyth-session-splash-guard
KSPLASHDROPEOF
