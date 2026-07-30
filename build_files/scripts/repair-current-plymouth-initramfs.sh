#!/usr/bin/env bash
# Repair the currently deployed initramfs when an older image wrote an invalid
# Plymouth defaults file without DeviceTimeout.

set -euo pipefail

# shellcheck source=lib/plymouth-initrd-checks.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib/plymouth-initrd-checks.sh"
# shellcheck source=lib/plymouth-stock-themes.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib/plymouth-stock-themes.sh"
# shellcheck source=lib/plymouth-config.sh disable=SC1091
source "$(dirname "${BASH_SOURCE[0]}")/lib/plymouth-config.sh"

if [[ "${EUID}" -ne 0 ]]; then
	printf 'ERROR: run as root, for example: run0 --pty /usr/bin/bash %q\n' "$0" >&2
	exit 1
fi

if [[ -x /usr/libexec/kyth-plymouth-branding-guard ]]; then
	/usr/libexec/kyth-plymouth-branding-guard || true
fi

kernel="${1:-$(uname -r)}"
include_root="$(mktemp -d /tmp/kyth-plymouth-repair.XXXXXX)"
boot_was_ro=0

cleanup() {
	rm -rf "${include_root}"
	if [[ "${boot_was_ro}" -eq 1 ]]; then
		mount -o remount,ro /boot || true
	fi
}
trap cleanup EXIT

if findmnt -no OPTIONS /boot 2>/dev/null | tr ',' '\n' | grep -qx ro; then
	mount -o remount,rw /boot
	boot_was_ro=1
fi

mkdir -p \
	"${include_root}/etc/plymouth" \
	"${include_root}/usr/share/plymouth" \
	"${include_root}/usr/share/pixmaps" \
	"${include_root}/usr/share/plymouth/themes"

printf '%s\n' "${KYTH_PLYMOUTHD_CONF}" \
	>"${include_root}/etc/plymouth/plymouthd.conf"
install -m 0644 \
	"${include_root}/etc/plymouth/plymouthd.conf" \
	"${include_root}/usr/share/plymouth/plymouthd.defaults"
if [[ -r /usr/share/kyth/branding/transparent-watermark.png ]]; then
	install -m 0644 /usr/share/kyth/branding/transparent-watermark.png \
		"${include_root}/usr/share/pixmaps/system-logo-white.png"
else
	printf '%s' 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=' |
		base64 -d >"${include_root}/usr/share/pixmaps/system-logo-white.png"
fi

cp -a /usr/share/plymouth/themes/kyth "${include_root}/usr/share/plymouth/themes/kyth"
ln -sfn kyth/kyth.plymouth "${include_root}/usr/share/plymouth/themes/default.plymouth"
for theme_name in "${KYTH_STOCK_PLYMOUTH_THEMES[@]}"; do
	rm -rf "${include_root}/usr/share/plymouth/themes/${theme_name}"
done

plugin_dir="$(plymouth --get-splash-plugin-path)"
if [[ -r "${plugin_dir}/script.so" ]]; then
	mkdir -p "${include_root}${plugin_dir}"
	cp -a "${plugin_dir}/script.so" "${include_root}${plugin_dir}/script.so"
fi

images=()
if [[ -d /boot/ostree ]]; then
	while IFS= read -r -d '' image; do
		images+=("${image}")
	done < <(find /boot/ostree -path "*/initramfs-${kernel}.img" -type f -print0)
fi
if [[ -e "/boot/initramfs-${kernel}.img" ]]; then
	images+=("/boot/initramfs-${kernel}.img")
fi

if [[ "${#images[@]}" -eq 0 ]]; then
	echo "ERROR: no deployed initramfs found for ${kernel}" >&2
	exit 1
fi

for image in "${images[@]}"; do
	backup="${image}.pre-device-timeout-fix"
	if [[ ! -e "${backup}" ]]; then
		cp -a "${image}" "${backup}"
	fi

	# --nohardlink: dracut's hardlink-dedup pass can SIGSEGV inside
	# containerized build environments due to a util-linux/kernel AF_ALG
	# interaction (util-linux/util-linux#4334) — harmless to skip everywhere.
	TMPDIR=/var/tmp dracut \
		--tmpdir /var/tmp \
		--no-hostonly \
		--compress "zstd -1" \
		--kver "${kernel}" \
		--force \
		--nohardlink \
		--add "drm plymouth ostree kyth-plymouth" \
		--include "${include_root}/etc/plymouth" /etc/plymouth \
		--include "${include_root}/usr/share/plymouth" /usr/share/plymouth \
		--include "${include_root}/usr/share/pixmaps/system-logo-white.png" /usr/share/pixmaps/system-logo-white.png \
		"${image}"

	defaults="$(mktemp /tmp/kyth-plymouth-defaults.XXXXXX)"
	listing="$(mktemp /tmp/kyth-plymouth-listing.XXXXXX)"
	logo="$(mktemp /tmp/kyth-plymouth-logo.XXXXXX)"
	lsinitrd -f /usr/share/plymouth/plymouthd.defaults "${image}" >"${defaults}"
	lsinitrd -f /usr/share/pixmaps/system-logo-white.png "${image}" >"${logo}"
	lsinitrd "${image}" >"${listing}"

	listing_checks=(
		'usr/share/plymouth/themes/kyth/kyth.plymouth|does not contain KythOS Plymouth theme'
		'usr/share/plymouth/themes/kyth/kyth.script|does not contain KythOS Plymouth script'
		'usr/share/plymouth/themes/kyth/kyth-logo.png|does not contain KythOS Plymouth logo'
	)
	for entry in "${listing_checks[@]}"; do
		plymouth_require_pattern "${listing}" "${entry%%|*}" "repaired initramfs ${entry#*|}"
	done

	plymouth_require_match "${logo}" "${include_root}/usr/share/pixmaps/system-logo-white.png" \
		"repaired initramfs still contains distro Plymouth system logo"

	for entry in "${KYTH_PLYMOUTH_DAEMON_CHECKS[@]}"; do
		plymouth_require_pattern "${defaults}" "${entry%%|*}" "repaired initramfs Plymouth defaults ${entry#*|}"
	done

	plymouth_require_pattern_ere "${listing}" 'usr/(lib64|lib)/plymouth/script\.so' \
		"repaired initramfs does not contain plymouth/script.so — kyth theme will silently fail and fall back to BGRT firmware logo"

	plymouth_forbid_fallback_theme "${listing}" "Plymouth fallback theme leaked into repaired initramfs"

	rm -f "${defaults}" "${listing}" "${logo}"

	echo "Repaired ${image}"
	echo "Backup: ${backup}"
done
