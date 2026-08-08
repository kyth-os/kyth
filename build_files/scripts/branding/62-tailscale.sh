# shellcheck shell=bash
# ── Tailscale mesh ───────────────────────────────────────────────────────
install -m 0755 /ctx/kyth-apply-tailscale /usr/bin/kyth-apply-tailscale
# firewalld trusted zone for tailscale0 (offline, hash-gated)
if command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --permanent --zone=trusted --add-interface=tailscale0 2>/dev/null || true
fi
