#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── KDE Plasma locale: force English for all users ───────────────────────────
# KDE applications (including Discover) use their own locale stack: they read
# plasma-localerc → [Translations] LANGUAGE before falling back to the system
# LANG. Without an explicit entry, KDE may pick whichever AppStream translation
# lands first in the XML (historically Arabic for some packages). Seed the
# system-wide XDG default and the per-user skel so that every session starts
# with English metadata display regardless of LANG propagation timing.
mkdir -p /etc/skel/.config
write_config /etc/xdg/plasma-localerc <<'PLASMALOCALEEOF'
[Formats]
LC_TIME=en_US.UTF-8

[Translations]
LANGUAGE=en_US
PLASMALOCALEEOF
cp /etc/xdg/plasma-localerc /etc/skel/.config/plasma-localerc
