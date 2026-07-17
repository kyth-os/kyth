#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── NXM mod link handler ──────────────────────────────────────────────────────
# Nexus Mods uses nxm:// URIs to hand off mod downloads to a local manager
# (Vortex, Mod Organizer 2).  Register a system-wide handler so Firefox and
# Chrome pass these URIs to kyth-nxm-handler, which routes them to the
# user's installed mod manager (Vortex in Bottles preferred, then MO2).
cat >/usr/bin/kyth-nxm-handler <<'NXMEOF'
#!/usr/bin/env bash
# Route nxm:// URIs to the user's mod manager.
# Vortex in Bottles is the recommended default; MO2 is a supported alternative.
NXM_URL="${1:-}"
if [[ -z "${NXM_URL}" ]]; then
    echo "Usage: kyth-nxm-handler nxm://..." >&2
    exit 1
fi

# Check for Vortex bottle
VORTEX_BOTTLE="${HOME}/.local/share/bottles/bottles/Vortex"
if [[ -d "${VORTEX_BOTTLE}" ]] && command -v bottles-cli >/dev/null 2>&1; then
    bottles-cli run -b Vortex -e "Vortex.exe" -- "${NXM_URL}"
    exit 0
fi

# Fallback: notify the user
if command -v notify-send >/dev/null 2>&1; then
    notify-send "NXM Link" \
        "Install Vortex in Bottles to handle Nexus Mods download links automatically.\nLink: ${NXM_URL}" \
        --icon=application-x-addon
fi

# Open the Gaming page guidance in a terminal
echo "NXM link received: ${NXM_URL}"
echo "Install Vortex via Bottles to enable automatic mod downloads."
NXMEOF
chmod +x /usr/bin/kyth-nxm-handler

cat >/usr/share/applications/kyth-nxm-handler.desktop <<'NXMDESKEOF'
[Desktop Entry]
Type=Application
Name=KythOS NXM Handler
Comment=Route Nexus Mods download links to your mod manager
Exec=/usr/bin/kyth-nxm-handler %u
MimeType=x-scheme-handler/nxm;x-scheme-handler/nxm-protocol;
NoDisplay=true
Terminal=false
NXMDESKEOF
