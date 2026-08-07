# shellcheck shell=bash
# ── Snapshot autoclean (qgroup quota) ────────────────────────────────────
# Extends 38-snapshot-timeline with quota limit; offline, btrfs-guarded
if command -v btrfs >/dev/null 2>&1 && btrfs filesystem show /home >/dev/null 2>&1; then
    btrfs quota enable /home 2>/dev/null || true
    btrfs qgroup limit 20% /home 2>/dev/null || true
fi
