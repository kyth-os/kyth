#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Platform and wireless firmware ───────────────────────────────────────────
# Fedora has been splitting linux-firmware into smaller subpackages. Keep the
# hardware-critical families explicit so workstation laptops do not depend on
# whichever subset the base image happened to include:
#   - iwlwifi-mvm: Intel Wi-Fi 4/5/6/6E families common in EliteBook systems
#   - iwlwifi-mld: newer Intel Wi-Fi 7 / BE-series devices
#   - iwlwifi-dvm + iwlegacy: older Intel adapters still seen in business fleets
#   - realtek/mediatek/atheros/brcmfmac: common USB/PCIe/Bluetooth companion HW
#   - cirrus/sof/intel-vsc: HP laptop audio, DSP, camera, and sensor firmware
dnf5 install -y --skip-unavailable \
	iwlwifi-mvm-firmware \
	iwlwifi-mld-firmware \
	iwlwifi-dvm-firmware \
	iwlegacy-firmware \
	intel-vsc-firmware \
	alsa-sof-firmware \
	realtek-firmware \
	mediatek-firmware \
	atheros-firmware \
	brcmfmac-firmware \
	cirrus-audio-firmware || true

iwlwifi_firmware_probe="$(
	find /usr/lib/firmware \
		\( -name 'iwlwifi-*.ucode*' -o -name 'iwlwifi-*.pnvm*' \) \
		-print -quit
)"
if [[ -z "${iwlwifi_firmware_probe}" ]]; then
	echo "ERROR: Intel iwlwifi firmware blobs are missing from the image." >&2
	exit 1
fi
echo "Intel iwlwifi firmware present: ${iwlwifi_firmware_probe}"
