#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

# ── VS Code: KWallet integration ─────────────────────────────────────────────
# Seed new users with argv.json pointing at VS Code's kwallet6 password store.
# KWallet is now unlocked via pam_kwallet6 at login (see 25/26), so enabling
# kwallet6 here gives VS Code and Brave proper secure storage instead of the
# legacy basic store which left credentials in plaintext.
HOME=/etc/skel /ctx/kyth-vscode-wallet
