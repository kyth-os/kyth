# shellcheck shell=bash
# ── Wayland/X11 auto-detect (runs before SDDM on every boot) ─────────────────
# kyth-configure-session detects VM vs bare metal and writes the SDDM session
# conf before the greeter starts. Bare metal gets Wayland (VRR, HDR, lower
# latency); VMs keep X11 so SDDM's Wayland compositor mode doesn't fail against
# virtual GPU drivers that lack DRM/KMS backend support.
# The script runs as SDDM's ExecStartPre — fast, idempotent, no flag file.
cat >/usr/bin/kyth-configure-session <<'CONFIGURESESIONEOF'
#!/bin/bash
mkdir -p /etc/sddm.conf.d
if systemd-detect-virt -q 2>/dev/null; then
    cat >/etc/sddm.conf.d/11-kyth-session.conf <<'EOF'
[General]
DisplayServer=x11
DefaultSession=plasmax11.desktop
EOF
else
    cat >/etc/sddm.conf.d/11-kyth-session.conf <<'EOF'
[General]
DisplayServer=wayland
DefaultSession=plasma.desktop
EOF
fi
CONFIGURESESIONEOF
chmod +x /usr/bin/kyth-configure-session

mkdir -p /usr/lib/systemd/system/sddm.service.d
cat >/usr/lib/systemd/system/sddm.service.d/10-kyth-detect-session.conf <<'SDDMDROPINEOF'
[Service]
ExecStartPre=/usr/bin/kyth-configure-session
SDDMDROPINEOF
