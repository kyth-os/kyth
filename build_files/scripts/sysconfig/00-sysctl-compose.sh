#!/bin/bash
# shellcheck shell=bash
# 00-sysctl-compose — consolidated sysctl generator (single writer for 99-kyth-*.conf).
# Runs in sysconfig-static layer; replaces fragmented write_config sysctl fragments.
set -euo pipefail

PYTHONPATH="/ctx/kyth_shared:${PYTHONPATH:-}" python3 -m kyth_shared.sysctl_compose --emit-all

# Ensure legacy colliding files are gone; generator is single writer
rm -f /etc/sysctl.d/99-kyth.conf \
      /etc/sysctl.d/99-kyth-vm-compaction.conf \
      /etc/sysctl.d/99-kyth-network-qdisc.conf 2>/dev/null || true

# Remove stale per-tunable 99-kyth-*.conf that are now consolidated in base/gaming/network tiers
# (Slice 5: 94 thin wrappers -> dispatcher; per-tunable sysctl files are superseded by sysctl_compose)
# Keep only the 3 composed files; remove any other 99-kyth-*.conf that matches a tunable name.
if [[ -f /ctx/config/tunables.toml ]]; then
    while IFS= read -r tunable; do
        rm -f "/etc/sysctl.d/99-kyth-${tunable}.conf" 2>/dev/null || true
    done < <(python3 -c '
import tomllib
from pathlib import Path
p=Path("/ctx/config/tunables.toml")
if p.is_file():
    with p.open("rb") as f:
        data=tomllib.load(f)
    for name, spec in data.get("tunables", {}).items():
        if spec.get("kind")=="sysctl":
            print(name)
')
fi
# Also handle bare-metal fallback when /ctx not mounted (local host apply)
if [[ -f build_files/config/tunables.toml ]]; then
    while IFS= read -r tunable; do
        rm -f "/etc/sysctl.d/99-kyth-${tunable}.conf" 2>/dev/null || true
    done < <(python3 -c '
import tomllib
from pathlib import Path
p=Path("build_files/config/tunables.toml")
if p.is_file():
    with p.open("rb") as f:
        data=tomllib.load(f)
    for name, spec in data.get("tunables", {}).items():
        if spec.get("kind")=="sysctl":
            print(name)
')
fi

# Modules that were previously loaded by retired fragments — still needed.
mkdir -p /etc/modules-load.d
printf '%s\n' 'tcp_bbr' > /etc/modules-load.d/bbr.conf
chmod 0644 /etc/modules-load.d/bbr.conf

if [[ -f /ctx/config/sysctl.conf ]]; then
    echo "00-sysctl-compose: dead file /ctx/config/sysctl.conf still present — delete after migrating keys" >&2
    exit 1
fi

# shellcheck disable=SC2012
echo "00-sysctl-compose: emitted $(ls -1 /etc/sysctl.d/99-kyth-*.conf 2>/dev/null | tr '\n' ' ')"
