#!/bin/bash
# Ensure the active kernel has a vmlinuz + initramfs under /usr/lib/modules
# after dnf5 upgrade, which bootc needs to build a deployable commit. Prunes
# kernel-less module dirs and repairs a missing vmlinuz/initramfs by pulling
# from /boot or /usr/lib/kernel, or rebuilding via dracut as a last resort.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=lib/find-kver.sh disable=SC1091
source "${SCRIPT_DIR}/lib/find-kver.sh"
# shellcheck source=lib/dracut-retry.sh disable=SC1091
source "${SCRIPT_DIR}/lib/dracut-retry.sh"

KVER="$(find_active_kver)"
if [ -z "${KVER}" ]; then
	# Prefer the newest module dir that actually ships a vmlinuz; only fall
	# back to the newest dir overall so the missing-vmlinuz repair below
	# still has a candidate to staple a vmlinuz onto.
	KVER="$(for d in /usr/lib/modules/*/; do [ -s "${d}vmlinuz" ] && basename "${d}"; done | sort -V | tail -n 1)"
fi
if [ -z "${KVER}" ]; then
	KVER="$(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -V | tail -n 1)"
fi
test -n "${KVER}" ||
	{
		echo "ERROR: no kernel found in /usr/lib/modules after upgrade; contents: $(ls /usr/lib/modules/ 2>&1)" >&2
		exit 1
	}
echo "==> kernel: ${KVER}"

for kdir in /usr/lib/modules/*/; do
	kbase="$(basename "${kdir}")"
	if [ "${kbase}" != "${KVER}" ] && [ ! -s "${kdir}vmlinuz" ]; then
		echo "  Pruning kernel-less module dir: ${kbase}"
		rm -rf "${kdir}"
	fi
done

if [ ! -s "/usr/lib/modules/${KVER}/vmlinuz" ]; then
	src=$(find /boot -name "vmlinuz-${KVER}" 2>/dev/null | head -1)
	if [ -n "${src}" ] && [ -s "${src}" ]; then
		echo "  Found vmlinuz at ${src}, copying..."
		cp --no-preserve=all "${src}" "/usr/lib/modules/${KVER}/vmlinuz"
	else
		echo "  vmlinuz not found in /boot, checking /usr/lib/kernel..."
		src=$(find /usr/lib/kernel -name "vmlinuz-${KVER}" 2>/dev/null | head -1)
		if [ -n "${src}" ] && [ -s "${src}" ]; then
			echo "  Found vmlinuz at ${src}, copying..."
			cp --no-preserve=all "${src}" "/usr/lib/modules/${KVER}/vmlinuz"
		fi
	fi
fi

depmod_output="$(depmod -a "${KVER}" 2>&1)" || {
	echo "ERROR: depmod -a ${KVER} failed:" >&2
	echo "${depmod_output}" >&2
	exit 1
}

# Dracut modules for the rebuilt initramfs. Keep in sync with the --add
# lists in build_files/scripts/plymouth-initramfs.sh and
# build_files/scripts/repair-current-plymouth-initramfs.sh.
KYTH_DRACUT_MODULES="drm plymouth ostree kyth-plymouth"

if [ ! -s "/usr/lib/modules/${KVER}/initramfs" ]; then
	if [ -s "/boot/initramfs-${KVER}.img" ]; then
		cp --no-preserve=all "/boot/initramfs-${KVER}.img" "/usr/lib/modules/${KVER}/initramfs"
	else
		kyth_build_initramfs "/usr/lib/modules/${KVER}/initramfs" \
			--no-hostonly \
			--compress "zstd -3" \
			--kver "${KVER}" \
			--add "${KYTH_DRACUT_MODULES}"
	fi
fi

if [ ! -s "/usr/lib/modules/${KVER}/vmlinuz" ]; then
	echo "ERROR: vmlinuz missing/empty for ${KVER}"
	echo "  Available files in /boot:"
	ls -la /boot/vmlinuz* 2>/dev/null || echo "    (none)"
	echo "  Contents of /usr/lib/modules/${KVER}:"
	# shellcheck disable=SC2012  # human-readable diagnostic output, not parsed
	ls -la "/usr/lib/modules/${KVER}/" 2>&1 | head -20
	exit 1
fi

test -s "/usr/lib/modules/${KVER}/initramfs" ||
	{
		echo "ERROR: initramfs missing/empty for ${KVER}" >&2
		exit 1
	}

echo "==> kernel OK: vmlinuz $(du -h "/usr/lib/modules/${KVER}/vmlinuz" | cut -f1), initramfs $(du -h "/usr/lib/modules/${KVER}/initramfs" | cut -f1)"
