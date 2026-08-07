# shellcheck shell=bash
# ── Scaling + ICC color ────────────────────────────────────────────────────
# Deploys per-output scaling + ICC via colord (offline, extends display_hdr)
if command -v colord >/dev/null 2>&1; then
    mkdir -p /usr/share/color/icc/kyth
fi
# kwinoutputconfig.json generated at first login via kyth-welcome, hash-gated
