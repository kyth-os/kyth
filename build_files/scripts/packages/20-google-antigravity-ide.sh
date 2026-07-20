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

# No GUI launcher is installed here: setup (triggered by the CLI wrapper above,
# or `ujust ai-dev-setup`) can take several minutes on first run with no visible
# progress in a menu-launched GUI app, which reads as a broken/hung icon.
# distrobox-export (kyth-ai-dev setup) installs the real "Google Antigravity (on
# kyth-ai-dev)" launcher once the container actually has Antigravity installed.
