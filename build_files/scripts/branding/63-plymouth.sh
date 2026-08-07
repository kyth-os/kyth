# shellcheck shell=bash
# ── Plymouth theme preset ────────────────────────────────────────────────
# plymouth-set-default-theme hash-gated, offline dracut re-use
if command -v plymouth-set-default-theme >/dev/null 2>&1; then
    plymouth-set-default-theme --list 2>/dev/null | grep -q kyth && plymouth-set-default-theme kyth 2>/dev/null || true
fi
