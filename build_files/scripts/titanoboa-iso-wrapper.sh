#!/usr/bin/env bash
# Titanoboa reads iso.yaml from the live-payload image mount at
# /rootfs/usr/lib/bootc-image-builder/iso.yaml. bootc/ostree images keep
# /usr under ostree (excluded by mksquashfs -e ostree), so that path is
# often missing on a type=image mount even when installer/build.sh copied
# the file. Fall back to the checkout copy bind-mounted at /kyth/iso.yaml.
set -euxo pipefail

TITANOBOA_ISO="${TITANOBOA_ISO:-/src/titanoboa-build_iso.sh}"
KYTH_ISO="${KYTH_ISO:-/kyth/iso.yaml}"
ROOTFS_ISO=/rootfs/usr/lib/bootc-image-builder/iso.yaml

if [[ ! -f "${ROOTFS_ISO}" ]]; then
	if [[ ! -f "${KYTH_ISO}" ]]; then
		echo "ERROR: Missing iso.yaml (not in live payload /usr and no /kyth/iso.yaml fallback)" >&2
		exit 1
	fi
	if mkdir -p "$(dirname "${ROOTFS_ISO}")" && cp "${KYTH_ISO}" "${ROOTFS_ISO}"; then
		:
	else
		patched=/tmp/kyth-titanoboa-build_iso.sh
		sed "s|iso_config_file=/rootfs/usr/lib/bootc-image-builder/iso.yaml|iso_config_file=${KYTH_ISO}|" \
			"${TITANOBOA_ISO}" >"${patched}"
		chmod +x "${patched}"
		exec "${patched}"
	fi
fi
exec "${TITANOBOA_ISO}"
