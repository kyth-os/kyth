#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Locale defaults ─────────────────────────────────────────────────────────
# Force a 12-hour AM/PM clock by default on installed systems.
# LANG keeps the desktop in US English; LC_TIME specifically controls date/time
# formatting for Plasma, Qt, and libc-aware apps.
cat >/etc/locale.conf <<'LOCALEEOF'
LANG=en_US.UTF-8
LC_TIME=en_US.UTF-8
LOCALEEOF

