# shellcheck shell=bash
# ── Gaming save cloud (restic local + rclone) ────────────────────────────
install -m 0755 /ctx/kyth-save-sync /usr/bin/kyth-save-sync
# save-cloud.toml + restic repo /var/cache/kyth/saves + rclone remote hash-gated
