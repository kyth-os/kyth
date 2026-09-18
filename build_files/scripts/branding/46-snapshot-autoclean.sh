# shellcheck shell=bash
# ── Snapshot autoclean (qgroup quota) ────────────────────────────────────
# Extends 38-snapshot-timeline with quota limit; offline, btrfs-guarded
#
# Quota budget (documented; keep in sync with HOME_QUOTA_LIMIT_PCT in the
# Rust system::snapshot model): snapper timelines (root + home) plus the
# read-only staging snapshots used for USB snapshot-then-send offload share
# this cap. 35% of /home was chosen so that on a small 256 GiB disk a
# pre-update snapshot (~a few GiB of changed extents) plus one in-flight
# USB offload staging snapshot always fit together — the old 20% tripped
# the limiter mid-update once the timeline had aged a few weeks, failing
# the very pre-update snapshot the update needed for rollback. Timeline
# pruning (TIMELINE_LIMIT_HOURLY/DAILY) keeps steady-state usage far below
# the cap; the headroom is for the worst case, not the average.
if command -v btrfs >/dev/null 2>&1 && btrfs filesystem show /home >/dev/null 2>&1; then
    btrfs quota enable /home 2>/dev/null || true
    btrfs qgroup limit 35% /home 2>/dev/null || true
fi
