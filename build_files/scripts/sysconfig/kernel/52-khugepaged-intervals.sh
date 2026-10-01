#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── khugepaged Compaction Tuning ─────────────────────────────────────────────
# Relaxes Transparent Huge Pages (THP) collapse frequency and limits scanning overhead
# to eliminate transient CPU/memory latency spikes during gameplay.
write_config /etc/tmpfiles.d/kyth-khugepaged.conf <<'EOF'
w! /sys/kernel/mm/transparent_hugepage/khugepaged/scan_sleep_millisecs - - - - 10000
w! /sys/kernel/mm/transparent_hugepage/khugepaged/alloc_sleep_millisecs - - - - 60000
w! /sys/kernel/mm/transparent_hugepage/khugepaged/pages_to_scan - - - - 4096
# Do not stall allocations on direct compaction. "kernel.khugepaged_defrag" was
# never a sysctl (sysctl.d logged a failure each boot); the real knob is sysfs.
w! /sys/kernel/mm/transparent_hugepage/khugepaged/defrag - - - - 0
EOF
