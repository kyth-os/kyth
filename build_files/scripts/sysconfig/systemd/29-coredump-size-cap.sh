#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── systemd-coredump size cap ─────────────────────────────────────────────────
# Nothing in the image bounds systemd-coredump. A crash-looping game/Proton
# process under gaming.slice (large address space, easy to hit on a driver
# bug) can otherwise dump multi-GB cores to /var/lib/systemd/coredump with no
# ceiling. A full /var then cascades into unrelated failures — journald can't
# write, D-Bus activation fails, sddm can't create its runtime dirs — that
# look like random instability rather than "disk is full because of one
# crashing process." Bound it the same way 28-journald-size-cap.sh bounds the
# journal, instead of leaving it unbounded.
#
# ProcessSizeMax/ExternalSizeMax: don't even try to dump (or keep) a core
# larger than 2 GiB — large enough for real Proton/game crash triage, small
# enough that one crash can't consume the disk on its own.
# MaxUse/KeepFree: total coredump storage capped at 1 GiB, and always leave at
# least 2 GiB free on the filesystem regardless — systemd-coredump prunes the
# oldest dumps itself once MaxUse is hit, so this never needs a cleanup timer.
write_config /etc/systemd/coredump.conf.d/99-kyth.conf <<'COREDUMPEOF'
[Coredump]
Storage=external
Compress=yes
ProcessSizeMax=2G
ExternalSizeMax=2G
MaxUse=1G
KeepFree=2G
COREDUMPEOF
