#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "../../lib/config-helpers.sh"

# ── Flatpak overrides: Steam OpenXR/OpenVR sockets for WiVRn ───────────────
write_config /etc/flatpak/overrides/com.valvesoftware.Steam <<'FLATPAKONEOF'
[Context]
filesystems=xdg-run/wivrn:ro;xdg-config/openxr:ro;xdg-config/openvr:ro;
FLATPAKONEOF
