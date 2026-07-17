#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── greenboot boot-time health checks ────────────────────────────────────────
# greenboot marks each boot good/bad and triggers automatic rollback to the
# previous bootc deployment if health checks fail across three consecutive boots.
# greenboot-default-health-checks adds basic required/wanted service checks out
# of the box. Installed last so a transient package issue here cannot gate the
# full image build — the core gaming stack lands regardless.
dnf5 install -y greenboot greenboot-default-health-checks
systemctl enable greenboot-healthcheck.service greenboot-set-rollback-trigger.service
