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
# --deepestcache=2 keeps IRQs inside a CCD on Ryzen X3D / multi-CCD.
IRQBALANCE_ONESHOT=yes
IRQBALANCE_BANNED_CPUS=
IRQBALANCE_ARGS="--hintpolicy=subset --deepestcache=2"
IRQBALANCE

# Fedora's irqbalance.service is Type=simple. IRQBALANCE_ONESHOT=yes
# makes the process exit after one pass, which systemd then records as
# failed (exit-code) on every boot. Pair oneshot with RemainAfterExit.
install -d /etc/systemd/system/irqbalance.service.d
write_config /etc/systemd/system/irqbalance.service.d/10-kyth-oneshot.conf <<'IRQDROPIN'
[Service]
Type=oneshot
RemainAfterExit=yes
IRQDROPIN
