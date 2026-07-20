#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Google Antigravity Host Wrapper ───────────────────────────────────────────
# Google Antigravity IDE is provided via the kyth-ai-dev container to keep the immutable core slim.
# Host wrapper transparently delegates to the container or prompts setup on first run.

install -Dm 0755 /dev/stdin /usr/bin/antigravity <<'WRAPPEREOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ -x "${HOME}/.local/bin/antigravity" ]]; then
	exec "${HOME}/.local/bin/antigravity" "$@"
fi

box="${KYTH_AI_DEV_BOX:-kyth-ai-dev}"
if command -v distrobox >/dev/null 2>&1 && distrobox list --no-color 2>/dev/null | awk '{print $3}' | grep -qx "${box}"; then
	exec distrobox enter "${box}" -- antigravity "$@"
else
	echo "Google Antigravity IDE is managed in the KythOS AI Developer container (${box})."
	echo "Initializing ${box} environment..."
	kyth-ai-dev setup
	exec distrobox enter "${box}" -- antigravity "$@"
fi
WRAPPEREOF

install -Dm 0644 /dev/stdin /usr/share/applications/antigravity.desktop <<'DESKTOPEOF'
[Desktop Entry]
Name=Google Antigravity
Comment=Google Antigravity AI IDE
GenericName=Text Editor
Exec=/usr/bin/antigravity %F
Icon=antigravity
Type=Application
StartupNotify=false
StartupWMClass=antigravity
Categories=Development;IDE;
MimeType=text/plain;inode/directory;
Keywords=antigravity;ide;ai;
DESKTOPEOF
