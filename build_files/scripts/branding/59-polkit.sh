# shellcheck shell=bash
# ── Polkit presets ───────────────────────────────────────────────────────
# polkit.rules + sudoers.d/kyth-polkit hash-gated, offline
mkdir -p /etc/polkit-1/rules.d 2>/dev/null || true
mkdir -p /etc/sudoers.d 2>/dev/null || true
