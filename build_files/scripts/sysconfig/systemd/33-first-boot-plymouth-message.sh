#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── First-boot Plymouth message ───────────────────────────────────────────────
# On the very first boot after install, the SELinux relabel and other setup
# tasks add a few extra seconds before login. Show a message on the boot splash
# so the user knows something is happening. The sentinel file ensures this only
# ever runs once — after first boot it is a no-op for all future reboots.
write_config /usr/lib/systemd/system/kyth-first-boot-message.service <<'FIRSTBOOTEOF'
[Unit]
Description=KythOS first-boot splash message
DefaultDependencies=no
After=plymouth-start.service local-fs.target
Before=plasmalogin.service
ConditionPathExists=!/var/lib/kyth/.first-boot-complete

[Service]
Type=oneshot
RemainAfterExit=yes
StateDirectory=kyth
# Write the sentinel first. ExecCondition=plymouth --ping skipped the
# whole unit (and the stamp) whenever Plymouth had already quit, so
# this retried on every later boot. '-' keeps a missing daemon from
# failing the unit.
ExecStart=/bin/bash -c 'mkdir -p /var/lib/kyth && touch /var/lib/kyth/.first-boot-complete'
ExecStart=-/usr/bin/plymouth --ping
ExecStart=-/usr/bin/plymouth message --text="Running first boot setup, this may take a few moments..."
ExecStart=-/usr/bin/plymouth message --text="After login, open Kyth Hub to finish installing your preferred software."

[Install]
WantedBy=multi-user.target
FIRSTBOOTEOF
systemctl enable kyth-first-boot-message.service 2>/dev/null || true
