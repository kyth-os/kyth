#!/bin/bash
# shellcheck shell=bash
# 01-tunable-dispatcher — install single dispatcher + 94 compat symlinks (Slice 5)
# Replaces 94 thin bash wrappers (7143 LOC) with one dispatcher and symlinks.
# Preserves symlinks via ln -sf (not cp without -a, which would dereference).
set -euo pipefail

# Install dispatcher
install -Dm0755 /ctx/kyth-tunable /usr/bin/kyth-tunable

# Create compat symlinks for every tunable in tunables.toml
# Use Python to read the registry so the list stays single-source.
mapfile -t tunables < <(python3 -c '
import tomllib
from pathlib import Path
p=Path("/ctx/config/tunables.toml")
if not p.is_file():
    p=Path("build_files/config/tunables.toml")
data=tomllib.load(p.open("rb"))
for name in sorted(data.get("tunables", {})):
    print(name)
')

for t in "${tunables[@]}"; do
    # ln -sf preserves symlink semantics; cp without -a would dereference and duplicate the file
    ln -sf kyth-tunable "/usr/bin/kyth-${t}"
done

echo "tunable-dispatcher: installed kyth-tunable + ${#tunables[@]} symlinks"
