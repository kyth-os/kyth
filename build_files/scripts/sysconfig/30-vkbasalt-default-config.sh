#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── vkBasalt default config ───────────────────────────────────────────────────
# vkBasalt is only active when ENABLE_VKBASALT=1 is set (per-launch or globally).
# Pre-configure CAS sharpening so there's a sensible default when users opt in.
# casSharpness: 0.0 = maximum sharpening, 1.0 = no sharpening; 0.4 is a clean balance.
cat >/etc/vkBasalt.conf <<'VKBASALTEOF'
effects = cas
casSharpness = 0.4
# Toggle the effect on/off in-game
toggleKey = Home
VKBASALTEOF
