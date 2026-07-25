#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── khugepaged Compaction Tuning ─────────────────────────────────────────────
# Relaxes Transparent Huge Pages (THP) collapse frequency and limits scanning overhead
# to eliminate transient CPU/memory latency spikes during gameplay.
mkdir -p /etc/tmpfiles.d
cat >/etc/tmpfiles.d/kyth-khugepaged.conf <<'EOF'
w! /sys/kernel/mm/transparent_hugepage/khugepaged/scan_sleep_millisecs - - - - 10000
w! /sys/kernel/mm/transparent_hugepage/khugepaged/alloc_sleep_millisecs - - - - 60000
w! /sys/kernel/mm/transparent_hugepage/khugepaged/pages_to_scan - - - - 4096
EOF
