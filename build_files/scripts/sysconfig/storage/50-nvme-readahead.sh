#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── NVMe Read-Ahead Tuning ───────────────────────────────────────────────────
# Gaming hint-aware: 2048 KB when /run/kyth/gaming-hint present (game active),
# 512 KB otherwise (desktop random I/O). Reduces read amplification for asset
# streaming while keeping sequential load benefit. Single flag file avoids
# per-device hotplug races.
write_config /etc/udev/rules.d/60-nvme-readahead.rules <<'EOF'
# ENV{DEVTYPE}=="disk" restricts this to whole-disk nodes (nvme0n1), not
# partitions (nvme0n1p1) — partitions have no queue/read_ahead_kb attribute
# of their own, so without this the rule fired on every partition too and
# logged a harmless but noisy "could not chase sysfs attribute" warning on
# every boot.
ACTION=="add|change", SUBSYSTEM=="block", KERNEL=="nvme[0-9]*n[0-9]*", ENV{DEVTYPE}=="disk", ATTR{queue/read_ahead_kb}="512"
ACTION=="add|change", SUBSYSTEM=="block", KERNEL=="nvme[0-9]*n[0-9]*", ENV{DEVTYPE}=="disk", TAG+="systemd", ENV{SYSTEMD_WANTS}="kyth-readahead-hint.service"
EOF
# Install hint service that toggles readahead via helper
install -m 0755 /ctx/kyth-readahead-hint /usr/bin/kyth-readahead-hint
write_config /usr/lib/systemd/system/kyth-readahead-hint.service <<'READAHEADEOF'
[Unit]
Description=Kyth readahead hint (gaming 2048 else 512)

[Service]
Type=oneshot
ExecStart=/usr/bin/kyth-readahead-hint apply
RemainAfterExit=yes
READAHEADEOF
