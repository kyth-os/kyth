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
