#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── DXVK Asynchronous Shader Compilation ─────────────────────────────────────
# Configures DXVK to run async shader compilation for DX9/10/11 games.
# This prevents micro-stutters when encountering new shaders.
write_config /etc/dxvk.conf <<'EOF'
dxvk.enableAsync = True
dxvk.numCompilerThreads = 0
EOF

write_config /etc/environment.d/30-dxvk.conf <<'EOF'
DXVK_CONFIG_FILE=/etc/dxvk.conf
EOF
