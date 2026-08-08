# shellcheck shell=bash
# ── Dev containers preset ────────────────────────────────────────────────
install -m 0755 /ctx/kyth-setup-devcontainer /usr/bin/kyth-setup-devcontainer
# devcontainers.toml declarative lives under ~/.config/kyth/ — hash-gated, no auto-create at build
