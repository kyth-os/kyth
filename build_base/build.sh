#!/bin/bash
set -euo pipefail

KYTH_KERNEL_FLAVOR="${KYTH_KERNEL_FLAVOR:-fedora}"

write_kernel_flavor() {
	mkdir -p /usr/share/kyth
	printf '%s\n' "${KYTH_KERNEL_FLAVOR}" >/usr/share/kyth/kernel-flavor
}

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

latest_kernel_version() {
	# Prefer module dirs that contain an actual kernel image — the upstream base
	# image can carry kernel-less debris dirs (kmods prebuilt for a kernel it
	# does not ship yet), so the highest-versioned dir is not necessarily it.
	local with_kernel
	with_kernel=$(
		for d in /usr/lib/modules/*/; do
			[ -s "${d}vmlinuz" ] && basename "${d}"
		done | sort -V | tail -n 1
	)
	if [[ -n "${with_kernel}" ]]; then
		printf '%s\n' "${with_kernel}"
		return
	fi
	find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -V | tail -n 1
}

remove_kernel_packages_except() {
	local keep_pattern=$1
	rpm -qa | grep -E '^kernel' | grep -Ev "${keep_pattern}" | xargs -r rpm --nodeps -e 2>/dev/null || true
}

install_cachyos_kernel() {
	dnf5 copr enable -y bieszczaders/kernel-cachyos
	dnf5 install -y --setopt=tsflags=noscripts kernel-cachyos-modules

	local kver
	kver=$(basename "$(echo /usr/lib/modules/*cachyos*)")

	dnf5 install -y --setopt=tsflags=noscripts --skip-unavailable \
		kernel-cachyos \
		kernel-cachyos-core

	# Matching kernel headers so akmods (akmod-nvidia, installed in the main
	# image layer) can build modules for this kernel at first boot.
	dnf5 install -y --skip-unavailable kernel-cachyos-devel-matched ||
		echo "WARNING: kernel-cachyos-devel-matched unavailable; first-boot akmod builds will fail." >&2

	depmod -a "${kver}"

	if ! find "/usr/lib/modules/${kver}" -name 'asus-armoury.ko*' -print -quit | grep -q .; then
		echo "WARNING: CachyOS kernel lacks asus-armoury.ko; ASUS Linux support will be reduced." >&2
	fi

	for kdir in /usr/lib/modules/*/; do
		local existing
		existing=$(basename "$kdir")
		if [[ "$existing" != *cachyos* ]]; then
			echo "Removing non-CachyOS kernel: ${existing}"
			rm -rf "$kdir"
		fi
	done
	remove_kernel_packages_except 'cachyos'

	if [ ! -f "/usr/lib/modules/${kver}/vmlinuz" ] && [ -f "/boot/vmlinuz-${kver}" ]; then
		cp --no-preserve=all "/boot/vmlinuz-${kver}" "/usr/lib/modules/${kver}/vmlinuz" 2>/dev/null || true
	fi

	dnf5 copr disable -y bieszczaders/kernel-cachyos
}

case "${KYTH_KERNEL_FLAVOR}" in
fedora)
	echo "Using Fedora kernel from upstream base image"
	;;
cachy | cachyos)
	KYTH_KERNEL_FLAVOR="cachy"
	install_cachyos_kernel
	;;
*)
	echo "Unknown KYTH_KERNEL_FLAVOR: ${KYTH_KERNEL_FLAVOR}" >&2
	echo "Valid values: fedora, cachy" >&2
	exit 1
	;;
esac
write_kernel_flavor

write_kyth_os_release /usr/lib/os-release
rm -f /etc/os-release
write_kyth_os_release /etc/os-release

KVER=$(latest_kernel_version)
if [[ -z "${KVER}" ]]; then
	echo "ERROR: no kernel found in /usr/lib/modules" >&2
	exit 1
fi

# ── Plymouth boot splash ──────────────────────────────────────────────────────
dnf5 install -y --exclude='kernel*' plymouth plymouth-plugin-script librsvg2-tools

PLYMOUTH_DIR=/usr/share/plymouth/themes/kyth
mkdir -p "${PLYMOUTH_DIR}"
cp /run/plymouth/kyth.plymouth "${PLYMOUTH_DIR}/kyth.plymouth"
cp /run/plymouth/kyth.script "${PLYMOUTH_DIR}/kyth.script"
rsvg-convert -w 200 /run/plymouth/kyth-logo.svg -o "${PLYMOUTH_DIR}/kyth-logo.png"
mkdir -p /usr/share/kyth/branding /usr/share/pixmaps
cat >/usr/share/kyth/branding/transparent-watermark.svg <<'SVEOF'
<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1" viewBox="0 0 1 1">
  <rect width="1" height="1" fill="none"/>
</svg>
SVEOF
printf '%s' 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=' |
	base64 -d >/usr/share/kyth/branding/transparent-watermark.png
install -m 0644 /usr/share/kyth/branding/transparent-watermark.png \
	/usr/share/pixmaps/system-logo-white.png
plymouth-set-default-theme kyth
rm -rf /usr/share/plymouth/themes/bgrt-fedora
rm -rf /usr/share/plymouth/themes/bgrt

