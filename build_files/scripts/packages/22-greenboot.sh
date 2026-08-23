#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── greenboot boot-time health checks ────────────────────────────────────────
# greenboot marks each boot good/bad and triggers automatic rollback to the
# previous bootc deployment if health checks fail across three consecutive boots.
# KythOS deliberately does not install greenboot-default-health-checks: its
# required repository-DNS probe can reboot an otherwise healthy offline desktop
# and cannot be repaired by rolling back the OS. KythOS installs immutable,
# rollback-actionable checks during the branding phase instead.
dnf5 install -y greenboot
systemctl enable greenboot-healthcheck.service greenboot-set-rollback-trigger.service

# Upstream unit is Type=oneshot without RemainAfterExit. After it
# succeeds (often in <1s, including a /boot remount), anything that
# Wants= it starts it again and the default start-limit fails the
# unit for the boot even though the trigger was written. Keep it
# active and remount /boot the Kyth way (bind,rw — plain remount,rw
# is EINVAL on the autofs+btrfs bind).
install -d /usr/lib/systemd/system/greenboot-set-rollback-trigger.service.d
cat > /usr/lib/systemd/system/greenboot-set-rollback-trigger.service.d/10-kyth.conf <<'GBROLLBACK'
[Service]
RemainAfterExit=yes
StartLimitIntervalSec=120
StartLimitBurst=5
ExecStartPre=-/usr/libexec/kyth-finalize-staged prepare-boot
GBROLLBACK
