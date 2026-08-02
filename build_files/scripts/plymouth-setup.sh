#!/bin/bash
# Plymouth boot splash setup — runs as a standalone Dockerfile layer so Docker
# can cache the expensive dracut rebuild independently of the daily branding layer.
# Source files are COPY'd from the build context to /tmp/kyth-plymouth/ and
# /tmp/kyth-branding/ before this script is called.

set -euo pipefail

# shellcheck source=lib/plymouth-config.sh disable=SC1091
source "lib/plymouth-config.sh"

PLYMOUTH_THEME_DIR=/usr/share/plymouth/themes/kyth
mkdir -p "${PLYMOUTH_THEME_DIR}"

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
printf '%s\n' "${KYTH_PLYMOUTHD_CONF}" >/etc/plymouth/plymouthd.conf
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
# See build_base/build.sh for why: util-linux hardlink's AF_ALG crypto-API
# file comparison reliably SIGSEGVs dracut's dedup pass in containerized
# builders (util-linux/util-linux#4334).
grep -q 'do_hardlink=' /etc/dracut.conf.d/99-kyth.conf ||
	printf 'do_hardlink="no"\n' >>/etc/dracut.conf.d/99-kyth.conf
# systemd-tmpfiles and udev run inside the initramfs before the real root's NSS
# databases are available. Include the repaired account files so stock rules can
# resolve groups such as disk, audio, kvm, tty, and tss during early boot.
grep -q 'install_items+=.*etc/passwd' /etc/dracut.conf.d/99-kyth.conf ||
	printf 'install_items+=" /etc/passwd /etc/group "\n' >>/etc/dracut.conf.d/99-kyth.conf

plymouth-set-default-theme kyth
