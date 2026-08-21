#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── journald size cap ────────────────────────────────────────────────────────
# On a gaming desktop the journal can silently grow to multi-GB over time from
# verbose game/driver output. Cap persistent storage and the in-memory runtime
# journal (current boot).
#
# A tight 500M cap with no SystemMaxFileSize left ordinary, months-of-normal-use
# growth sitting right at the ceiling: systemd-journal-flush.service (a stock,
# unavoidable part of early boot, well before local-fs.target) then has to
# vacuum old archived journals back under the cap on every single boot, and
# that vacuum was observed stalling ALL logging (kernel included — journald
# also brokers /dev/kmsg) for ~30s while it ran under full boot I/O contention.
# That single stall was previously misread as a zram/udev-specific hang,
# because systemd-zram-setup@zram0.service's dev-zram0.device wait has its own
# tight 30s JobTimeoutSec (see 51-zram.sh) and happened to trip right at the
# end of it. Give real headroom (4x the old cap; negligible on any disk this
# ships on) and a bounded per-file size so any future vacuum only ever has to
# drop one small file at a time instead of reclaiming a multi-file backlog in
# one synchronous burst during the most I/O-contended part of boot.
write_config /etc/systemd/journald.conf.d/99-kyth.conf <<'JOURNALDEOF'
[Journal]
SystemMaxUse=2G
SystemMaxFileSize=32M
RuntimeMaxUse=128M
JOURNALDEOF
