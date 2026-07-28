# shellcheck shell=bash
# ── Wayland/X11 auto-detect (runs before SDDM on every boot) ─────────────────
# kyth-configure-session detects VM vs bare metal and writes the SDDM session
# conf before the greeter starts. Bare metal gets Wayland (VRR, HDR, lower
# latency); VMs keep X11 so SDDM's Wayland compositor mode doesn't fail against
# virtual GPU drivers that lack DRM/KMS backend support.
# The script runs as SDDM's ExecStartPre — fast, idempotent, no flag file.
install -m 0755 /ctx/kyth-configure-session /usr/bin/kyth-configure-session

write_config /usr/lib/systemd/system/sddm.service.d/10-kyth-detect-session.conf <<'SDDMDROPINEOF'
[Service]
ExecStartPre=/usr/bin/kyth-configure-session
SDDMDROPINEOF
