#!/bin/bash
# Rebuild the boot splash initramfs after final branding lands, then assert
# the branded Plymouth theme (and none of the distro fallback themes) made
# it in. Run after scripts/branding.sh in the same image layer.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/find-kver.sh disable=SC1091
source "${SCRIPT_DIR}/lib/find-kver.sh"
# shellcheck source=lib/plymouth-initrd-checks.sh disable=SC1091
source "${SCRIPT_DIR}/lib/plymouth-initrd-checks.sh"
# shellcheck source=lib/plymouth-config.sh disable=SC1091
source "${SCRIPT_DIR}/lib/plymouth-config.sh"
# shellcheck source=lib/dracut-retry.sh disable=SC1091
source "${SCRIPT_DIR}/lib/dracut-retry.sh"

/usr/libexec/kyth-plymouth-branding-guard /ctx/branding/transparent-watermark.svg

KVER="$(find_active_kver)"
test -n "${KVER}" ||
	{
		echo "ERROR: no kernel with vmlinuz found in /usr/lib/modules for branded initramfs rebuild" >&2
		exit 1
	}

mkdir -p /etc/plymouth /usr/share/plymouth
printf '%s\n' "${KYTH_PLYMOUTHD_CONF}" >/etc/plymouth/plymouthd.conf
install -m 0644 /etc/plymouth/plymouthd.conf /usr/share/plymouth/plymouthd.defaults

kyth_build_initramfs "/usr/lib/modules/${KVER}/initramfs" \
	--no-hostonly \
	--compress "zstd -3" \
	--kver "${KVER}" \
	--add kyth-plymouth

echo "=== POST-DRACUT: plymouthd.defaults from initramfs ===" >&2
(lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${KVER}/initramfs" 2>/dev/null || echo "MISSING") >&2

if command -v lsinitrd >/dev/null 2>&1; then
	initramfs="/usr/lib/modules/${KVER}/initramfs"
	initrd_listing="$(mktemp)"
	lsinitrd "${initramfs}" >"${initrd_listing}"

	# Each entry is "pattern|message"; message is appended to the standard
	# "ERROR: branded initramfs ..." prefix.
	listing_checks=(
		'usr/share/plymouth/themes/kyth/kyth.plymouth|does not contain KythOS Plymouth theme'
		'usr/share/plymouth/themes/kyth/kyth.script|does not contain KythOS Plymouth script'
		'usr/share/plymouth/themes/kyth/kyth-logo.png|does not contain KythOS Plymouth logo'
		'usr/share/plymouth/themes/default.plymouth|does not force the KythOS Plymouth default theme'
	)
	for entry in "${listing_checks[@]}"; do
		plymouth_require_pattern "${initrd_listing}" "${entry%%|*}" "branded initramfs ${entry#*|}"
	done

	plymouth_require_match \
		<(lsinitrd -f /usr/share/pixmaps/system-logo-white.png "${initramfs}") \
		/usr/share/kyth/branding/transparent-watermark.png \
		"branded initramfs still contains distro Plymouth system logo"

	for entry in "${KYTH_PLYMOUTH_DAEMON_CHECKS[@]}"; do
		plymouth_require_pattern \
			<(lsinitrd -f /usr/share/plymouth/plymouthd.defaults "${initramfs}") \
			"${entry%%|*}" "branded initramfs Plymouth defaults ${entry#*|}"
	done

	plymouth_require_pattern_ere "${initrd_listing}" 'usr/(lib64|lib)/plymouth/script\.so' \
		"branded initramfs does not contain plymouth/script.so — kyth script theme will silently fail and fall back to BGRT firmware logo"

	for account_file in etc/passwd etc/group; do
		plymouth_require_pattern_ere "${initrd_listing}" "(^|[[:space:]])${account_file}$" \
			"branded initramfs is missing /${account_file}; early udev/tmpfiles account lookup will fail"
	done

	plymouth_forbid_fallback_theme "${initrd_listing}" "Plymouth fallback theme leaked into branded initramfs"

	rm -f "${initrd_listing}"
fi
