#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# Write the BLS entry after bootc releases the sysroot lock, and again at
# shutdown if the in-session finalize was skipped (raw `bootc upgrade`).
# See docs/update-safety.md.
install -m 0755 /ctx/sysconfig/kyth-finalize-staged /usr/libexec/kyth-finalize-staged
ln -sfn /usr/libexec/kyth-finalize-staged /usr/bin/kyth-finalize-staged

install -m 0644 /ctx/sysconfig/systemd/kyth-boot-rw.service /usr/lib/systemd/system/kyth-boot-rw.service
systemctl enable kyth-boot-rw.service 2>/dev/null || true

install -d /usr/lib/systemd/system/ostree-finalize-staged.service.d
write_config /usr/lib/systemd/system/ostree-finalize-staged.service.d/10-kyth-boot-rw.conf <<'EOF'
[Service]
# bootc starts this unit while it still holds the sysroot write-lock.
# ExecStart must only remount /boot (prepare-boot). Finalize here deadlocks
# against bootc until kyth-safe-upgrade's timeout kills the upgrade.
# The '-' prefix keeps the unit active if remount fails so ExecStop can
# finalize at shutdown after remounting again.
ExecStart=
ExecStart=-/usr/libexec/kyth-finalize-staged prepare-boot
ExecStop=
ExecStop=/usr/libexec/kyth-finalize-staged
EOF
