# shellcheck shell=bash
# ── Fonts & rendering preset ─────────────────────────────────────────────
# fontconfig 99-kyth-fonts.conf hash-gated, offline
if command -v fc-cache >/dev/null 2>&1; then
    mkdir -p /etc/fonts/conf.d 2>/dev/null || true
fi
