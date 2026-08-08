#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── NVMe Read-Ahead Tuning ───────────────────────────────────────────────────
# Increases block device read-ahead to 2048 KB for NVMe drives,
# improving sequential disk read throughput and game loading times.
write_config /etc/udev/rules.d/60-nvme-readahead.rules <<'EOF'
# ENV{DEVTYPE}=="disk" restricts this to whole-disk nodes (nvme0n1), not
# partitions (nvme0n1p1) — partitions have no queue/read_ahead_kb attribute
# of their own, so without this the rule fired on every partition too and
# logged a harmless but noisy "could not chase sysfs attribute" warning on
# every boot.
ACTION=="add|change", SUBSYSTEM=="block", KERNEL=="nvme[0-9]*n[0-9]*", ENV{DEVTYPE}=="disk", ATTR{queue/read_ahead_kb}="2048"
EOF
