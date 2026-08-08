#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Mesa Shader Cache Tuning ─────────────────────────────────────────────────
# Raises default shader cache limit to 10GB and enables single-file cache storage.
# Prevents games from discarding compiled shaders, eliminating stuttering on subsequent launches.
write_config /etc/environment.d/10-mesa-cache.conf <<'EOF'
MESA_SHADER_CACHE_MAX_SIZE=10G
MESA_DISK_CACHE_SINGLE_FILE=1
EOF
