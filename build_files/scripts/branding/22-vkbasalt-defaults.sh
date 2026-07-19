# shellcheck shell=bash
# ── vkBasalt defaults ─────────────────────────────────────────────────────────
# vkBasalt is inactive unless ENABLE_VKBASALT=1 is set per-game.
# Ship a default config (CAS sharpening) so it works correctly when enabled.
# Users can override with ~/.config/vkBasalt/vkBasalt.conf
install -m 0644 /ctx/vkBasalt.conf /etc/vkBasalt.conf
