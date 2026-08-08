# shellcheck shell=bash
#
# Assertion patterns for built/repaired initramfs images. The daemon config
# itself is emitted by the canonical kyth-plymouth-configure owner.
#
# shellcheck disable=SC2034  # consumed by the scripts that source this file

_plymouth_config_owner=${KYTH_PLYMOUTH_CONFIGURE:-/usr/libexec/kyth-plymouth-configure}
if [[ ! -x "${_plymouth_config_owner}" ]]; then
	_repo_owner="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)/build_base/plymouth/kyth-plymouth-configure"
	_plymouth_config_owner=${_repo_owner}
fi
KYTH_PLYMOUTHD_CONF="$("${_plymouth_config_owner}" --print-daemon-config)"
unset _plymouth_config_owner _repo_owner

# Each entry is "pattern|message"; message is appended to the standard
# "ERROR: ... Plymouth defaults <message>" prefix by the caller.
KYTH_PLYMOUTH_DAEMON_CHECKS=(
	'^Theme=kyth$|do not force Theme=kyth'
	'^ShowDelay=0$|do not draw immediately'
	'^DeviceTimeout=8$|are missing DeviceTimeout=8'
	'^UseFirmwareBackground=false$|do not suppress BGRT firmware background'
)
