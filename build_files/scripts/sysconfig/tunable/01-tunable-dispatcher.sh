#!/bin/bash
# shellcheck shell=bash
# 01-tunable-dispatcher — install single dispatcher + 94 compat symlinks (Slice 5)
# Replaces 94 thin bash wrappers (7143 LOC) with one dispatcher and symlinks.
# Preserves symlinks via ln -sf (not cp without -a, which would dereference).
set -euo pipefail

# Install dispatcher
install -Dm0755 /ctx/kyth-tunable /usr/bin/kyth-tunable
install -Dm0755 /usr/bin/kyth-tunable-rs /usr/bin/kyth-tunable-rs

# Create compat symlinks for every tunable in the native registry.
mapfile -t tunables < <(/usr/bin/kyth-tunable-rs --list)
mapfile -t native_tunables < <(/usr/bin/kyth-tunable-rs --list-native)
declare -A native_lookup=()
for t in "${native_tunables[@]}"; do
    native_lookup["$t"]=1
done

# All current registry entries have native Rust dispatch parity. Keep the
# compatibility branch for forward-compatible registry additions and rollback
# to older images.

for t in "${tunables[@]}"; do
    # ln -sf preserves symlink semantics; cp without -a would dereference and duplicate the file
    if [[ ${native_lookup[$t]+yes} ]]; then
        ln -sf kyth-tunable-rs "/usr/bin/kyth-${t}"
    else
        ln -sf kyth-tunable "/usr/bin/kyth-${t}"
    fi
done

echo "tunable-dispatcher: installed kyth-tunable + ${#tunables[@]} symlinks (${#native_tunables[@]} native)"
