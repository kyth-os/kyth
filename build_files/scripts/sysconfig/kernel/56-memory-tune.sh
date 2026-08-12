#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── RAM-aware memory tuning ─────────────────────────────────────────────────
# Installs memory-tune generator and systemd unit. The generator reads
# MemTotal once at boot and writes 99-kyth-memory.conf override (lexically
# after 99-kyth-base.conf) with swappiness/watermark/dirty scaling.

install -Dm0755 /ctx/kyth-shared/kyth_shared/memory_tune.py "/usr/lib/python*/site-packages/kyth_shared/memory_tune.py" 2>/dev/null || true

write_config /usr/lib/systemd/system/kyth-memory-tune.service <<'MEMSVC'
[Unit]
Description=Kyth RAM-aware memory tuning (MemTotal scaling)
After=multi-user.target
ConditionPathExists=/proc/meminfo

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -c "from kyth_shared.memory_tune import generate_memory_tune; generate_memory_tune()"
ExecStartPost=/usr/bin/sysctl --system
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
MEMSVC

systemctl enable kyth-memory-tune.service 2>/dev/null || true

# Install wrapper for manual tuning
install -Dm0755 /dev/stdin /usr/bin/kyth-memory-tune <<'WRAP'
#!/usr/bin/env bash
set -euo pipefail
case "${1:-status}" in
  status) python3 -c 'from kyth_shared.memory_tune import load_memory_tune,memory_tune_status; import os; c=load_memory_tune(); print(f"tier={c[\"tier\"]} swappiness={c[\"swappiness\"]} dirty={c[\"dirty_bytes\"]} active={memory_tune_status()}")' ;;
  apply) sudo python3 -c 'from kyth_shared.memory_tune import generate_memory_tune; generate_memory_tune()' && sudo sysctl --system >/dev/null 2>&1; echo "memory tune applied" ;;
  *) echo "Usage: kyth-memory-tune [status|apply]" >&2; exit 1 ;;
esac
WRAP
chmod 0755 /usr/bin/kyth-memory-tune 2>/dev/null || true
