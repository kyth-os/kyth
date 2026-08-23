# shellcheck shell=bash
set -euo pipefail

# ── Zram swap (udev-independent) ────────────────────────────────────────
# systemd-zram-generator + systemd-zram-setup@zram0 Requires/After
# dev-zram0.device. After switch-root, udevd is down until sysinit, and
# sysinit After=swap.target — so waiting for the udev device deadlocks
# until JobTimeoutSec (30s on this image). Users see that as
# dev-zram0.device / "dev-zram0.service" timing out every boot.
#
# Own the swap setup: create the node from sysfs, mkswap/swapon, and
# mask the generator units so they cannot enter the job queue.

write_line 'zram' /usr/lib/modules-load.d/zram.conf
write_config /etc/dracut.conf.d/99-kyth-zram.conf <<'DRACUTZRAM'
add_drivers+=" zram "
DRACUTZRAM

install -Dm0755 /dev/stdin /usr/libexec/kyth-zram-swap <<'ZRAMSWAP'
#!/usr/bin/bash
# Set up /dev/zram0 swap without waiting for udev or zram-generator.
set -euo pipefail

ensure_node() {
	/sbin/modprobe zram num_devices=1 2>/dev/null || true
	if [[ ! -e /dev/zram0 && -r /sys/class/block/zram0/dev ]]; then
		IFS=: read -r maj min < /sys/class/block/zram0/dev
		if [[ -n "${maj:-}" && -n "${min:-}" ]]; then
			mknod -m 0600 /dev/zram0 b "$maj" "$min"
		fi
	fi
}

size_bytes() {
	local mem_kb mem_mb size_mb
	mem_kb=$(awk '/^MemTotal:/{print $2; exit}' /proc/meminfo)
	mem_mb=$((${mem_kb:-0} / 1024))
	size_mb=$((mem_mb / 2))
	if ((size_mb > 8192)); then
		size_mb=8192
	fi
	if ((size_mb < 64)); then
		size_mb=64
	fi
	# Honor memory_tune / zram-generator.conf when the formula is obvious.
	if [[ -r /etc/systemd/zram-generator.conf ]]; then
		local raw
		raw=$(awk -F= '/^[[:space:]]*zram-size[[:space:]]*=/{sub(/^[^=]*=/, ""); gsub(/[[:space:]]/, ""); print; exit}' /etc/systemd/zram-generator.conf)
		case "${raw}" in
		ram) size_mb=${mem_mb} ;;
		ram*0.5 | 'min(ram*0.5,8192)' | 'min(ram*.5,8192)')
			size_mb=$((mem_mb / 2))
			((size_mb > 8192)) && size_mb=8192
			;;
		esac
	fi
	echo $((size_mb * 1024 * 1024))
}

compression() {
	local algo=lz4
	if [[ -r /etc/systemd/zram-generator.conf ]]; then
		local listed
		listed=$(awk -F= '/^[[:space:]]*compression-algorithm[[:space:]]*=/{sub(/^[^=]*=/, ""); gsub(/[[:space:]]/, ""); print; exit}' /etc/systemd/zram-generator.conf)
		[[ -n "${listed}" ]] && algo=${listed%%,*}
	fi
	echo "${algo}"
}

cmd=${1:-start}
case "${cmd}" in
start)
	if grep -q '^/dev/zram0 ' /proc/swaps 2>/dev/null; then
		exit 0
	fi
	ensure_node
	if [[ ! -e /dev/zram0 ]]; then
		echo "kyth-zram-swap: /dev/zram0 missing; skipping swap" >&2
		exit 0
	fi
	echo 1 >/sys/block/zram0/reset 2>/dev/null || true
	algo=$(compression)
	echo "${algo}" >/sys/block/zram0/comp_algorithm 2>/dev/null || true
	if ! echo "$(size_bytes)" >/sys/block/zram0/disksize; then
		echo "kyth-zram-swap: could not set disksize; skipping" >&2
		exit 0
	fi
	if ! /sbin/mkswap /dev/zram0 >/dev/null; then
		echo "kyth-zram-swap: mkswap failed; skipping" >&2
		exit 0
	fi
	if ! /sbin/swapon -p 100 /dev/zram0; then
		echo "kyth-zram-swap: swapon failed; skipping" >&2
		exit 0
	fi
	;;
stop)
	/sbin/swapoff /dev/zram0 2>/dev/null || true
	echo 1 >/sys/block/zram0/reset 2>/dev/null || true
	;;
*)
	echo "Usage: kyth-zram-swap [start|stop]" >&2
	exit 1
	;;
esac
ZRAMSWAP

write_config /usr/lib/systemd/system/kyth-zram-swap.service <<'ZRAMSVCEOF'
[Unit]
Description=Kyth zram swap (no udev device wait)
DefaultDependencies=no
After=systemd-modules-load.service
Before=swap.target
# Never After=/Requires= a .device unit — that is the switch-root deadlock.
ConditionPathIsDirectory=/sys/class/block
StartLimitIntervalSec=60
StartLimitBurst=3

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/libexec/kyth-zram-swap start
ExecStop=/usr/libexec/kyth-zram-swap stop
TimeoutStartSec=20

[Install]
WantedBy=sysinit.target
ZRAMSVCEOF
systemctl enable kyth-zram-swap.service 2>/dev/null || true

# Disable the generator so it cannot recreate dev-zram0.device /
# dev-zram0.swap / systemd-zram-setup@zram0.service on daemon-reload.
install -d /etc/systemd/system-generators
printf '%s\n' '#!/bin/true' >/etc/systemd/system-generators/zram-generator
chmod 0755 /etc/systemd/system-generators/zram-generator

# Mask leftover units from earlier images / generator leftovers. A masked
# device unit is skipped (not failed) if udev later tries to plug it.
for unit in \
	dev-zram0.device \
	dev-zram0.swap \
	systemd-zram-setup@zram0.service; do
	ln -sfn /dev/null "/etc/systemd/system/${unit}"
	systemctl mask "${unit}" 2>/dev/null || true
done

# Drop the 30s device/swap timeouts that guaranteed a failed unit.
rm -f /etc/systemd/system/dev-zram0.device.d/10-timeout.conf
rm -f /etc/systemd/system/swap.target.d/10-kyth-async.conf
rmdir /etc/systemd/system/dev-zram0.device.d 2>/dev/null || true
rmdir /etc/systemd/system/swap.target.d 2>/dev/null || true

# Compatibility name used by older units/docs.
install -Dm0755 /dev/stdin /usr/libexec/kyth-zram-ensure <<'ZRAMENSURE'
#!/usr/bin/bash
exec /usr/libexec/kyth-zram-swap start
ZRAMENSURE

# Boot timing observability for FA617NS-class stalls.
write_config /usr/lib/systemd/system/kyth-boot-timing.service <<'BOOTTIMING'
[Unit]
Description=Kyth boot timing log (zram/udev)
After=local-fs.target
ConditionPathExists=/usr/bin/journalctl

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'journalctl -b -o short-monotonic | grep -E "zram|dev-zram|systemd-udevd|systemd-udev-trigger" > /var/log/kyth-boot-timing.log 2>/dev/null || true'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
BOOTTIMING
systemctl enable kyth-boot-timing.service 2>/dev/null || true