dnf5 remove -y librsvg2-tools || true

# CachyOS rebuilds its initramfs in this base layer, before the main image layer
# installs the reusable KythOS Plymouth guard. Provide the same dracut module
# locally so dracut can resolve kyth-plymouth here too.
rm -rf /usr/lib/dracut/modules.d/46kyth-plymouth
KYTH_PLYMOUTH_DRACUT_DIR=/usr/lib/dracut/modules.d/99kyth-plymouth
mkdir -p "${KYTH_PLYMOUTH_DRACUT_DIR}"
cat >"${KYTH_PLYMOUTH_DRACUT_DIR}/module-setup.sh" <<'KYTHPLYMOUTHEOF'
#!/usr/bin/bash

check() {
    return 0
}

depends() {
    echo plymouth
    return 0
}

install() {
    mkdir -p \
        "${initdir}/etc/plymouth" \
        "${initdir}/usr/share/plymouth" \
        "${initdir}/usr/share/pixmaps" \
        "${initdir}/usr/share/plymouth/themes"
    cat > "${initdir}/etc/plymouth/plymouthd.conf" <<'PLYMOUTHCONF'
[Daemon]
Theme=kyth
ShowDelay=0
DeviceTimeout=8
UseFirmwareBackground=false
PLYMOUTHCONF
    cat > "${initdir}/usr/share/plymouth/plymouthd.defaults" <<'PLYMOUTHDEFAULTS'
[Daemon]
Theme=kyth
ShowDelay=0
DeviceTimeout=8
UseFirmwareBackground=false
PLYMOUTHDEFAULTS
    rm -rf \
        "${initdir}/usr/share/plymouth/themes/default.plymouth" \
        "${initdir}/usr/share/plymouth/themes/bgrt-fedora" \
        "${initdir}/usr/share/plymouth/themes/bgrt" \
        "${initdir}/usr/share/plymouth/themes/spinner"
    ln -sfn kyth/kyth.plymouth \
        "${initdir}/usr/share/plymouth/themes/default.plymouth"
    inst_libdir_file "plymouth/script.so"
    inst_multiple \
        /usr/share/plymouth/themes/kyth/kyth.plymouth \
        /usr/share/plymouth/themes/kyth/kyth.script \
        /usr/share/plymouth/themes/kyth/kyth-logo.png
    inst_multiple -o \
        /etc/os-release \
        /usr/lib/os-release \
        /usr/share/kyth/branding/transparent-watermark.svg \
        /usr/share/kyth/branding/transparent-watermark.png
    rm -f "${initdir}/usr/share/pixmaps/system-logo-white.png"
    inst_simple \
        /usr/share/kyth/branding/transparent-watermark.png \
        /usr/share/pixmaps/system-logo-white.png
    rm -rf \
        "${initdir}/usr/share/plymouth/themes/bgrt-fedora" \
        "${initdir}/usr/share/plymouth/themes/bgrt" \
        "${initdir}/usr/share/plymouth/themes/spinner"
}
KYTHPLYMOUTHEOF
chmod 0755 "${KYTH_PLYMOUTH_DRACUT_DIR}/module-setup.sh"
unset KYTH_PLYMOUTH_DRACUT_DIR

# Write dracut config — applies on next initramfs regeneration (bootc deploy,
# or dracut run in the cachy path below).
mkdir -p /etc/dracut.conf.d
cat >/etc/dracut.conf.d/99-kyth.conf <<'DRACUTEOF'
add_dracutmodules+=" ostree drm plymouth kyth-plymouth "
force_add_dracutmodules+=" kyth-plymouth "
add_drivers+=" virtio_blk virtio_scsi virtio_pci nvme ahci virtio_gpu qxl bochs overlay "
DRACUTEOF

# Write Plymouth defaults unconditionally so both Fedora and CachyOS images ship
# a host config that agrees with the late kyth-plymouth dracut module.
mkdir -p /etc/plymouth /usr/share/plymouth
cat >/etc/plymouth/plymouthd.conf <<'PLYMOUTHCONF'
[Daemon]
Theme=kyth
ShowDelay=0
DeviceTimeout=8
UseFirmwareBackground=false
PLYMOUTHCONF
install -m 0644 /etc/plymouth/plymouthd.conf /usr/share/plymouth/plymouthd.defaults

# For the CachyOS kernel we must rebuild the initramfs at image-build time
# because the kernel itself was just replaced.  For the stock Fedora kernel
# the upstream base image already ships a valid initramfs; bootc regenerates
# it on first deployment using the dracut.conf.d above.
if [[ "${KYTH_KERNEL_FLAVOR}" == "cachy" ]]; then
	mkdir -p /etc/plymouth /usr/share/plymouth
	cat >/etc/plymouth/plymouthd.conf <<'PLYMOUTHCONF'
