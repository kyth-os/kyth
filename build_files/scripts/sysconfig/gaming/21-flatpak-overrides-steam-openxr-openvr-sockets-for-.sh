#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Flatpak overrides: Steam OpenXR/OpenVR sockets for WiVRn ───────────────
mkdir -p /etc/flatpak/overrides
cat >/etc/flatpak/overrides/com.valvesoftware.Steam <<'FLATPAKONEOF'
[Context]
filesystems=xdg-run/wivrn:ro;xdg-config/openxr:ro;xdg-config/openvr:ro;
FLATPAKONEOF
