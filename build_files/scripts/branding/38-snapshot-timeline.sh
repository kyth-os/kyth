# shellcheck shell=bash
# ── Snapshot timeline (btrfs + bootc) ────────────────────────────────────────
# Offline, hash-gated. Configures snapper for root AND home (btrfs only);
# timeline limits keep steady-state usage far under the shared /home quota
# (35% — see 46-snapshot-autoclean.sh and HOME_QUOTA_LIMIT_PCT in the Rust
# system::snapshot model, which documents the budget).
if command -v btrfs >/dev/null 2>&1 && btrfs filesystem show / >/dev/null 2>&1; then
    if command -v snapper >/dev/null 2>&1; then
        snapper -c root create-config / >/dev/null 2>&1 || true
        # keep timeline enabled, limit to 20
        snapper -c root set-config TIMELINE_CREATE=yes TIMELINE_LIMIT_HOURLY=5 TIMELINE_LIMIT_DAILY=7 >/dev/null 2>&1 || true
        if btrfs filesystem show /home >/dev/null 2>&1; then
            snapper -c home create-config /home >/dev/null 2>&1 || true
            # Home churns faster than /: wider hourly window, same daily
            # cap so root + home timelines stay under quota together.
            snapper -c home set-config TIMELINE_CREATE=yes TIMELINE_LIMIT_HOURLY=8 TIMELINE_LIMIT_DAILY=7 >/dev/null 2>&1 || true
        fi
    fi
fi
# Pre/post snapshots around updates and user polish. Update and polish flows
# run through this wrapper so a bad update always has a paired rollback
# point: a `pre` snapshot is taken first, the wrapped command runs, then a
# `post` snapshot is paired with the pre number. If the wrapped command
# fails, the pre number is printed so the user can roll back to it.
install -m 0755 /dev/stdin /usr/libexec/kyth-with-snapshots <<'SNAP_WRAP'
#!/usr/bin/env bash
# kyth-with-snapshots <description> <command> [args…]
# Usage from update/polish recipes: kyth-with-snapshots "before kyth update" ujust update
set -u
description="${1:?usage: kyth-with-snapshots <description> <command> [args…]}"; shift
pre=""
if command -v snapper >/dev/null 2>&1 && snapper -c root list >/dev/null 2>&1; then
    pre="$(snapper -c root create --type pre --description "${description}" --print-number 2>/dev/null || true)"
fi
"$@"
status=$?
if [[ -n "${pre}" ]]; then
    snapper -c root create --type post --pre-number "${pre}" --description "${description}" >/dev/null 2>&1 || true
    if [[ ${status} -ne 0 ]]; then
        echo "kyth-with-snapshots: command failed (exit ${status}); pre-update snapshot #${pre} retained for rollback" >&2
    fi
fi
exit ${status}
SNAP_WRAP
# The native binary is installed from the hub-web-builder stage in Dockerfile.
# Keep the Python source fixture out of the final image.
