#!/bin/bash
# shellcheck shell=bash
# 00-sysctl-compose — consolidated sysctl generator (single writer for 99-kyth-*.conf).
# Runs in sysconfig-static layer; replaces fragmented write_config sysctl fragments.
set -euo pipefail

PYTHONPATH="/ctx/kyth_shared:${PYTHONPATH:-}" python3 -m kyth_shared.sysctl_compose --emit-all

# Ensure legacy colliding files are gone; generator is single writer
rm -f /etc/sysctl.d/99-kyth.conf \
      /etc/sysctl.d/99-kyth-vm-compaction.conf \
      /etc/sysctl.d/99-kyth-network-qdisc.conf 2>/dev/null || true

# Modules that were previously loaded by retired fragments — still needed.
mkdir -p /etc/modules-load.d
printf '%s\n' 'tcp_bbr' > /etc/modules-load.d/bbr.conf
chmod 0644 /etc/modules-load.d/bbr.conf

if [[ -f /ctx/config/sysctl.conf ]]; then
    echo "00-sysctl-compose: dead file /ctx/config/sysctl.conf still present — delete after migrating keys" >&2
    exit 1
fi

echo "00-sysctl-compose: emitted $(ls -1 /etc/sysctl.d/99-kyth-*.conf 2>/dev/null | tr '\n' ' ')"
