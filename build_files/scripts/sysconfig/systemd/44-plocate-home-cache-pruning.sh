#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# Keep plocate's vendor PRUNEFS/PRUNEPATHS intact, but omit large,
# high-churn cache/dependency trees and Git metadata from its daily scan.
write_config /usr/lib/systemd/system/plocate-updatedb.service.d/50-kyth-home-cache-pruning.conf <<'PLOCATEPRUNEEOF'
[Service]
ExecStart=
ExecStart=/usr/bin/updatedb --add-prunenames ".cache .git node_modules shadercache"
PLOCATEPRUNEEOF
