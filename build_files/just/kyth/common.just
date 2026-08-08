# The GHCR org KythOS images are published under. system-updates.just's
# rebase/switch-channel/switch-kernel recipes all need this — kept as one
# constant here rather than hardcoded in each so a future org/repo rename
# (this repo has already had one) only needs a single edit instead of
# updating every recipe that stages a bootc switch on an end user's machine.
export kyth_registry := "ghcr.io/mrtrick37"

# Install a Flatpak app from Flathub, adding the remote first if needed. Internal helper
# shared by the install-* recipes below — keeps the remote-add/install/message boilerplate
# in one place instead of copy-pasted per app.
[group('KythOS')]
[private]
_install-flatpak id name:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! command -v flatpak >/dev/null 2>&1; then
        echo "flatpak is not available on this system." >&2
        exit 1
    fi
    flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
    flatpak install -y flathub {{ id }}
    echo
    echo "{{ name }} installed. Launch it from the app menu."
