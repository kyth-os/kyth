#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── VM Memory Compaction Tuning ──────────────────────────────────────────────
# Reduces memory compaction frequency by increasing the fragmentation threshold,
# preventing background compaction thread spikes from dropping game frames.
write_config /etc/sysctl.d/99-kyth-vm-compaction.conf <<'EOF'
vm.extfrag_threshold = 750
EOF
