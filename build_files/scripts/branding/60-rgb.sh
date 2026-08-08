# shellcheck shell=bash
# ── RGB peripherals (openrgb/liquidctl) ──────────────────────────────────
install -m 0755 /ctx/kyth-apply-rgb /usr/bin/kyth-apply-rgb
install -m 0644 /ctx/kyth-rgb.service /usr/lib/systemd/user/kyth-rgb.service
systemctl --global enable kyth-rgb.service 2>/dev/null || true
