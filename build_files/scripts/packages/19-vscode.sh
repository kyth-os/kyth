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

# No GUI launcher is installed here: setup (triggered by the CLI wrapper above,
# or `ujust ai-dev-setup`) can take several minutes on first run with no visible
# progress in a menu-launched GUI app, which reads as a broken/hung icon.
# distrobox-export (kyth-ai-dev setup) installs the real "Visual Studio Code (on
# kyth-ai-dev)" launcher once the container actually has VS Code installed.
