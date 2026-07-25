#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Baloo file indexer — disabled by default ─────────────────────────────────
# Baloo (KDE's file indexer) runs heavy I/O scans on first boot and after game
# downloads, causing stutter mid-session. Disable it in the skel so new users
# start with indexing off. Users can re-enable it from System Settings → Search.
mkdir -p /etc/skel/.config
cat >/etc/skel/.config/baloofilerc <<'BALOOEOF'
[Basic Settings]
Indexing-Enabled=false
BALOOEOF
