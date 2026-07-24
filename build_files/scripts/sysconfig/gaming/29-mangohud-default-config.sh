#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── MangoHud default config ───────────────────────────────────────────────────
# Pre-configure a curated overlay: useful OOTB without being overwhelming.
# Users can override globally via ~/.config/MangoHud/MangoHud.conf or per-game
# via the MANGOHUD_CONFIG env var / Steam launch options.
mkdir -p /etc/skel/.config/MangoHud
cat >/etc/skel/.config/MangoHud/MangoHud.conf <<'MANGOHUDEOF'
# KythOS default MangoHud overlay — toggle with Shift_R+F12
# Full option reference: https://github.com/flightlessmango/MangoHud

toggle_hud=Shift_R+F12

# Position and style
position=top-left
background_alpha=0.5
font_size=20
text_color=FFFFFF
round_corners=4

# Frame metrics
fps
# Color-code FPS: green ≥60, yellow ≥30, red <30
fps_color_change=1
fps_value=60,30
# Show when an FPS cap/limit is active (Steam, MangoHud, or driver limiter)
show_fps_limit
frametime=1
frame_timing=1

# GPU
gpu_name
gpu_stats
gpu_temp
gpu_core_clock
gpu_mem_clock
vram
# GPU power draw — a sustained drop toward TDP indicates thermal throttling
gpu_power
# Active Vulkan driver (RADV, AMDVLK, ANV, etc.)
vulkan_driver

# CPU
cpu_stats
cpu_temp
cpu_mhz
# CPU package power — useful for spotting frequency boosts and throttle events
cpu_power

# System RAM
ram

# Battery (shown only on systems where a battery is present)
battery

# Presentation mode (FIFO=vsync, Immediate=tearing, Mailbox=triple-buffer)
present_mode

# Show Wine/Proton version when running Windows games
wine
engine_version
MANGOHUDEOF
