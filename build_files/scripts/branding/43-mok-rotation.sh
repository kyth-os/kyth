# shellcheck shell=bash
# ── SecureBoot MOK rotation ───────────────────────────────────────────────
install -m 0755 /ctx/kyth-mok-rotate /usr/bin/kyth-mok-rotate
install -m 0644 /ctx/kyth-mok-rotate.service /usr/lib/systemd/system/kyth-mok-rotate.service
install -m 0644 /ctx/kyth-mok-rotate.timer /usr/lib/systemd/system/kyth-mok-rotate.timer
systemctl enable kyth-mok-rotate.timer 2>/dev/null || true
