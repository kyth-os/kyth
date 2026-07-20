#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── Windows environment management tools ─────────────────────────────────────
# RDP, Active Directory, Kerberos, and SMB tooling in standard Fedora repos.
# Azure CLI is provided via the kyth-ai-dev container to keep the core OS slim.

install -Dm 0755 /dev/stdin /usr/bin/az <<'WRAPPEREOF'
#!/usr/bin/env bash
set -euo pipefail

if [[ -x "${HOME}/.local/bin/az" ]]; then
	exec "${HOME}/.local/bin/az" "$@"
fi

box="${KYTH_AI_DEV_BOX:-kyth-ai-dev}"
if command -v distrobox >/dev/null 2>&1 && distrobox list --no-color 2>/dev/null | awk '{print $3}' | grep -qx "${box}"; then
	exec distrobox enter "${box}" -- az "$@"
else
	echo "Azure CLI is managed in the KythOS AI Developer container (${box})."
	echo "Initializing ${box} environment..."
	kyth-ai-dev setup
	exec distrobox enter "${box}" -- az "$@"
fi
WRAPPEREOF

# RDP and SMB tooling — standard Fedora repos.
# freerdp: best-in-class RDP client; powers Remmina's RDP backend.
# samba-client: smbclient + net ads + wbinfo for SMB share browsing.
dnf5 install -y --skip-unavailable \
	freerdp \
	samba-client

