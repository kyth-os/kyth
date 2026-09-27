#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Locale defaults ─────────────────────────────────────────────────────────
# Seed-only: write /etc/locale.conf when the installer (or the user) has not
# set one. Clobbering an existing file would discard the installer's language
# choice on every image update.
# LANG keeps the desktop in US English; LC_TIME specifically controls date/time
# formatting for Plasma, Qt, and libc-aware apps (12-hour AM/PM by default).
if [[ ! -f /etc/locale.conf ]]; then
    write_config /etc/locale.conf <<'LOCALEEOF'
LANG=en_US.UTF-8
LC_TIME=en_US.UTF-8
LOCALEEOF
fi
