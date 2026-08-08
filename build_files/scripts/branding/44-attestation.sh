# shellcheck shell=bash
# ── Attestation viewer (cosign offline) ───────────────────────────────────
# Attest bundle cached at build time via supply-chain.yml, verified offline at runtime
if [[ -f /ctx/attest.json ]]; then
    install -m 0644 /ctx/attest.json /usr/share/kyth/attest.json
fi
# Hub Supply-Chain tab reads /usr/share/kyth/attest.json via kyth_shared.attest
