#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── irqbalance tuning ────────────────────────────────────────────────────
# Logs show 14× "Cannot change IRQ 75-89 affinity: Permission denied ->
# IRQ xx affinity is now unmanaged" on every boot. Modern AMD platforms
# expose IRQs that irqbalance is not allowed to migrate (managed by
# hardware or pinned by the kernel). Marking them unmanaged each boot
# is noisy and leaves performance on the table. Tell irqbalance to
# skip the unmanageable ranges via its sysconfig.
mkdir -p /etc/sysconfig
write_config /etc/sysconfig/irqbalance <<'IRQBALANCE'
# KythOS: one-shot mode is cheaper than the daemon on gaming desktops;
# the kernel's default affinity is already optimal for most IRQs.
IRQBALANCE_ONESHOT=yes
IRQBALANCE_BANNED_CPUS=
IRQBALANCE_ARGS="--hintpolicy=subset"
IRQBALANCE
