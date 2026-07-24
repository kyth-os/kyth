#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── NXM mod link handler ──────────────────────────────────────────────────────
# Nexus Mods uses nxm:// URIs to hand off mod downloads to a local manager
# (Vortex, Mod Organizer 2).  Register a system-wide handler so Firefox and
# Chrome pass these URIs to kyth-nxm-handler, which routes them to the
# user's installed mod manager (Vortex in Bottles preferred, then MO2).
install -m 0755 /ctx/sysconfig/kyth-nxm-handler /usr/bin/kyth-nxm-handler

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