[Daemon]
Theme=kyth
ShowDelay=0
DeviceTimeout=8
UseFirmwareBackground=false
PLYMOUTHCONF
	install -m 0644 /etc/plymouth/plymouthd.conf /usr/share/plymouth/plymouthd.defaults
	_kyth_plymouth_include_root="$(mktemp -d)"
	mkdir -p \
		"${_kyth_plymouth_include_root}/etc/plymouth" \
		"${_kyth_plymouth_include_root}/usr/share/plymouth" \
		"${_kyth_plymouth_include_root}/usr/share/pixmaps"
	install -m 0644 /etc/plymouth/plymouthd.conf \
		"${_kyth_plymouth_include_root}/etc/plymouth/plymouthd.conf"
	install -m 0644 /usr/share/plymouth/plymouthd.defaults \
		"${_kyth_plymouth_include_root}/usr/share/plymouth/plymouthd.defaults"
	install -m 0644 /usr/share/kyth/branding/transparent-watermark.png \
		"${_kyth_plymouth_include_root}/usr/share/pixmaps/system-logo-white.png"
	TMPDIR=/var/tmp dracut \
		--no-hostonly \
		--compress "zstd -1" \
		--kver "${KVER}" \
		--force \
		--add kyth-plymouth \
		--include "${_kyth_plymouth_include_root}" / \
		"/usr/lib/modules/${KVER}/initramfs" \
		2> >(grep -Ev 'xattr|fail to copy' >&2)
	rm -rf "${_kyth_plymouth_include_root}"
	if command -v lsinitrd >/dev/null 2>&1; then
		_initrd_listing="$(mktemp)"
		lsinitrd "/usr/lib/modules/${KVER}/initramfs" >"${_initrd_listing}"
		grep -q 'usr/share/plymouth/themes/kyth/kyth.plymouth' "${_initrd_listing}" || {
			echo "ERROR: CachyOS initramfs does not contain KythOS Plymouth theme" >&2
			exit 1
		}
		grep -q 'usr/share/plymouth/themes/kyth/kyth.script' "${_initrd_listing}" || {
			echo "ERROR: CachyOS initramfs does not contain KythOS Plymouth script" >&2
			exit 1
		}
		grep -q 'usr/share/plymouth/themes/kyth/kyth-logo.png' "${_initrd_listing}" || {
			echo "ERROR: CachyOS initramfs does not contain KythOS Plymouth logo" >&2
			exit 1
		}
		if ! lsinitrd -f /usr/share/pixmaps/system-logo-white.png "/usr/lib/modules/${KVER}/initramfs" | cmp -s - /usr/share/kyth/branding/transparent-watermark.png; then
			echo "ERROR: CachyOS initramfs still contains distro Plymouth system logo" >&2
			exit 1
		fi
		if ! lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${KVER}/initramfs" | grep -q '^Theme=kyth$'; then
			echo "ERROR: CachyOS initramfs Plymouth defaults do not force Theme=kyth" >&2
			echo "---- /usr/share/plymouth/plymouthd.defaults from initramfs ----" >&2
			lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${KVER}/initramfs" >&2 || true
			exit 1
		fi
		if ! lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${KVER}/initramfs" | grep -q '^ShowDelay=0$'; then
			echo "ERROR: CachyOS initramfs Plymouth defaults do not draw immediately" >&2
			echo "---- /usr/share/plymouth/plymouthd.defaults from initramfs ----" >&2
			lsinitrd -f /usr/share/plymouth/plymouthd.defaults "/usr/lib/modules/${KVER}/initramfs" >&2 || true
			exit 1
		fi
		if grep -Ei 'usr/share/plymouth/themes/(bgrt-fedora|bgrt|spinner)(/|$)' "${_initrd_listing}" >&2; then
			echo "ERROR: Plymouth fallback theme leaked into CachyOS initramfs" >&2
			exit 1
		fi
		rm -f "${_initrd_listing}"
	fi
fi

# ── Kernel args (bootc kargs.d) ───────────────────────────────────────────────
mkdir -p /usr/lib/bootc/kargs.d
cat >/usr/lib/bootc/kargs.d/99-kyth.toml <<'KARGSEOF'
kargs = ["quiet", "rhgb", "splash", "rd.plymouth=1", "plymouth.enable=1", "plymouth.ignore-serial-consoles", "systemd.show_status=false", "rd.systemd.show_status=false", "loglevel=3", "rd.udev.log_level=3", "vt.global_cursor_default=0", "threadirqs"]
KARGSEOF

# ── SDDM — ensure graphical target ───────────────────────────────────────────
systemctl enable sddm 2>/dev/null || true
systemctl set-default graphical.target 2>/dev/null || true
ln -sf /usr/lib/systemd/system/sddm.service \
	/etc/systemd/system/display-manager.service
mkdir -p /etc/systemd/system/graphical.target.wants
ln -sf /etc/systemd/system/display-manager.service \
	/etc/systemd/system/graphical.target.wants/display-manager.service
ln -sf /usr/lib/systemd/system/graphical.target \
	/etc/systemd/system/default.target

systemctl mask bootloader-update.service 2>/dev/null || true
systemctl mask systemd-remount-fs.service 2>/dev/null || true

rm -f /etc/systemd/system/plasmalogin.service
ln -s /dev/null /etc/systemd/system/plasmalogin.service
