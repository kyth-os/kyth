#!/usr/bin/env bash
# Remove distro artwork from Plymouth fallback themes. This is intentionally
# runnable more than once because package upgrades can restore upstream assets.

set -euo pipefail

# Asset repair remains here; host defaults and dracut configuration are owned
# exclusively by /usr/libexec/kyth-plymouth-configure.
KYTH_STOCK_PLYMOUTH_THEMES=(bgrt-fedora bgrt spinner)

source_svg="${1:-}"
asset_dir=/usr/share/kyth/branding
transparent_svg="${asset_dir}/transparent-watermark.svg"
transparent_png="${asset_dir}/transparent-watermark.png"
pixmaps_dir=/usr/share/pixmaps

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

configure=${KYTH_PLYMOUTH_CONFIGURE:-/usr/libexec/kyth-plymouth-configure}
if [[ ! -x "${configure}" ]]; then
	printf 'ERROR: missing canonical Plymouth configuration owner: %s\n' "${configure}" >&2
	exit 1
fi
"${configure}"

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
