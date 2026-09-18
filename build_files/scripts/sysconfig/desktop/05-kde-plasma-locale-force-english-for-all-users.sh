#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── KDE Plasma locale: seed English for new users ────────────────────────────
# KDE applications (including Discover) use their own locale stack: they read
# plasma-localerc → [Translations] LANGUAGE before falling back to the system
# LANG. Without an explicit entry, KDE may pick whichever AppStream translation
# lands first in the XML (historically Arabic for some packages).
# Seed-only: existing system-wide and skel files are left alone so a user's
# chosen language survives image updates; only missing files get the default.
mkdir -p /etc/skel/.config
if [[ ! -f /etc/xdg/plasma-localerc ]]; then
    write_config /etc/xdg/plasma-localerc <<'PLASMALOCALEEOF'
[Formats]
LC_TIME=en_US.UTF-8

[Translations]
LANGUAGE=en_US
PLASMALOCALEEOF
fi
if [[ ! -f /etc/skel/.config/plasma-localerc ]]; then
    cp /etc/xdg/plasma-localerc /etc/skel/.config/plasma-localerc
fi
