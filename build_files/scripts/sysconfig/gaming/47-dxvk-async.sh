#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── DXVK defaults ────────────────────────────────────────────────────────────
# Proton 11 still ships a DXVK 2.7.1 support branch; GE-Proton and
# Proton-CachyOS track newer DXVK (3.x). Both already compile shaders on
# worker threads. The old unofficial async shader toggle is not part of
# upstream DXVK, was dropped from GE-Proton years ago, and can trip
# kernel-level anti-cheat — do not re-enable it globally.
#
# DXVK 3.0 also removed DXVK_FRAME_RATE. Cap FPS with Gamescope or MangoHud
# (see kyth-gamescope presets and /etc/skel/.config/MangoHud/MangoHud.conf).
# numCompilerThreads = 0 means "use all CPU cores" (DXVK default).
write_config /etc/dxvk.conf <<'EOF'
dxvk.numCompilerThreads = 0
EOF

write_config /etc/environment.d/30-dxvk.conf <<'EOF'
DXVK_CONFIG_FILE=/etc/dxvk.conf
EOF
