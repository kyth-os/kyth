#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── PipeWire low-latency audio ─────────────────────────────────────────────────
# Base drop-in stays conservative: 1024 samples at 48 kHz (~21 ms) with a
# 64-sample floor. Aggressive quanta break Bluetooth (SBC/LDAC headroom) and
# crackle on weak DSPs; apps that need less (games, pro-audio) negotiate down
# per-stream or get 128 samples via the gaming profile only
# (kyth_shared.pipewire_gaming → 99-kyth-gaming.conf, removed when balanced).
# min-quantum=64 still lets pro-audio apps request low latency explicitly.
write_config /etc/pipewire/pipewire.conf.d/99-kyth.conf <<'PWEOF'
context.properties = {
    default.clock.rate          = 48000
    default.clock.quantum       = 1024
    default.clock.min-quantum   = 64
    default.clock.max-quantum   = 8192
    # Allow PipeWire to switch between 44100 and 48000 Hz rather than resampling.
    # Without this, a game or app that outputs at 44100 Hz forces the entire graph
    # (mic, desktop audio, etc.) through a sample-rate converter — adding CPU
    # overhead and latency. With it, PipeWire renegotiates the clock rate instead.
    default.clock.allowed-rates = [ 44100 48000 ]
}
PWEOF

# Gaming-profile template (128 samples ≈ 2.7 ms). NOT installed into
# pipewire.conf.d here — kyth-pipewire-gaming links it in only while the gaming
# profile is active and removes it on return to balanced.
write_config /usr/share/kyth/pipewire-gaming-128.conf <<'PWGAMEEOF'
# Kyth gaming-profile PipeWire quantum — applied only while gaming.
context.properties = {
    default.clock.rate          = 48000
    default.clock.quantum       = 128
    default.clock.min-quantum   = 64
    default.clock.max-quantum   = 8192
    default.clock.allowed-rates = [ 44100 48000 ]
}
PWGAMEEOF
