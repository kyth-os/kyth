#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── VS Code Host Wrapper ──────────────────────────────────────────────────────
# VS Code is provided via the kyth-ai-dev container to keep the immutable core slim.
# Host wrapper transparently delegates to the container or prompts setup on first run.

install -Dm 0755 /dev/stdin /usr/bin/code <<'WRAPPEREOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ -x "${HOME}/.local/bin/code" ]]; then
	exec "${HOME}/.local/bin/code" "$@"
fi

box="${KYTH_AI_DEV_BOX:-kyth-ai-dev}"
if command -v distrobox >/dev/null 2>&1 && distrobox list --no-color 2>/dev/null | awk '{print $3}' | grep -qx "${box}"; then
	exec distrobox enter "${box}" -- code "$@"
else
	echo "VS Code is managed in the KythOS AI Developer container (${box})."
	echo "Initializing ${box} environment..."
	kyth-ai-dev setup
	exec distrobox enter "${box}" -- code "$@"
fi
WRAPPEREOF

install -Dm 0644 /dev/stdin /usr/share/applications/code.desktop <<'DESKTOPEOF'
[Desktop Entry]
Name=Visual Studio Code
Comment=Code Editing. Redefined.
GenericName=Text Editor
Exec=/usr/bin/code %F
Icon=vscode
Type=Application
StartupNotify=false
StartupWMClass=Code
Categories=TextEditor;Development;IDE;
MimeType=text/plain;inode/directory;
Actions=new-empty-window;
Keywords=vscode;

[Desktop Action new-empty-window]
Name=New Empty Window
Exec=/usr/bin/code --new-window %F
Icon=vscode
DESKTOPEOF
