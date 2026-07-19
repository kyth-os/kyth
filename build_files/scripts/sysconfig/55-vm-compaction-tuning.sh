#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── VM Memory Compaction Tuning ──────────────────────────────────────────────
# Reduces memory compaction frequency by increasing the fragmentation threshold,
# preventing background compaction thread spikes from dropping game frames.
mkdir -p /etc/sysctl.d
cat >/etc/sysctl.d/99-kyth-vm-compaction.conf <<'EOF'
vm.extfrag_threshold = 750
EOF
