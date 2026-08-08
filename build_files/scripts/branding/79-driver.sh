# shellcheck shell=bash
# ── Driver helper (nvidia/open + mesa_git) ───────────────────────────────
install -m 0755 /ctx/kyth-driver-switch /usr/bin/kyth-driver-switch
# driver.toml hash-gated gpu auto/nvidia/open + mesa_git via hardware_policy + repos.json
