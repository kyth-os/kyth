# shellcheck shell=bash
# ── Wayland session + software-compose rescue (runs before SDDM on every boot)
# kyth-configure-session rewrites 11-kyth-session.conf to Plasma Wayland so
# older images that stored DisplayServer=x11 for VMs or nomodeset migrate on
# reboot. kyth-sddm-compositor wraps kwin_wayland and enables QPainter/llvmpipe
# when there is no DRM render node, on live media, or with nomodeset. The helper
# fail-opens: a write error logs a warning and returns 0 so ExecStartPre cannot
# block the greeter — 10-kyth.conf still provides the Wayland default in that
# case.
install -m 0755 /ctx/kyth-configure-session /usr/bin/kyth-configure-session
install -m 0755 /ctx/kyth-sddm-compositor /usr/bin/kyth-sddm-compositor

write_config /usr/lib/systemd/system/sddm.service.d/10-kyth-detect-session.conf <<'SDDMDROPINEOF'
[Service]
ExecStartPre=/usr/bin/kyth-configure-session
SDDMDROPINEOF
