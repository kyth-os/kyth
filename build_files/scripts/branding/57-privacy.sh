# shellcheck shell=bash
# ── Privacy preset (geoclue/flatpak) ─────────────────────────────────────
# geoclue.conf + flatpak overrides hash-gated, offline
if [[ -f /etc/geoclue/geoclue.conf ]]; then
    mkdir -p /etc/geoclue 2>/dev/null || true
fi
