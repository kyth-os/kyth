# shellcheck shell=bash
set -euo pipefail

# ── Zram swap tiering ────────────────────────────────────────────────────
# zram-generator.conf is produced in sysconfig/kernel/13-ntsync.sh and
# applied via systemd-zram-setup@zram0.service. That service is generator-
# created and Requires=dev-zram0.device, but the device itself is created
# lazily by the generator — causing the initial 90s timeout seen on every
# boot (dev-zram0.device/start timed out, then succeeds 1s later) and a
# degraded systemd-oomd window with no swap. Ensure the kernel module is
# loaded early and relax the device timeout so the first boot does not
# trip the timeout, and make stop handling tolerant of busy devices.
if command -v zramctl >/dev/null 2>&1; then
    mkdir -p /etc/systemd
fi

# Load zram early so /dev/zram0 exists before systemd-zram-setup runs.
# Without this, the first boot always times out waiting for dev-zram0.device
# (see journal: Job dev-zram0.device/start timed out -> succeeds 1s later).
# Keep modules-load for fallback, but primary early load is via initramfs
# (dracut add_drivers) so the device exists before switch-root and udev
# coldplug. On FA617NS the real-root udevd was not running for ~122s
# (10.76s Add -> 132.83s Found), so modules-load alone was too late.
write_line 'zram' /usr/lib/modules-load.d/zram.conf
write_config /etc/dracut.conf.d/99-kyth-zram.conf <<'DRACUTZRAM'
add_drivers+=" zram "
DRACUTZRAM

# Explicit early modprobe service ordered before udevd coldplug. Ensures
# /dev/zram0 uevent is queued before systemd-udev-trigger runs, even if
# initramfs driver was not included for a given kver. FA617NS host trace
# showed real-root udevd Deactivated for 122s after switch-root; triggering
# modprobe before udev-trigger avoids the race without dead-locking udevd
# startup (Before=udev-trigger only, not Before=udevd).
write_config /usr/lib/systemd/system/kyth-zram-early.service <<'ZRAM_EARLY'
[Unit]
Description=Kyth early zram modprobe (before udev coldplug)
DefaultDependencies=no
Before=systemd-udev-trigger.service
Wants=systemd-udevd.service
After=systemd-udevd.service
ConditionPathIsDirectory=/sys/class/block

[Service]
Type=oneshot
ExecStart=/sbin/modprobe zram num_devices=1
RemainAfterExit=yes

[Install]
WantedBy=sysinit.target
ZRAM_EARLY
systemctl enable kyth-zram-early.service 2>/dev/null || true

# Fail-fast instead of hiding the race with 180s. The device should now
# exist via initramfs/early service; if not, retry quickly rather than
# blocking graphical.target for 2m. Keep busy-device tolerant stop path.
write_config /etc/systemd/system/systemd-zram-setup@.service.d/10-kyth-zram.conf <<'ZRAMOVERRIDE'
[Unit]
JobTimeoutSec=30
JobRunningTimeoutSec=30
StartLimitIntervalSec=60
StartLimitBurst=3
[Service]
ExecStartPre=-/sbin/modprobe zram num_devices=1
Restart=on-failure
RestartSec=1
# On stop, zram may still be in use as swap; swapoff is handled by
# dev-zram0.swap unit, so ignore busy errors here.
ExecStopPost=-/usr/bin/bash -c 'echo 1 > /sys/block/zram0/reset 2>/dev/null || true'
ZRAMOVERRIDE

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
