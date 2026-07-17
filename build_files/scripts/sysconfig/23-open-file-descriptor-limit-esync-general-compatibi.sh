#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Open file descriptor limit (esync / general compatibility) ────────────────
# esync requires a high open-file limit; even with NTSYNC some games fall back
# to it. 1048576 matches Bazzite and CachyOS defaults. Applied to both system
# services and user sessions.
mkdir -p /etc/systemd/system.conf.d /etc/systemd/user.conf.d
echo '[Manager]
DefaultLimitNOFILE=1048576' >/etc/systemd/system.conf.d/99-kyth-limits.conf
echo '[Manager]
DefaultLimitNOFILE=1048576' >/etc/systemd/user.conf.d/99-kyth-limits.conf

