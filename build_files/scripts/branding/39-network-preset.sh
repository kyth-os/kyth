# shellcheck shell=bash
# ── Network preset (DoT + firewalld) ───────────────────────────────────────
install -m 0755 /ctx/kyth-apply-network /usr/bin/kyth-apply-network
# Apply once at build time so resolved.conf.d exists (offline, no network fetch)
if command -v kyth-apply-network >/dev/null 2>&1; then
    python3 -m kyth_shared.network_preset 2>/dev/null || true
fi
# firewalld zone already via sysconfig; this drop-in is hash-gated
