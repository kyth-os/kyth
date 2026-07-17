#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── MGLRU Thrashing Mitigation ───────────────────────────────────────────────
# Enables Multi-Gen LRU page reclamation on all paths to optimize memory eviction
# and prevent system lockups/thrashing under high memory pressure.
mkdir -p /etc/tmpfiles.d
cat >/etc/tmpfiles.d/kyth-mglru.conf <<'EOF'
w! /sys/kernel/mm/lru_gen/enabled - - - - 7
EOF
