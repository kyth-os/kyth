#!/bin/bash
# Plymouth boot splash setup — runs as a standalone Dockerfile layer so Docker
# can cache the expensive dracut rebuild independently of the daily branding layer.
# Source files are COPY'd from the build context to /tmp/kyth-plymouth/ and
# /tmp/kyth-branding/ before this script is called.

set -euo pipefail

PLYMOUTH_THEME_DIR=/usr/share/plymouth/themes/kyth
mkdir -p "${PLYMOUTH_THEME_DIR}"

write_kyth_os_release() {
	local target=$1
	mkdir -p "$(dirname "${target}")"
	cat >"${target}" <<'EOF'
NAME="KythOS"
PRETTY_NAME="KythOS 44"
ID=kythos
VERSION="44"
VERSION_ID="44"
ANSI_COLOR="0;34"
LOGO=kyth
HOME_URL="https://github.com/mrtrick37/kyth"
SUPPORT_URL="https://github.com/mrtrick37/kyth/discussions"
BUG_REPORT_URL="https://github.com/mrtrick37/kyth/issues"
EOF
}

write_kyth_os_release /usr/lib/os-release
rm -f /etc/os-release
write_kyth_os_release /etc/os-release

rsvg-convert -w 256 /tmp/kyth-branding/kyth-logo-transparent.svg \
	-o "${PLYMOUTH_THEME_DIR}/kyth-logo.png"
install -m 0644 /tmp/kyth-plymouth/kyth.plymouth "${PLYMOUTH_THEME_DIR}/"
install -m 0644 /tmp/kyth-plymouth/kyth.script "${PLYMOUTH_THEME_DIR}/"

# Replace Fedora watermarks in every Plymouth fallback theme with transparent
# assets. This guard is installed permanently and rerun after later package
# transactions because dnf upgrades can restore upstream theme files.
install -Dm0755 /tmp/plymouth-branding-guard.sh \
	/usr/libexec/kyth-plymouth-branding-guard
/usr/libexec/kyth-plymouth-branding-guard \
	/tmp/kyth-branding/transparent-watermark.svg

# The guard owns the late 99kyth-plymouth dracut module. Keep setup focused on
# the theme files and host defaults so there is one generated module body.
mkdir -p /etc/plymouth /usr/share/plymouth
cat >/etc/plymouth/plymouthd.conf <<'PLYMOUTHCONF'
[Daemon]
Theme=kyth
ShowDelay=0
DeviceTimeout=8
UseFirmwareBackground=false
PLYMOUTHCONF
install -m 0644 /etc/plymouth/plymouthd.conf /usr/share/plymouth/plymouthd.defaults

mkdir -p /etc/dracut.conf.d
if [[ -f /etc/dracut.conf.d/99-kyth.conf ]]; then
	grep -q 'add_dracutmodules+=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf ||
		printf '\nadd_dracutmodules+=" kyth-plymouth "\n' >>/etc/dracut.conf.d/99-kyth.conf
else
	cat >/etc/dracut.conf.d/99-kyth.conf <<'DRACUTEOF'
add_dracutmodules+=" ostree drm plymouth kyth-plymouth "
DRACUTEOF
fi
grep -q 'force_add_dracutmodules+=.*kyth-plymouth' /etc/dracut.conf.d/99-kyth.conf ||
	printf 'force_add_dracutmodules+=" kyth-plymouth "\n' >>/etc/dracut.conf.d/99-kyth.conf

plymouth-set-default-theme kyth
