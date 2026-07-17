#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── mimalloc Preload ─────────────────────────────────────────────────────────
# Preloads mimalloc for desktop environment applications and games.
# Applying this at the environment level prevents it from running for early boot/system services.
mkdir -p /etc/environment.d
cat >/etc/environment.d/20-mimalloc.conf <<'EOF'
LD_PRELOAD=libmimalloc.so
EOF
