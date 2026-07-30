#!/usr/bin/env bash
# Remove distro artwork from Plymouth fallback themes. This is intentionally
# runnable more than once because package upgrades can restore upstream assets.

set -euo pipefail

# This script is installed standalone (/usr/libexec/kyth-plymouth-branding-guard,
# also inst_multiple'd into the initramfs) with no sibling lib/ directory, so it
# can't source build_files/scripts/lib/plymouth-stock-themes.sh like other
# plymouth scripts do — keep this list in sync with that file by hand.
KYTH_STOCK_PLYMOUTH_THEMES=(bgrt-fedora bgrt spinner)

source_svg="${1:-}"
asset_dir=/usr/share/kyth/branding
transparent_svg="${asset_dir}/transparent-watermark.svg"
transparent_png="${asset_dir}/transparent-watermark.png"
pixmaps_dir=/usr/share/pixmaps
# Keep in sync with KYTH_PLYMOUTHD_CONF in lib/plymouth-config.sh (this
# script can't source it — see the no-sibling-lib/ note above).
plymouth_conf='[Daemon]
Theme=kyth
ShowDelay=0
DeviceTimeout=8
UseFirmwareBackground=false'

mkdir -p "${asset_dir}"
if [[ -n "${source_svg}" && -r "${source_svg}" ]]; then
	install -m 0644 "${source_svg}" "${transparent_svg}"
elif [[ ! -r "${transparent_svg}" ]]; then
	cat >"${transparent_svg}" <<'SVEOF'
<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1" viewBox="0 0 1 1">
  <rect width="1" height="1" fill="none"/>
</svg>
SVEOF
fi

if command -v rsvg-convert >/dev/null 2>&1; then
	rsvg-convert "${transparent_svg}" -o "${transparent_png}"
elif [[ ! -r "${transparent_png}" ]]; then
	printf '%s' 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNgYAAAAAMAASsJTYQAAAAASUVORK5CYII=' |
		base64 -d >"${transparent_png}"
fi

mkdir -p "${pixmaps_dir}"
install -m 0644 "${transparent_png}" "${pixmaps_dir}/system-logo-white.png"

for theme_name in "${KYTH_STOCK_PLYMOUTH_THEMES[@]}"; do
	theme_dir="/usr/share/plymouth/themes/${theme_name}"
	[[ -d "${theme_dir}" ]] || continue

	for asset in watermark.png watermark@2x.png logo.png; do
		install -m 0644 "${transparent_png}" "${theme_dir}/${asset}"
	done
	for asset in watermark.svg logo.svg; do
		install -m 0644 "${transparent_svg}" "${theme_dir}/${asset}"
	done

	for branded_asset in "${theme_dir}"/*fedora* "${theme_dir}"/*Fedora* "${theme_dir}"/*FEDORA*; do
		[[ -e "${branded_asset}" ]] || continue
		case "${branded_asset}" in
		*.svg | *.svgz)
			install -m 0644 "${transparent_svg}" "${branded_asset}"
			;;
		*.png)
			install -m 0644 "${transparent_png}" "${branded_asset}"
			;;
		*)
			rm -f "${branded_asset}"
			;;
		esac
	done
done

install_kyth_plymouth_dracut_module() {
	rm -rf /usr/lib/dracut/modules.d/46kyth-plymouth

	local kyth_plymouth_dracut_dir=/usr/lib/dracut/modules.d/99kyth-plymouth
	mkdir -p "${kyth_plymouth_dracut_dir}"
	cat >"${kyth_plymouth_dracut_dir}/module-setup.sh" <<'KYTHPLYMOUTHEOF'
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
    install -m 0644 "${initdir}/etc/plymouth/plymouthd.conf" \
        "${initdir}/usr/share/plymouth/plymouthd.defaults"
    # Keep in sync with KYTH_STOCK_PLYMOUTH_THEMES in
    # build_files/scripts/lib/plymouth-stock-themes.sh — this heredoc is
    # quoted so ${initdir} stays literal for dracut, and can't source it.
    rm -rf \
        "${initdir}/usr/share/plymouth/themes/default.plymouth" \
        "${initdir}/usr/share/plymouth/themes/bgrt-fedora" \
        "${initdir}/usr/share/plymouth/themes/bgrt" \
        "${initdir}/usr/share/plymouth/themes/spinner"
    ln -sfn kyth/kyth.plymouth \
        "${initdir}/usr/share/plymouth/themes/default.plymouth"
    inst_libdir_file "plymouth/script.so"
    inst_multiple \
        /usr/libexec/kyth-plymouth-branding-guard \
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
    # Keep in sync with KYTH_STOCK_PLYMOUTH_THEMES (see comment above).
    rm -rf \
        "${initdir}/usr/share/plymouth/themes/bgrt-fedora" \
        "${initdir}/usr/share/plymouth/themes/bgrt" \
        "${initdir}/usr/share/plymouth/themes/spinner"
}
KYTHPLYMOUTHEOF
	chmod 0755 "${kyth_plymouth_dracut_dir}/module-setup.sh"
}

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

# Remove both Fedora-branded and plain bgrt themes from the system filesystem.
# The bgrt theme can render the firmware BGRT image, which may still be Fedora
# artwork from the inherited boot path. Removing it leaves only KythOS or text.
# spinner is deliberately left installed on the host — only stripped from the
# initramfs above — so skip it here.
for theme_name in "${KYTH_STOCK_PLYMOUTH_THEMES[@]}"; do
	[[ "${theme_name}" == spinner ]] && continue
	rm -rf "/usr/share/plymouth/themes/${theme_name}"
done
plymouth-set-default-theme kyth

# Keep host-side Plymouth config explicit too. Fedora's dracut Plymouth module
# reads these files before our late kyth-plymouth module reinforces the initramfs.
mkdir -p /etc/plymouth /usr/share/plymouth
printf '%s\n' "${plymouth_conf}" >/etc/plymouth/plymouthd.conf
install -m 0644 /etc/plymouth/plymouthd.conf /usr/share/plymouth/plymouthd.defaults

install_kyth_plymouth_dracut_module
