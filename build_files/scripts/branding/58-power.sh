# shellcheck shell=bash
# ── Power tuned (governor/epp) ───────────────────────────────────────────
# power.toml hash-gated, powerprofilesctl custom + tlp.d drop-in offline
mkdir -p /etc/tlp.d 2>/dev/null || true
