#!/usr/bin/env bash
# Boot a KythOS ISO through an unattended install and optional update/rollback.

set -euo pipefail

usage() {
	cat <<'EOF'
Usage: vm-acceptance.sh --iso PATH [--update-ref IMAGE] [--artifacts DIR]
                        [--timeout-minutes N]

Without --update-ref, validates live boot, bundled-image installation, and the
first installed boot. With --update-ref, also stages that image, boots it,
stages rollback, and verifies the original digest after the rollback boot.
EOF
}

ISO=
UPDATE_REF=
ARTIFACTS=
TIMEOUT_MINUTES=75
while (($#)); do
	case "$1" in
	--iso)
		ISO="${2:?}"
		shift 2
		;;
	--update-ref)
		UPDATE_REF="${2:?}"
		shift 2
		;;
	--artifacts)
		ARTIFACTS="${2:?}"
		shift 2
		;;
	--timeout-minutes)
		TIMEOUT_MINUTES="${2:?}"
		shift 2
		;;
	--help | -h)
		usage
		exit 0
		;;
	*)
		echo "Unknown argument: $1" >&2
		usage >&2
		exit 64
		;;
	esac
done

[[ -n "${ISO}" && -r "${ISO}" ]] || {
	echo "Readable --iso is required" >&2
	exit 64
}
[[ "${TIMEOUT_MINUTES}" =~ ^[1-9][0-9]*$ ]] || {
	echo "Invalid timeout" >&2
	exit 64
}
for command in qemu-img qemu-system-x86_64 timeout; do
	command -v "${command}" >/dev/null || {
		echo "Missing command: ${command}" >&2
		exit 69
	}
done

if [[ -z "${ARTIFACTS}" ]]; then
	ARTIFACTS="$(mktemp -d /tmp/kyth-vm-acceptance.XXXXXXXX)"
else
	mkdir -p "${ARTIFACTS}"
fi
ARTIFACTS="$(realpath "${ARTIFACTS}")"
ISO="$(realpath "${ISO}")"
DISK="${ARTIFACTS}/installed.qcow2"
SERIAL_LOG="${ARTIFACTS}/serial.log"
QEMU_LOG="${ARTIFACTS}/qemu.log"
MONITOR="${ARTIFACTS}/monitor.sock"
rm -f "${DISK}" "${SERIAL_LOG}" "${QEMU_LOG}" "${MONITOR}"
qemu-img create -q -f qcow2 -o lazy_refcounts=on "${DISK}" 64G

OVMF_ARGS=()
for code in /usr/share/OVMF/OVMF_CODE_4M.fd /usr/share/edk2/ovmf/OVMF_CODE.fd /usr/share/OVMF/OVMF_CODE.fd; do
	[[ -r "${code}" ]] || continue
	vars_template="${code/CODE/VARS}"
	if [[ -r "${vars_template}" ]]; then
		cp "${vars_template}" "${ARTIFACTS}/OVMF_VARS.fd"
		OVMF_ARGS=(
			-drive "if=pflash,format=raw,unit=0,readonly=on,file=${code}"
			-drive "if=pflash,format=raw,unit=1,file=${ARTIFACTS}/OVMF_VARS.fd"
		)
		break
	fi
done

# shellcheck disable=SC2054  # commas below are qemu's own option syntax, not array separators
QEMU_ARGS=(
	-machine q35
	-smp 4
	-m 8192
	-nodefaults
	-no-user-config
	-device virtio-vga
	-display none
	-device virtio-rng-pci
	-device ich9-ahci,id=ahci
	-drive "if=none,id=liveiso,format=raw,media=cdrom,readonly=on,file=${ISO}"
	-device ide-cd,bus=ahci.0,drive=liveiso,bootindex=1
	-drive "if=none,id=systemdisk,file=${DISK},format=qcow2,cache=writeback"
	-device virtio-blk-pci,drive=systemdisk,serial=KYTH_ACCEPT,bootindex=2
	-netdev user,id=net0
	-device virtio-net-pci,netdev=net0
	-serial "file:${SERIAL_LOG}"
	-D "${QEMU_LOG}"
	-monitor "unix:${MONITOR},server=on,wait=off"
	-fw_cfg name=opt/com.kyth/acceptance,string=1
	-boot once=d,menu=off
	"${OVMF_ARGS[@]}"
)
if [[ -r /dev/kvm && -w /dev/kvm ]]; then
	QEMU_ARGS+=(-enable-kvm -cpu host)
