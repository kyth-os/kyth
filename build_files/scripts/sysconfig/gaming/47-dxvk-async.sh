#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── DXVK Asynchronous Shader Compilation ─────────────────────────────────────
# Configures DXVK to run async shader compilation for DX9/10/11 games.
# This prevents micro-stutters when encountering new shaders.
mkdir -p /etc
cat >/etc/dxvk.conf <<'EOF'
dxvk.enableAsync = True
dxvk.numCompilerThreads = 0
EOF

mkdir -p /etc/environment.d
cat >/etc/environment.d/30-dxvk.conf <<'EOF'
DXVK_CONFIG_FILE=/etc/dxvk.conf
EOF
