#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── VS Code: avoid KWallet password prompts ──────────────────────────────────
# Seed new users with argv.json pointing at VS Code's basic password store.
# KWallet PAM unlock is fragile across autologin/session restore paths; the
# local encrypted-at-rest desktop is less annoying when apps do not wake KWallet.
HOME=/etc/skel /ctx/kyth-vscode-wallet
