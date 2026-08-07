# shellcheck shell=bash
# ── Plasma drift reconciler ──────────────────────────────────────────────
install -m 0755 /ctx/kyth-apply-plasma /usr/bin/kyth-apply-plasma
# declarative plasma.toml lives under ~/.config/kyth/ and /etc/kyth/ — hash-gated
