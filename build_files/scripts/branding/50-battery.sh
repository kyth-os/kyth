# shellcheck shell=bash
# ── Battery health + charge limit ────────────────────────────────────────
install -m 0755 /ctx/kyth-batteryd /usr/bin/kyth-batteryd
install -m 0644 /ctx/kyth-batteryd.service /usr/lib/systemd/system/kyth-batteryd.service
systemctl enable kyth-batteryd.service 2>/dev/null || true
