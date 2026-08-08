# shellcheck shell=bash
# ── Gaming containers isolation ──────────────────────────────────────────
install -m 0755 /ctx/kyth-isolate-game /usr/bin/kyth-isolate-game
# podman rootless already via sysconfig; seccomp default via /etc/containers/seccomp.json stays
