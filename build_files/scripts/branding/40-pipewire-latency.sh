# shellcheck shell=bash
# ── PipeWire low-latency presets ───────────────────────────────────────────
install -m 0755 /ctx/kyth-apply-pipewire-latency /usr/bin/kyth-apply-pipewire-latency
# Best-effort apply during image build (usually a no-op without user toml);
# at runtime, users re-run kyth-apply-pipewire-latency after editing
# ~/.config/kyth/pipewire-latency.toml to write real pipewire.conf.d drop-ins.
if command -v kyth-apply-pipewire-latency >/dev/null 2>&1; then
    kyth-apply-pipewire-latency 2>/dev/null || true
fi
