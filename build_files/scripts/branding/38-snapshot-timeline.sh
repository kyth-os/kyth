# shellcheck shell=bash
# ── Snapshot timeline (btrfs + bootc) ────────────────────────────────────────
# Offline, hash-gated. Configures snapper for root if btrfs is present.
if command -v btrfs >/dev/null 2>&1 && btrfs filesystem show / >/dev/null 2>&1; then
    if command -v snapper >/dev/null 2>&1; then
        snapper -c root create-config / >/dev/null 2>&1 || true
        # keep timeline enabled, limit to 20
        snapper -c root set-config TIMELINE_CREATE=yes TIMELINE_LIMIT_HOURLY=5 TIMELINE_LIMIT_DAILY=7 >/dev/null 2>&1 || true
    fi
fi
install -m 0755 /ctx/kyth-snapshot-timeline /usr/bin/kyth-snapshot-timeline
