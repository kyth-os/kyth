# shellcheck shell=bash
# ── PipeWire low-latency presets ───────────────────────────────────────────
install -m 0755 /ctx/kyth-apply-pipewire-latency /usr/bin/kyth-apply-pipewire-latency
# drop-in already via kyth-apply-pipewire-latency at build time (offline)
if command -v kyth-apply-pipewire-latency >/dev/null 2>&1; then
    kyth-apply-pipewire-latency 2>/dev/null || true
fi
