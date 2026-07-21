# shellcheck shell=bash
#
# COPRs enabled for the gaming stack (packages/06-gaming-core.sh) and
# disabled again once packages are installed (packages/12-vram-latency-and-copr-disable.sh).
# Kept here, not re-listed at each call site, so the enable-time and
# disable-time lists can't drift out of sync with each other — a COPR added
# to one list but not the other would either fail to provide packages it's
# needed for, or stay enabled as an active repo source in the shipped image.
KYTH_GAMING_COPRS=(
	ublue-os/bazzite
	ublue-os/bazzite-multilib
	ublue-os/staging
	ublue-os/packages
	ublue-os/obs-vkcapture
	lukenukem/asus-linux
	ycollet/audinux
)
