# shellcheck shell=bash
# ── Cloud Drive parity (rclone + kio) ────────────────────────────────────
install -m 0755 /ctx/kyth-cloud-mount /usr/bin/kyth-cloud-mount
install -m 0644 /ctx/rclone@.service /usr/lib/systemd/user/rclone@.service
# kio network:/ Dolphin entry via kio-rclone already if rclone present
