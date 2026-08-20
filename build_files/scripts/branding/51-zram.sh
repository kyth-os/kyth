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
write_line 'zram' /usr/lib/modules-load.d/zram.conf

# Tolerate the race where systemd requests dev-zram0.device before the
# generator has created it: extend the device timeout from 90s default.
# Also make the zram-setup stop path ignore busy-device errors on shutdown
# (Error: Device or resource busy) which otherwise marks the service failed.
mkdir -p /etc/systemd/system/systemd-zram-setup@.service.d
cat > /etc/systemd/system/systemd-zram-setup@.service.d/10-kyth-zram.conf <<'ZRAMOVERRIDE'
[Unit]
JobTimeoutSec=180
[Service]
# On stop, zram may still be in use as swap; swapoff is handled by
# dev-zram0.swap unit, so ignore busy errors here.
ExecStopPost=-/usr/bin/bash -c 'echo 1 > /sys/block/zram0/reset 2>/dev/null || true'
ZRAMOVERRIDE
