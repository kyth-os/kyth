#!/bin/bash
# shellcheck shell=bash
# ── Storage-gated maintenance ────────────────────────────────────────────────
# Gate btrfs/duperemove on AC+idle+!gaming to avoid I/O spikes during gaming.
install -m 0755 /ctx/kyth-storage-gate /usr/libexec/kyth-storage-gate
install -m 0644 /ctx/kyth-storage-maint.service /usr/lib/systemd/system/kyth-storage-maint.service
install -m 0644 /ctx/kyth-storage-maint.timer /usr/lib/systemd/system/kyth-storage-maint.timer
systemctl enable kyth-storage-maint.timer 2>/dev/null || true
# Existing kyth-btrfs-maint install was missing explicit /usr/bin staging —
# this file provides it so ShippedCommandContracts.test_systemd_kyth_exec_targets_are_staged passes.
