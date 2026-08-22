# shellcheck shell=bash
set -euo pipefail

# ── Zram swap tiering ────────────────────────────────────────────────────
# zram-generator.conf is produced in sysconfig/kernel/13-ntsync.sh and
# applied via systemd-zram-setup@zram0.service. The generator Requires
# dev-zram0.device, which after switch-root deadlocks with udevd/sysinit
# (see kyth-zram-early below). Create the node without udev and drop that
# Requires so swap.target does not time out every boot.
if command -v zramctl >/dev/null 2>&1; then
    mkdir -p /etc/systemd
fi

# Load zram early so /dev/zram0 exists before systemd-zram-setup runs.
# After switch-root, real-root udevd is down (stopped at initrd-cleanup)
# until sysinit proceeds, and sysinit After=swap.target. If zram-setup
# Requires=dev-zram0.device (udev-ready) and kyth-zram-early After=udevd,
# the job queue deadlocks for JobTimeoutSec: device wait holds sysinit,
# udevd cannot start, swap.target times out. Do not wait for udev —
# create the node from sysfs and drop the .device Requires.
write_line 'zram' /usr/lib/modules-load.d/zram.conf
write_config /etc/dracut.conf.d/99-kyth-zram.conf <<'DRACUTZRAM'
add_drivers+=" zram "
DRACUTZRAM

install -Dm0755 /dev/stdin /usr/libexec/kyth-zram-ensure <<'ZRAMENSURE'
#!/usr/bin/bash
# Ensure the zram module is loaded and /dev/zram0 exists without udev.
set -euo pipefail
/sbin/modprobe zram num_devices=1 || true
if [[ ! -e /dev/zram0 && -r /sys/class/block/zram0/dev ]]; then
	IFS=: read -r maj min < /sys/class/block/zram0/dev
	if [[ -n "${maj:-}" && -n "${min:-}" ]]; then
		mknod -m 0600 /dev/zram0 b "$maj" "$min"
	fi
fi
ZRAMENSURE

# Start independently of udevd. After=udevd + swap.target's device wait
# is the 30s boot timeout on every FA617NS-class switch-root.
write_config /usr/lib/systemd/system/kyth-zram-early.service <<'ZRAM_EARLY'
[Unit]
Description=Kyth early zram device node (no udev wait)
DefaultDependencies=no
After=systemd-modules-load.service
Before=systemd-zram-setup@zram0.service swap.target
Wants=systemd-udevd.service
ConditionPathIsDirectory=/sys/class/block

[Service]
Type=oneshot
ExecStart=/usr/libexec/kyth-zram-ensure
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
ZRAM_EARLY
systemctl enable kyth-zram-early.service 2>/dev/null || true

# Drop generator Requires/BindsTo on the udev .device unit — empty
# assignment resets the merged list — and create the node ourselves.
write_config /etc/systemd/system/systemd-zram-setup@.service.d/10-kyth-zram.conf <<'ZRAMOVERRIDE'
[Unit]
Requires=
BindsTo=
After=kyth-zram-early.service systemd-modules-load.service
Wants=kyth-zram-early.service
JobTimeoutSec=30
JobRunningTimeoutSec=30
StartLimitIntervalSec=60
StartLimitBurst=3
[Service]
ExecStartPre=/usr/libexec/kyth-zram-ensure
Restart=on-failure
RestartSec=1
# On stop, zram may still be in use as swap; swapoff is handled by
# dev-zram0.swap unit, so ignore busy errors here.
ExecStopPost=-/usr/bin/bash -c 'echo 1 > /sys/block/zram0/reset 2>/dev/null || true'
ZRAMOVERRIDE

# Same deadlock: generated dev-zram0.swap BindsTo/Requires the udev device.
write_config /etc/systemd/system/dev-zram0.swap.d/10-kyth-async.conf <<'SWAPDEV'
[Unit]
Requires=
BindsTo=
After=systemd-zram-setup@zram0.service kyth-zram-early.service
SWAPDEV

# Boot timing observability for FA617NS-class stalls. Provides
# journalctl evidence without host nsenter (Operation not permitted
# in current toolbx). Used by kyth doctor.
write_config /usr/lib/systemd/system/kyth-boot-timing.service <<'BOOTTIMING'
[Unit]
Description=Kyth boot timing log (zram/udev)
After=multi-user.target
ConditionPathExists=/usr/bin/journalctl

[Service]
Type=oneshot
ExecStart=/usr/bin/bash -c 'journalctl -b -o short-monotonic | grep -E "zram|dev-zram|systemd-udevd|systemd-udev-trigger" > /var/log/kyth-boot-timing.log 2>/dev/null || true'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
BOOTTIMING
systemctl enable kyth-boot-timing.service 2>/dev/null || true
