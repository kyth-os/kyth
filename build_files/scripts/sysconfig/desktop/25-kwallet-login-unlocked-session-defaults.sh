#!/bin/bash
# shellcheck shell=bash
set -euo pipefail

source "$(dirname "${BASH_SOURCE[0]}")/../../lib/config-helpers.sh"

# ── KWallet: login-unlocked session defaults ─────────────────────────────────
# KWallet's normal low-friction path is a wallet named "kdewallet" protected by
# the login password and opened by kwallet-pam during graphical login. Keep that
# wallet open for the desktop session so Electron/Chromium apps do not trigger a
# second password prompt after the user has already logged in.
write_config /etc/skel/.config/kwalletrc <<'KWALLETRCEOF'
[Wallet]
Enabled=true
Default Wallet=kdewallet
Local Wallet=kdewallet
Use One Wallet=true
Close When Idle=false
Close on Screensaver=false
Leave Open=true
KWALLETRCEOF
