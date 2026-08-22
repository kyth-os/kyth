#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── KWin VRR policy — Automatic (fullscreen / direct scanout) ────────────────
# KDE Plasma ships with VRR disabled (VrrPolicy=0 / Never). Gaming users expect
# their 144 Hz / VRR monitor to actually use variable refresh in games.
# "Automatic" (1) enables VRR only when KWin hands a surface directly to the
# display (fullscreen / direct scanout) — i.e., during games — and reverts to
# fixed rate on the desktop. "Always" (2) would enable VRR even on composited
# desktop, which causes flicker artifacts on some panels and wastes panel power.
write_config /etc/xdg/kwinrc <<'KWINRCEOF'
[Effect-blur]
BlurStrength=3
NoiseStrength=0

[Plugins]
blurEnabled=false

[org.kde.kdecoration2]
ButtonsOnLeft=
ButtonsOnRight=IAX
library=org.kde.breeze
theme=Breeze

[Wayland]
VrrPolicy=1
KWINRCEOF
