# shellcheck shell=bash
# ── Backup Full (restic + btrfs send) ────────────────────────────────────
# kyth-backup is the native Rust binary copied from the
# hub-web-builder stage; no Python launcher remains in the source tree.
# backup.toml + restic repo on EXTERNAL media + snapshot-then-send btrfs
# offload, hash-gated. Rest of the policy lives in backup_config.rs:
# password-file, forget retention, restic check, nonzero exit on failure.
#
# OPT-IN scheduling: the user timer below is INSTALLED but never enabled by
# the image. Backups only run on a schedule after the user BOTH sets
# `enabled = true` in /etc/kyth/backup.toml (pointing `repo` at external
# media — the same-disk default is refused without `allow_same_disk`) AND
# runs `systemctl --user enable --now kyth-backup.timer`. A backup the user
# never asked for is a privacy incident; a same-disk "backup" is data loss
# with extra steps. Neither ships by default.

install -d /usr/lib/systemd/user
cat >/usr/lib/systemd/user/kyth-backup.service <<'BACKUP_SERVICE'
[Unit]
Description=KythOS full /home backup (restic + btrfs send to USB)
Documentation=https://github.com/kyth-os/kyth
# The binary refuses to run against a same-disk repo without
# allow_same_disk, and exits nonzero on any restic failure so the timer
# records the failure instead of faking a healthy backup.
ConditionPathExists=/etc/kyth/backup.toml

[Service]
Type=oneshot
ExecStart=/usr/bin/kyth-backup
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
BACKUP_SERVICE
cat >/usr/lib/systemd/user/kyth-backup.timer <<'BACKUP_TIMER'
[Unit]
Description=KythOS full /home backup (weekly, opt-in)

[Timer]
# Weekly off-hours run with a persistent catch-up. Installed DISABLED:
# enable only after pointing backup.toml at external media.
OnCalendar=Sun 03:00
RandomizedDelaySec=30m
Persistent=true

[Install]
WantedBy=timers.target
BACKUP_TIMER
# Deliberately NO `systemctl --user enable` here: scheduling is opt-in
# (see header). Enabling an unconfigured timer would either no-op on the
# ConditionPathExists gate or, worse, train users to ignore a failing unit.
