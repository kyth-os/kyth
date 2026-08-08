# shellcheck shell=bash
# ── Zram swap tiering ────────────────────────────────────────────────────
# zram-generator.conf hash-gated, applied via systemd-zram-setup@zram0.service
if command -v zramctl >/dev/null 2>&1; then
    mkdir -p /etc/systemd
fi
