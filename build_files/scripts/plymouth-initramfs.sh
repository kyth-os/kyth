#!/bin/bash
# Rebuild the boot splash initramfs after final branding lands, then assert
# the branded Plymouth theme (and none of the distro fallback themes) made
# it in. Run after scripts/branding.sh in the same image layer.
set -euo pipefail

# shellcheck source=lib/find-kver.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib/find-kver.sh"

/usr/libexec/kyth-plymouth-branding-guard /ctx/branding/transparent-watermark.svg

KVER="$(find_active_kver)"
test -n "${KVER}" ||
	{
		echo "ERROR: no kernel with vmlinuz found in /usr/lib/modules for branded initramfs rebuild" >&2
		exit 1
	}

mkdir -p /etc/plymouth /usr/share/plymouth
printf '[Daemon]\nTheme=kyth\nShowDelay=0\nDeviceTimeout=8\nUseFirmwareBackground=false\n' >/etc/plymouth/plymouthd.conf
install -m 0644 /etc/plymouth/plymouthd.conf /usr/share/plymouth/plymouthd.defaults

TMPDIR=/var/tmp dracut \
	--no-hostonly \
	--compress "zstd -3" \
	--kver "${KVER}" \
	--force \
	--add kyth-plymouth \
	"/usr/lib/modules/${KVER}/initramfs" \
	2> >(grep -Ev 'xattr|fail to copy' >&2)

echo "=== POST-DRACUT: plymouthd.defaults from initramfs ===" >&2
(lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${KVER}/initramfs" 2>/dev/null || echo "MISSING") >&2

if command -v lsinitrd >/dev/null 2>&1; then
	initrd_listing="$(mktemp)"
	lsinitrd "/usr/lib/modules/${KVER}/initramfs" >"${initrd_listing}"

	grep -q 'usr/share/plymouth/themes/kyth/kyth.plymouth' "${initrd_listing}" ||
		{
			echo "ERROR: branded initramfs does not contain KythOS Plymouth theme" >&2
			exit 1
		}
	grep -q 'usr/share/plymouth/themes/kyth/kyth.script' "${initrd_listing}" ||
		{
			echo "ERROR: branded initramfs does not contain KythOS Plymouth script" >&2
			exit 1
		}
	grep -q 'usr/share/plymouth/themes/kyth/kyth-logo.png' "${initrd_listing}" ||
		{
			echo "ERROR: branded initramfs does not contain KythOS Plymouth logo" >&2
			exit 1
		}
	lsinitrd -f /usr/share/pixmaps/system-logo-white.png "/usr/lib/modules/${KVER}/initramfs" | cmp -s - /usr/share/kyth/branding/transparent-watermark.png ||
		{
			echo "ERROR: branded initramfs still contains distro Plymouth system logo" >&2
			exit 1
		}
	grep -q 'usr/share/plymouth/themes/default.plymouth' "${initrd_listing}" ||
		{
			echo "ERROR: branded initramfs does not force the KythOS Plymouth default theme" >&2
			exit 1
		}
	lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${KVER}/initramfs" | grep -q '^Theme=kyth$' ||
		{
			echo "ERROR: branded initramfs Plymouth defaults do not force Theme=kyth" >&2
			exit 1
		}
	lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${KVER}/initramfs" | grep -q '^ShowDelay=0$' ||
		{
			echo "ERROR: branded initramfs Plymouth defaults do not draw immediately" >&2
			exit 1
		}
	lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${KVER}/initramfs" | grep -q '^DeviceTimeout=8$' ||
		{
			echo "ERROR: branded initramfs Plymouth defaults are missing DeviceTimeout=8" >&2
			exit 1
		}
	lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${KVER}/initramfs" | grep -q '^UseFirmwareBackground=false$' ||
		{
			echo "ERROR: branded initramfs Plymouth defaults do not suppress BGRT firmware background" >&2
			exit 1
		}
	grep -Eq 'usr/(lib64|lib)/plymouth/script\.so' "${initrd_listing}" ||
		{
			echo "ERROR: branded initramfs does not contain plymouth/script.so — kyth script theme will silently fail and fall back to BGRT firmware logo" >&2
			exit 1
		}
	if grep -Ei 'usr/share/plymouth/themes/(bgrt-fedora|bgrt|spinner)(/|$)' "${initrd_listing}" >&2; then
		echo "ERROR: Plymouth fallback theme leaked into branded initramfs" >&2
		exit 1
	fi

	rm -f "${initrd_listing}"
fi
