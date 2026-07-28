#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── PipeWire low-latency audio ─────────────────────────────────────────────────
# 128 samples at 48 kHz = ~2.7 ms latency — low enough to eliminate perceptible
# audio lag in games while staying stable on typical hardware.
# min-quantum=32 lets pro-audio apps request sub-1 ms when needed.
# Apps that need higher buffering (e.g. Bluetooth) negotiate up automatically.
write_config /etc/pipewire/pipewire.conf.d/99-kyth.conf <<'PWEOF'
context.properties = {
    default.clock.rate          = 48000
    default.clock.quantum       = 128
    default.clock.min-quantum   = 32
    default.clock.max-quantum   = 8192
    # Allow PipeWire to switch between 44100 and 48000 Hz rather than resampling.
    # Without this, a game or app that outputs at 44100 Hz forces the entire graph
    # (mic, desktop audio, etc.) through a sample-rate converter — adding CPU
    # overhead and latency. With it, PipeWire renegotiates the clock rate instead.
    default.clock.allowed-rates = [ 44100 48000 ]
}
PWEOF
