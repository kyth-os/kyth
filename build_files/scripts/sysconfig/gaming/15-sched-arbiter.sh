#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Scheduler arbiter — single placement owner ───────────────────────────────
# Installs the arbiter CLI and systemd unit. The arbiter replaces stacked
# scheduling (scx_rusty + ananicy pin + gamemode pin_cores + boost affinity)
# with a single writer. See kyth_shared/sched_arbiter.py.

install -Dm0755 /ctx/kyth-sched-arbiter /usr/bin/kyth-sched-arbiter

write_config /usr/lib/systemd/system/kyth-sched-arbiter.service <<'ARBSVCEOF'
[Unit]
Description=Kyth scheduler arbiter (single placement owner)
After=multi-user.target
Before=gamemode.service

[Service]
Type=oneshot
ExecStart=/usr/bin/kyth-sched-arbiter apply
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
ARBSVCEOF

systemctl enable kyth-sched-arbiter.service 2>/dev/null || true

# Default arbiter state — auto-detect SCX vs BORE
mkdir -p /etc/kyth
if [[ ! -f /etc/kyth/sched-arbiter.toml ]]; then
    cat > /etc/kyth/sched-arbiter.toml <<'ARBTOMEOF'
# Kyth scheduler arbiter — single writer for placement
# chosen: auto (detect SCX), scx_rusty, bore, balanced
chosen = "auto"
allow_ananicy_pin = false
gamemode_pin = false
ARBTOMEOF
    chmod 0644 /etc/kyth/sched-arbiter.toml
fi
