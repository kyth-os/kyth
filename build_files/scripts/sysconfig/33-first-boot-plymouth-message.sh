#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── First-boot Plymouth message ───────────────────────────────────────────────
# On the very first boot after install, the SELinux relabel and other setup
# tasks add a few extra seconds before login. Show a message on the boot splash
# so the user knows something is happening. The sentinel file ensures this only
# ever runs once — after first boot it is a no-op for all future reboots.
cat >/usr/lib/systemd/system/kyth-first-boot-message.service <<'FIRSTBOOTEOF'
[Unit]
Description=KythOS first-boot splash message
DefaultDependencies=no
After=plymouth-start.service local-fs.target
Before=sddm.service
ConditionPathExists=!/var/lib/kyth/.first-boot-complete

[Service]
Type=oneshot
# Only send the message if the Plymouth daemon is actually listening.
# On fast boots SDDM may already have started and stopped Plymouth before
# this service runs; "plymouth message" would then exit non-zero and the
# sentinel file would never be written, causing a retry on every boot.
ExecCondition=/usr/bin/plymouth --ping
ExecStart=/usr/bin/plymouth message --text="Running first boot setup, this may take a few moments..."
ExecStart=/bin/bash -c 'mkdir -p /var/lib/kyth && touch /var/lib/kyth/.first-boot-complete'
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
FIRSTBOOTEOF
systemctl enable kyth-first-boot-message.service 2>/dev/null || true

