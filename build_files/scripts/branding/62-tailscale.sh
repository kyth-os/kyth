# shellcheck shell=bash
# ── Tailscale mesh ───────────────────────────────────────────────────────
# kyth-apply-tailscale is the native Rust binary copied from the
# hub-web-builder stage; no Python launcher remains in the source tree.
# Scoped firewalld zone for tailscale0 (offline, hash-gated): the old
# `trusted`-zone binding exposed every local port to the whole tailnet.
# The `tailscale` zone below opens only the explicit ports Tailscale needs
# (41641/udp WireGuard + the ports the user opens temporarily, below).
# Port-opening policy: anything beyond 41641/udp is TEMPORARY and
# documented at open time — use
#   firewall-cmd --zone=tailscale --add-port=<port>/<proto> --timeout=<secs>
# so the opening expires on its own, and record the reason in the Hub
# (Gaming > Tailscale). Permanent additions need a comment in this file.
if command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --permanent --new-zone=tailscale 2>/dev/null || true
    firewall-cmd --permanent --zone=tailscale --add-interface=tailscale0 2>/dev/null || true
    firewall-cmd --permanent --zone=tailscale --add-port=41641/udp 2>/dev/null || true
    firewall-cmd --permanent --zone=trusted --remove-interface=tailscale0 2>/dev/null || true
    firewall-cmd --reload 2>/dev/null || true
fi
