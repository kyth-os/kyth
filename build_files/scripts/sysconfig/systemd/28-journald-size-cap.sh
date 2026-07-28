#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── journald size cap ────────────────────────────────────────────────────────
# On a gaming desktop the journal can silently grow to multi-GB over time from
# verbose game/driver output. Cap persistent storage at 500 MB and the in-memory
# runtime journal (current boot) at 128 MB.
write_config /etc/systemd/journald.conf.d/99-kyth.conf <<'JOURNALDEOF'
[Journal]
SystemMaxUse=500M
RuntimeMaxUse=128M
JOURNALDEOF
