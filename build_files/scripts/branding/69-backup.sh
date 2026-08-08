# shellcheck shell=bash
# ── Backup Full (restic + btrfs send) ────────────────────────────────────
install -m 0755 /ctx/kyth-backup /usr/bin/kyth-backup
# backup.toml + restic repo /var/cache/kyth/backup + btrfs send hash-gated