else
	echo "Warning: /dev/kvm is unavailable; using slower TCG emulation" >&2
	QEMU_ARGS+=(-accel tcg -cpu max)
fi
if [[ -n "${UPDATE_REF}" ]]; then
	[[ "${UPDATE_REF}" =~ ^[A-Za-z0-9._/@:+-]+$ ]] || {
		echo "Unsafe update ref" >&2
		exit 64
	}
	QEMU_ARGS+=(-fw_cfg "name=opt/com.kyth/update-ref,string=${UPDATE_REF}")
fi

echo "Acceptance artifacts: ${ARTIFACTS}"
set +e
timeout --signal=TERM --kill-after=30s "${TIMEOUT_MINUTES}m" \
	qemu-system-x86_64 "${QEMU_ARGS[@]}" &
QEMU_WRAPPER_PID=$!
set -e

capture_phase() {
	local phase="$1"
	local output="$2"
	[[ -S "${MONITOR}" ]] || return 0
	printf 'screendump %s\n' "${output}" |
		socat - "UNIX-CONNECT:${MONITOR}" >/dev/null 2>&1 || true
}

captured_live=0
captured_installed=0
while kill -0 "${QEMU_WRAPPER_PID}" 2>/dev/null; do
	if command -v socat >/dev/null && [[ -r "${SERIAL_LOG}" ]]; then
		if ((captured_live == 0)) && grep -q '^KYTH_ACCEPTANCE:LIVE_READY:' "${SERIAL_LOG}"; then
			capture_phase LIVE_READY "${ARTIFACTS}/live-desktop.ppm"
			captured_live=1
		fi
		if ((captured_installed == 0)) && grep -q '^KYTH_ACCEPTANCE:INSTALLED_READY:' "${SERIAL_LOG}"; then
			capture_phase INSTALLED_READY "${ARTIFACTS}/installed-login.ppm"
			captured_installed=1
		fi
	fi
	sleep 2
done
set +e
wait "${QEMU_WRAPPER_PID}"
QEMU_STATUS=$?
set -e

cat "${SERIAL_LOG}" || true
if ((QEMU_STATUS == 124 || QEMU_STATUS == 137)); then
	echo "VM acceptance timed out after ${TIMEOUT_MINUTES} minutes" >&2
	exit 1
fi
grep -q '^KYTH_ACCEPTANCE:LIVE_READY:' "${SERIAL_LOG}" ||
	{
		echo "Live desktop readiness sentinel missing" >&2
		exit 1
	}
grep -q '^KYTH_ACCEPTANCE:INSTALL_COMPLETE:' "${SERIAL_LOG}" ||
	{
		echo "Install completion sentinel missing" >&2
		exit 1
	}
grep -q '^KYTH_ACCEPTANCE:INSTALLED_READY:' "${SERIAL_LOG}" ||
	{
		echo "Installed boot readiness sentinel missing" >&2
		exit 1
	}
grep -q '^KYTH_ACCEPTANCE:COMPLETE:' "${SERIAL_LOG}" ||
	{
		echo "Acceptance completion sentinel missing" >&2
		exit 1
	}
if [[ -n "${UPDATE_REF}" ]]; then
	for phase in UPDATE_STAGED UPDATE_BOOTED ROLLBACK_STAGED ROLLBACK_BOOTED; do
		grep -q "^KYTH_ACCEPTANCE:${phase}:" "${SERIAL_LOG}" ||
			{
				echo "${phase} sentinel missing" >&2
				exit 1
			}
	done
fi
if grep -q '^KYTH_ACCEPTANCE:FAILED:' "${SERIAL_LOG}"; then
	echo "Guest reported an acceptance failure" >&2
	exit 1
fi
((QEMU_STATUS == 0)) || {
	echo "QEMU exited with ${QEMU_STATUS}" >&2
	exit 1
}
echo "KythOS VM acceptance passed"
