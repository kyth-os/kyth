# shellcheck shell=bash
#
# Canonical Plymouth [Daemon] config, and the assertion patterns used to
# verify it landed in a built/repaired initramfs. Sourced by plymouth-setup.sh,
# plymouth-initramfs.sh, and repair-current-plymouth-initramfs.sh.
#
# Two copies of this same config live outside this file's reach and must be
# kept in sync by hand: plymouth-branding-guard.sh is installed standalone
# (/usr/libexec/kyth-plymouth-branding-guard, also inst_multiple'd into the
# initramfs) with no sibling lib/ directory, and bakes two further copies into
# a quoted dracut module heredoc where variables must stay literal for dracut
# to expand later — none of those can source this file. build_base/build.sh
# builds in the separate `build_base/` Docker context and has no access to
# build_files/scripts/ at all.
#
# shellcheck disable=SC2034  # consumed by the scripts that source this file

KYTH_PLYMOUTHD_CONF='[Daemon]
Theme=kyth
ShowDelay=0
DeviceTimeout=8
UseFirmwareBackground=false'

# Each entry is "pattern|message"; message is appended to the standard
# "ERROR: ... Plymouth defaults <message>" prefix by the caller.
KYTH_PLYMOUTH_DAEMON_CHECKS=(
	'^Theme=kyth$|do not force Theme=kyth'
	'^ShowDelay=0$|do not draw immediately'
	'^DeviceTimeout=8$|are missing DeviceTimeout=8'
	'^UseFirmwareBackground=false$|do not suppress BGRT firmware background'
)
