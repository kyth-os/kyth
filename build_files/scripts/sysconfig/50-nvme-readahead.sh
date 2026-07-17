#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── NVMe Read-Ahead Tuning ───────────────────────────────────────────────────
# Increases block device read-ahead to 2048 KB for NVMe drives,
# improving sequential disk read throughput and game loading times.
mkdir -p /etc/udev/rules.d
cat >/etc/udev/rules.d/60-nvme-readahead.rules <<'EOF'
ACTION=="add|change", KERNEL=="nvme[0-9]*n[0-9]*", ATTR{queue/read_ahead_kb}="2048"
EOF
